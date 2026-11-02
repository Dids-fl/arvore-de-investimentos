"""
Coleta e cache dos indicadores de mercado usados pelo recomendador.

Fontes:
    - SELIC meta: BCB/SGS, série 432.
    - IPCA acumulado em 12 meses: BCB/SGS, série 13522.
    - Expectativa anual da SELIC: BCB/Olinda (Focus).
    - CAGR do Ibovespa: Yahoo Finance, via yfinance.

O módulo não inventa taxas fixas quando uma fonte falha. Se uma atualização
online não for possível, pode reutilizar por um período limitado um cache real
anterior, sempre acrescentando um aviso explícito ao resultado.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import os
import tempfile
import threading
import time
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import MAX_RETRIES, REQUEST_TIMEOUT, RETRY_BACKOFF
from utils.exceptions import DadosIndisponiveisError
from utils.formatacao import formatar_pct
from utils.logging_config import get_logger

logger = get_logger(__name__)

# ── Configuração ──────────────────────────────────────────────────────────────

CACHE_FILE = (
    Path.home() / ".cache" / "recomendador_investimentos_market.json"
)
CACHE_TTL_SECONDS = 6 * 60 * 60
STALE_CACHE_MAX_AGE_SECONDS = 7 * 24 * 60 * 60

# A versão 4 inclui a curva anual do Focus e invalida caches que guardavam
# apenas uma expectativa isolada para a SELIC.
CACHE_SCHEMA_VERSION = 4

SGS_SELIC = 432
SGS_IPCA_12M = 13522
# Séries opcionais (gratuitas, BCB/SGS). A ausência delas gera aviso, nunca
# um número inventado.
SGS_CDI_ANUAL = 4389     # CDI anualizado base 252, % a.a.
SGS_POUPANCA = 195       # Rentabilidade da poupança (regra de 2012), % no mês

_SGS_URL = (
    "https://api.bcb.gov.br/dados/serie/"
    "bcdata.sgs.{serie}/dados"
)


# ── Sessão HTTP com retry automático ─────────────────────────────────────────

def _build_http_session() -> requests.Session:
    retry = Retry(
        total=MAX_RETRIES,
        connect=MAX_RETRIES,
        read=MAX_RETRIES,
        status=MAX_RETRIES,
        backoff_factor=RETRY_BACKOFF,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
        raise_on_status=False,
    )

    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "recomendador-investimentos/1.0 "
                "(dados-publicos; contato-via-repositorio)"
            ),
            "Accept": "application/json",
        }
    )
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


_HTTP = _build_http_session()


# ── yfinance ──────────────────────────────────────────────────────────────────

try:
    import yfinance as yf
except ImportError:
    yf = None
    logger.warning(
        "yfinance não está instalado. O CAGR do Ibovespa não poderá ser "
        "atualizado; instale as dependências do projeto."
    )

try:
    from bcb import Expectativas
except ImportError:
    Expectativas = None
    logger.warning(
        "python-bcb não está instalado. A curva Focus da SELIC não poderá "
        "ser atualizada; instale as dependências do projeto."
    )


# ── Funções auxiliares ────────────────────────────────────────────────────────

def _utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _json_get(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    timeout=REQUEST_TIMEOUT,
) -> Any:
    response = _HTTP.get(url, params=params, timeout=timeout)
    response.raise_for_status()

    try:
        return response.json()
    except requests.exceptions.JSONDecodeError as exc:
        content_type = response.headers.get("Content-Type", "desconhecido")
        raise RuntimeError(
            f"Resposta não é JSON válido (Content-Type: {content_type})."
        ) from exc


def _is_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _validar_taxa(
    value: Any,
    nome: str,
    *,
    minimo: float,
    maximo: float,
) -> float:
    if not _is_number(value):
        raise ValueError(f"{nome}: valor não numérico ou não finito: {value!r}")

    taxa = float(value)
    if not minimo <= taxa <= maximo:
        raise ValueError(
            f"{nome}: valor fora do intervalo plausível "
            f"[{minimo:.2f}, {maximo:.2f}]: {taxa:.6f}"
        )
    return taxa


def _validar_payload_cache(data: Any) -> bool:
    if not isinstance(data, dict):
        return False

    if data.get("_schema_version") != CACHE_SCHEMA_VERSION:
        return False

    required = {
        "selic",
        "focus_selic",
        "focus_selic_por_ano",
        "ipca",
        "ibov_cagr",
        "data_ref",
        "fontes",
        "avisos",
        "fetched_at",
    }
    if not required.issubset(data):
        return False

    try:
        _validar_taxa(data["selic"], "SELIC em cache", minimo=0.0, maximo=1.0)
        _validar_taxa(
            data["ipca"],
            "IPCA em cache",
            minimo=-0.20,
            maximo=1.0,
        )
        if data["ibov_cagr"] is not None:
            _validar_taxa(
                data["ibov_cagr"],
                "CAGR do Ibovespa em cache",
                minimo=-0.90,
                maximo=2.0,
            )
        if data["focus_selic"] is not None:
            _validar_taxa(
                data["focus_selic"],
                "Focus SELIC em cache",
                minimo=0.0,
                maximo=1.0,
            )
        focus_por_ano = data["focus_selic_por_ano"]
        if not isinstance(focus_por_ano, dict):
            return False
        for ano, taxa in focus_por_ano.items():
            ano_inteiro = int(ano)
            if ano_inteiro < 1900 or ano_inteiro > 9999:
                return False
            _validar_taxa(
                taxa,
                f"Focus SELIC {ano_inteiro} em cache",
                minimo=0.0,
                maximo=1.0,
            )
    except (TypeError, ValueError):
        return False

    return (
        isinstance(data["data_ref"], str)
        and bool(data["data_ref"].strip())
        and isinstance(data["fontes"], list)
        and isinstance(data["avisos"], list)
        and isinstance(data["fetched_at"], str)
    )


def _read_market_cache() -> tuple[dict | None, float | None]:
    """Lê um cache válido e devolve também sua idade em segundos."""
    try:
        if not CACHE_FILE.is_file():
            return None, None

        age_seconds = max(0.0, time.time() - CACHE_FILE.stat().st_mtime)
        with CACHE_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)

        if not _validar_payload_cache(data):
            logger.warning(
                "Cache de mercado ausente, incompatível ou inválido; "
                "uma atualização online será feita."
            )
            return None, None

        return data, age_seconds
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(f"Erro ao ler cache de mercado: {exc}")
        return None, None


def _load_market_cache(
    max_age_seconds: float = CACHE_TTL_SECONDS,
) -> dict | None:
    """Mantém compatibilidade com chamadas e testes da versão anterior."""
    data, age_seconds = _read_market_cache()
    if data is None or age_seconds is None or age_seconds > max_age_seconds:
        return None

    logger.info(
        "Cache de mercado carregado (idade: %.1f minutos).",
        age_seconds / 60,
    )
    return data


def _save_market_cache(payload: dict) -> None:
    """
    Salva o cache de forma atômica.

    O arquivo temporário é criado no mesmo diretório para que os.replace()
    não atravesse sistemas de arquivos diferentes.
    """
    temp_path: Path | None = None
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=CACHE_FILE.parent,
            prefix=f".{CACHE_FILE.name}.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            json.dump(payload, temp_file, ensure_ascii=False, indent=2)
            temp_file.flush()
            os.fsync(temp_file.fileno())

        os.replace(temp_path, CACHE_FILE)
        logger.info("Cache de mercado salvo.")
    except (OSError, TypeError, ValueError) as exc:
        logger.warning(f"Erro ao salvar cache de mercado: {exc}")
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass


def _cache_antigo_com_aviso(
    data: dict,
    age_seconds: float,
    falhas: dict[str, str],
) -> dict:
    fallback = dict(data)
    fallback["fontes"] = list(data.get("fontes", []))
    fallback["avisos"] = list(data.get("avisos", []))
    fallback["cache_status"] = "stale"

    idade_horas = age_seconds / 3600
    campos = ", ".join(sorted(falhas))
    fallback["avisos"].append(
        "⚠️  Não foi possível atualizar todos os indicadores "
        f"({campos}). Foram usados dados reais do cache, com "
        f"{idade_horas:.1f} hora(s) de idade."
    )
    return fallback


# ── Coletores ─────────────────────────────────────────────────────────────────

_BRASILAPI_TAXAS_URL = "https://brasilapi.com.br/api/taxas/v1"
_BRASILAPI_NOMES = {SGS_SELIC: "Selic", SGS_IPCA_12M: "IPCA", SGS_CDI_ANUAL: "CDI"}


def _fetch_brasilapi_taxa(serie: int) -> tuple[float, str]:
    """Selic, CDI ou IPCA 12 meses pela BrasilAPI (gratuita, sem chave).

    A BrasilAPI republica os dados do Banco Central; serve de reserva quando
    o SGS está fora do ar. Não informa a data de referência, então a
    referência registra o dia da consulta e a fonte.
    """
    nome = _BRASILAPI_NOMES[serie]
    data = _json_get(_BRASILAPI_TAXAS_URL)
    for item in data if isinstance(data, list) else []:
        if isinstance(item, dict) and str(item.get("nome", "")).casefold() == nome.casefold():
            valor = item.get("valor")
            if _is_number(valor):
                hoje = dt.datetime.now(dt.timezone.utc).date()
                return float(valor) / 100.0, f"{hoje:%d/%m/%Y}, via BrasilAPI"
    raise RuntimeError(f"BrasilAPI: taxa {nome} ausente.")


def _fetch_taxa_bcb(serie: int) -> tuple[float, str]:
    """SGS do Banco Central; se falhar, a mesma taxa pela BrasilAPI."""
    try:
        return _fetch_sgs_value(serie)
    except Exception as erro_sgs:  # noqa: BLE001 — qualquer falha tenta a reserva
        try:
            valor = _fetch_brasilapi_taxa(serie)
        except Exception:  # noqa: BLE001
            raise erro_sgs from None
        logger.warning("SGS série %s indisponível (%s); usando BrasilAPI.", serie, erro_sgs)
        return valor


def _fetch_sgs_value(serie: int) -> tuple[float, str]:
    hoje = dt.datetime.now(dt.timezone.utc).date()
    data_inicial = hoje - dt.timedelta(days=90)
    data = _json_get(
        _SGS_URL.format(serie=serie),
        params={
            "formato": "json",
            "dataInicial": data_inicial.strftime("%d/%m/%Y"),
            "dataFinal": hoje.strftime("%d/%m/%Y"),
        },
    )
    if not isinstance(data, list) or not data:
        raise RuntimeError(f"SGS série {serie}: resposta vazia ou inesperada.")

    candidatos: list[tuple[dt.date, float, str]] = []
    for item in data:
        if not isinstance(item, dict):
            continue

        raw = str(item.get("valor", "")).strip()
        data_ref = str(item.get("data", "")).strip()
        if not raw or not data_ref:
            continue

        try:
            value = float(raw.replace(",", ".")) / 100.0
            data_item = dt.datetime.strptime(data_ref, "%d/%m/%Y").replace(tzinfo=dt.timezone.utc).date()
        except (TypeError, ValueError):
            continue

        if data_item > hoje or not math.isfinite(value):
            continue
        candidatos.append((data_item, value, data_ref))

    if not candidatos:
        raise RuntimeError(f"SGS série {serie}: nenhum valor válido.")

    _, value, data_ref = max(candidatos, key=lambda item: item[0])
    return value, data_ref


def _fetch_focus_selic() -> float | None:
    """Compatibilidade: devolve a primeira expectativa anual disponível."""
    focus_por_ano = _fetch_focus_selic_por_ano()
    return next(iter(focus_por_ano.values()), None)


def _fetch_focus_selic_por_ano(
    quantidade_anos: int = 4,
) -> dict[int, float]:
    """Obtém as medianas Focus da SELIC para o ano atual e os seguintes."""
    return _fetch_focus_por_ano("Selic", quantidade_anos)


def _fetch_focus_ipca_por_ano(
    quantidade_anos: int = 4,
) -> dict[int, float]:
    """Obtém as medianas Focus do IPCA para o ano atual e os seguintes."""
    return _fetch_focus_por_ano("IPCA", quantidade_anos)


def _fetch_poupanca_anual() -> tuple[float, str]:
    """Rentabilidade mensal mais recente da poupança, anualizada."""
    mensal, referencia = _fetch_sgs_value(SGS_POUPANCA)
    return (1.0 + mensal) ** 12 - 1.0, referencia


def _fetch_focus_por_ano(
    indicador: str,
    quantidade_anos: int = 4,
) -> dict[int, float]:
    """Obtém as medianas Focus de ``indicador`` por ano de referência."""
    if Expectativas is None:
        return {}
    if quantidade_anos <= 0:
        raise ValueError("quantidade_anos deve ser maior que zero.")

    hoje = dt.datetime.now(dt.timezone.utc).date()
    data_inicial = hoje - dt.timedelta(days=120)
    resultado: dict[int, float] = {}

    try:
        expectativas = Expectativas()
        endpoint = expectativas.get_endpoint("ExpectativasMercadoAnuais")
    except (requests.exceptions.RequestException, RuntimeError, ValueError, TypeError, AttributeError) as exc:
        logger.warning(f"Erro ao inicializar o serviço Focus: {exc}")
        return {}

    for ano_referencia in range(
        hoje.year,
        hoje.year + quantidade_anos,
    ):
        try:
            tabela = (
                endpoint.query()
                .filter(
                    endpoint.Indicador == indicador,
                    endpoint.DataReferencia == ano_referencia,
                    endpoint.Data >= data_inicial,
                    endpoint.baseCalculo == 0,
                )
                .select(
                    endpoint.Data,
                    endpoint.DataReferencia,
                    endpoint.Mediana,
                )
                .orderby(endpoint.Data.desc())
                .limit(1)
                .collect()
            )
            if tabela.empty:
                continue

            mediana = _validar_taxa(
                float(tabela.iloc[0]["Mediana"]) / 100.0,
                f"Focus {indicador} {ano_referencia}",
                minimo=-0.20,
                maximo=1.0,
            )
            resultado[ano_referencia] = mediana
            logger.info(
                "Focus %s carregado: %.2f%% para %d.",
                indicador,
                mediana * 100,
                ano_referencia,
            )
        except (
            requests.exceptions.RequestException,
            RuntimeError,
            ValueError,
            TypeError,
            AttributeError,
            KeyError,
        ) as exc:
            logger.warning(
                "Erro ao buscar Focus %s para %s: %s",
                indicador,
                ano_referencia,
                exc,
            )

    return resultado


_HISTORICO_IBOV: dict[str, Any] = {"ts": 0.0, "closes": None}
_HISTORICO_IBOV_LOCK = threading.Lock()


def _historico_ibov_10a():
    """Fechamentos do Ibovespa em 10 anos, baixados uma vez por carga."""
    if yf is None:
        return None
    with _HISTORICO_IBOV_LOCK:
        if _HISTORICO_IBOV["closes"] is not None and time.time() - _HISTORICO_IBOV["ts"] < 600:
            return _HISTORICO_IBOV["closes"]
        history = yf.Ticker("^BVSP").history(
            period="10y",
            interval="1d",
            auto_adjust=False,
            actions=False,
        )
        if history is None or "Close" not in history:
            return None
        closes = history["Close"].dropna()
        _HISTORICO_IBOV.update(ts=time.time(), closes=closes)
        return closes


def _fetch_ibov_volatilidade_10a() -> float | None:
    """Volatilidade anual do Ibovespa (base do cenário pessimista de ações)."""
    from macroeconomia.premio_acoes import volatilidade_anual

    try:
        closes = _historico_ibov_10a()
        if closes is None or len(closes) < 250:
            return None
        indice = closes.copy()
        indice.index = indice.index.tz_localize(None) if indice.index.tz is not None else indice.index
        vol = volatilidade_anual(indice, indice.index.max())
        return None if vol is None else _validar_taxa(vol, "Volatilidade do Ibovespa", minimo=0.0, maximo=2.0)
    except (
        requests.exceptions.RequestException,
        ValueError,
        TypeError,
        RuntimeError,
        OSError,
        AttributeError,
        KeyError,
    ) as exc:
        logger.warning(f"Erro ao calcular volatilidade do Ibovespa: {exc}")
        return None


def _fetch_ibov_cagr_10a() -> float | None:
    if yf is None:
        return None

    try:
        closes = _historico_ibov_10a()
        if closes is None:
            return None
        if len(closes) < 200:
            logger.warning(
                "Histórico insuficiente do Ibovespa: %d observações.",
                len(closes),
            )
            return None

        initial_close = float(closes.iloc[0])
        final_close = float(closes.iloc[-1])
        if initial_close <= 0 or final_close <= 0:
            return None

        first_date = closes.index[0]
        last_date = closes.index[-1]
        years = (
            (last_date - first_date).total_seconds()
            / (365.2425 * 24 * 60 * 60)
        )
        if years < 1.0:
            return None

        cagr = (final_close / initial_close) ** (1.0 / years) - 1.0
        return _validar_taxa(
            cagr,
            "CAGR do Ibovespa",
            minimo=-0.90,
            maximo=2.0,
        )
    except (
        requests.exceptions.RequestException,
        ValueError,
        TypeError,
        RuntimeError,
        OSError,
        AttributeError,
        KeyError,
    ) as exc:
        logger.warning(f"Erro ao buscar histórico do Ibovespa: {exc}")
        return None


def _extras_opcionais(results: Mapping[str, Any]) -> dict[str, Any]:
    """Valida CDI, poupança e Focus IPCA sem tornar nenhum deles obrigatório."""
    fontes: list[str] = []
    avisos: list[str] = []
    extras: dict[str, Any] = {
        "cdi": None,
        "cdi_ref": None,
        "poupanca": None,
        "poupanca_ref": None,
        "focus_ipca_por_ano": {},
    }

    for chave, rotulo, serie in (
        ("cdi", "CDI", SGS_CDI_ANUAL),
        ("poupanca", "Poupança (anualizada)", SGS_POUPANCA),
    ):
        bruto = results.get(chave)
        try:
            if bruto is None:
                raise ValueError("fonte sem valor válido")
            valor, referencia = bruto
            valor = _validar_taxa(valor, rotulo, minimo=0.0, maximo=1.0)
            if not isinstance(referencia, str) or not referencia.strip():
                raise ValueError("data de referência ausente")
        except (TypeError, ValueError) as exc:
            logger.warning("%s indisponível: %s", rotulo, exc)
            avisos.append(
                f"⚠️  {rotulo} indisponível; o comparativo correspondente "
                "foi omitido."
            )
            continue
        extras[chave] = valor
        extras[f"{chave}_ref"] = referencia
        fontes.append(
            f"{rotulo} {formatar_pct(valor)} a.a. — BCB/SGS série {serie} "
            f"(ref. {referencia})"
        )

    focus_ipca = results.get("focus_ipca_por_ano")
    if isinstance(focus_ipca, Mapping):
        for ano_bruto, taxa_bruta in focus_ipca.items():
            try:
                ano = int(ano_bruto)
                extras["focus_ipca_por_ano"][ano] = _validar_taxa(
                    taxa_bruta,
                    f"Focus IPCA {ano}",
                    minimo=-0.20,
                    maximo=1.0,
                )
            except (TypeError, ValueError) as exc:
                logger.warning(f"Ponto do Focus IPCA ignorado: {exc}")
    extras["focus_ipca_por_ano"] = dict(
        sorted(extras["focus_ipca_por_ano"].items())
    )
    for ano, taxa in extras["focus_ipca_por_ano"].items():
        fontes.append(
            f"Previsão IPCA Focus {ano}: {formatar_pct(taxa)} a.a. — BCB/Olinda"
        )

    extras["_fontes"] = fontes
    extras["_avisos"] = avisos
    return extras


# ── API pública ───────────────────────────────────────────────────────────────

def load_market_data(
    *,
    force_refresh: bool = False,
    allow_stale_cache: bool = True,
) -> dict:
    """
    Obtém os indicadores de mercado usados pelo recomendador.

    Args:
        force_refresh:
            Ignora um cache ainda fresco e tenta atualizar as fontes.
        allow_stale_cache:
            Em caso de falha online, permite reutilizar cache real com no
            máximo sete dias, acrescentando aviso explícito.

    Raises:
        DadosIndisponiveisError:
            Quando algum indicador obrigatório não pode ser obtido e não há
            cache aceitável.
    """
    cached_data, cache_age = _read_market_cache()

    if (
        not force_refresh
        and cached_data is not None
        and cache_age is not None
        and cache_age <= CACHE_TTL_SECONDS
    ):
        logger.info(
            "Cache de mercado carregado (idade: %.1f minutos).",
            cache_age / 60,
        )
        return cached_data

    fetchers = {
        "selic": lambda: _fetch_taxa_bcb(SGS_SELIC),
        "ipca": lambda: _fetch_taxa_bcb(SGS_IPCA_12M),
        "focus_selic_por_ano": _fetch_focus_selic_por_ano,
        "ibov_cagr": _fetch_ibov_cagr_10a,
        # Opcionais: enriquecem a análise, mas não bloqueiam o carregamento.
        "ibov_volatilidade": _fetch_ibov_volatilidade_10a,
        "cdi": lambda: _fetch_taxa_bcb(SGS_CDI_ANUAL),
        "poupanca": _fetch_poupanca_anual,
        "focus_ipca_por_ano": _fetch_focus_ipca_por_ano,
    }
    # O CAGR do Ibovespa é só informativo desde que as projeções passaram a
    # usar a curva de juros (ver engine.taxas_por_risco).
    opcionais = {
        "focus_selic_por_ano",
        "cdi",
        "poupanca",
        "focus_ipca_por_ano",
        "ibov_cagr",
        "ibov_volatilidade",
    }

    results: dict[str, Any] = {}
    failures: dict[str, str] = {}

    with ThreadPoolExecutor(max_workers=len(fetchers)) as executor:
        futures = {
            executor.submit(fetcher): key
            for key, fetcher in fetchers.items()
        }
        for future in as_completed(futures):
            key = futures[future]
            try:
                value = future.result()
                results[key] = value
                if value is None and key not in opcionais:
                    failures[key] = "fonte sem valor válido"
            except Exception as exc:  # noqa: BLE001
                # Bibliotecas de terceiros (yfinance, python-bcb) levantam
                # exceções próprias, como YFRateLimitError. Qualquer falha de
                # uma fonte vira "fonte indisponível": opcional segue sem o
                # dado; obrigatória cai no cache antigo ou no erro explícito.
                logger.warning(f"Falha ao obter {key}: {type(exc).__name__}: {exc}")
                results[key] = None
                if key not in opcionais:
                    failures[key] = str(exc)

    selic_raw = results.get("selic")
    ipca_raw = results.get("ipca")
    focus_raw = results.get("focus_selic_por_ano")
    ibov_raw = results.get("ibov_cagr")

    selic_value: float | None = None
    ipca_value: float | None = None
    ibov_value: float | None = None
    selic_ref = ""
    ipca_ref = ""

    try:
        if selic_raw is None:
            raise ValueError("fonte sem valor válido")
        selic_value, selic_ref = selic_raw
        selic_value = _validar_taxa(
            selic_value,
            "SELIC",
            minimo=0.0,
            maximo=1.0,
        )
        if not isinstance(selic_ref, str) or not selic_ref.strip():
            raise ValueError("data de referência ausente")
    except (TypeError, ValueError) as exc:
        failures["selic"] = str(exc)

    try:
        if ipca_raw is None:
            raise ValueError("fonte sem valor válido")
        ipca_value, ipca_ref = ipca_raw
        ipca_value = _validar_taxa(
            ipca_value,
            "IPCA 12 meses",
            minimo=-0.20,
            maximo=1.0,
        )
        if not isinstance(ipca_ref, str) or not ipca_ref.strip():
            raise ValueError("data de referência ausente")
    except (TypeError, ValueError) as exc:
        failures["ipca"] = str(exc)

    try:
        if ibov_raw is not None:
            ibov_value = _validar_taxa(
                ibov_raw,
                "CAGR do Ibovespa",
                minimo=-0.90,
                maximo=2.0,
            )
    except (TypeError, ValueError) as exc:
        logger.warning(f"CAGR do Ibovespa descartado: {exc}")
    ibov_vol = results.get("ibov_volatilidade")

    focus_por_ano: dict[int, float] = {}
    if isinstance(focus_raw, Mapping):
        for ano_bruto, taxa_bruta in focus_raw.items():
            try:
                ano = int(ano_bruto)
                focus_por_ano[ano] = _validar_taxa(
                    taxa_bruta,
                    f"Focus SELIC {ano}",
                    minimo=0.0,
                    maximo=1.0,
                )
            except (TypeError, ValueError) as exc:
                logger.warning(f"Ponto da curva Focus ignorado: {exc}")
    elif focus_raw is not None:
        logger.warning(
            "Curva Focus retornou formato inválido: %r",
            type(focus_raw).__name__,
        )

    focus_por_ano = dict(sorted(focus_por_ano.items()))
    focus_value = next(iter(focus_por_ano.values()), None)

    extras = _extras_opcionais(results)

    if failures:
        cache_stale_aceitavel = (
            allow_stale_cache
            and cached_data is not None
            and cache_age is not None
            and cache_age <= STALE_CACHE_MAX_AGE_SECONDS
        )
        if cache_stale_aceitavel:
            logger.warning(
                "Atualização incompleta; usando cache real anterior: %s",
                failures,
            )
            return _cache_antigo_com_aviso(
                cached_data,
                cache_age,
                failures,
            )

        campos = ", ".join(sorted(failures))
        detalhes = "; ".join(
            f"{key}: {message}" for key, message in sorted(failures.items())
        )
        raise DadosIndisponiveisError(
            f"Indicadores obrigatórios ({campos})",
            detalhes,
        )

    # `failures` vazio garante que esses valores foram preenchidos e validados.
    assert selic_value is not None
    assert ipca_value is not None

    fontes = [
        (
            f"SELIC {formatar_pct(selic_value)} a.a. — "
            f"BCB/SGS série {SGS_SELIC} (ref. {selic_ref})"
        ),
        (
            f"IPCA 12m {formatar_pct(ipca_value)} a.a. — "
            f"BCB/SGS série {SGS_IPCA_12M} (ref. {ipca_ref})"
        ),
    ]
    avisos: list[str] = []
    if ibov_value is not None:
        fontes.append(
            f"Ibovespa CAGR 10a {formatar_pct(ibov_value)} a.a. — Yahoo Finance/yfinance"
        )
    if isinstance(ibov_vol, (int, float)):
        fontes.append(
            f"Volatilidade do Ibovespa (10 anos) {formatar_pct(ibov_vol)} a.a. — "
            "Yahoo Finance/yfinance"
        )
    else:
        ibov_vol = None
        avisos.append(
            "⚠️  Volatilidade do Ibovespa indisponível; o cenário pessimista de "
            "ações usa a regra simplificada."
        )

    if focus_por_ano:
        for ano, taxa in focus_por_ano.items():
            fontes.append(
                f"Previsão SELIC Focus {ano}: {formatar_pct(taxa)} a.a. — "
                "BCB/Olinda"
            )
    else:
        avisos.append(
            "⚠️  Focus SELIC indisponível; esse dado opcional não foi usado."
        )

    fontes.extend(extras.pop("_fontes"))
    avisos.extend(extras.pop("_avisos"))

    payload = {
        "_schema_version": CACHE_SCHEMA_VERSION,
        "selic": selic_value,
        "focus_selic": focus_value,
        "focus_selic_por_ano": focus_por_ano,
        "ipca": ipca_value,
        "ibov_cagr": ibov_value,
        "ibov_volatilidade": ibov_vol,
        # Mantido por compatibilidade: representa a referência da SELIC.
        "data_ref": selic_ref,
        "fontes": fontes,
        "avisos": avisos,
        "fetched_at": _utc_now_iso(),
        "cache_status": "fresh",
        **extras,
    }

    _save_market_cache(payload)
    return payload


__all__ = [
    "SGS_CDI_ANUAL",
    "SGS_IPCA_12M",
    "SGS_POUPANCA",
    "SGS_SELIC",
    "load_market_data",
]
