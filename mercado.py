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
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import MAX_RETRIES, REQUEST_TIMEOUT, RETRY_BACKOFF
from utils.exceptions import DadosIndisponiveisError
from utils.logging_config import get_logger

logger = get_logger(__name__)

# ── Configuração ──────────────────────────────────────────────────────────────

CACHE_FILE = (
    Path.home() / ".cache" / "recomendador_investimentos_market.json"
)
CACHE_TTL_SECONDS = 6 * 60 * 60
STALE_CACHE_MAX_AGE_SECONDS = 7 * 24 * 60 * 60

# A versão 2 invalida caches criados pela implementação antiga, que percorria
# os pontos do SGS do mais antigo para o mais recente.
CACHE_SCHEMA_VERSION = 2

SGS_SELIC = 432
SGS_IPCA_12M = 13522

_SGS_URL = (
    "https://api.bcb.gov.br/dados/serie/"
    "bcdata.sgs.{serie}/dados/ultimos/5"
)
_FOCUS_URL = (
    "https://olinda.bcb.gov.br/olinda/servico/"
    "Expectativas/versao/v1/odata/ExpectativaMercadoAnuais"
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


# ── Funções auxiliares ────────────────────────────────────────────────────────

def _utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _json_get(
    url: str,
    *,
    params: Optional[dict[str, Any]] = None,
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
    except (TypeError, ValueError):
        return False

    return (
        isinstance(data["data_ref"], str)
        and bool(data["data_ref"].strip())
        and isinstance(data["fontes"], list)
        and isinstance(data["avisos"], list)
        and isinstance(data["fetched_at"], str)
    )


def _read_market_cache() -> tuple[Optional[dict], Optional[float]]:
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
) -> Optional[dict]:
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
    temp_path: Optional[Path] = None
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

def _fetch_sgs_value(serie: int) -> Tuple[float, str]:
    data = _json_get(
        _SGS_URL.format(serie=serie),
        params={"formato": "json"},
    )
    if not isinstance(data, list) or not data:
        raise RuntimeError(f"SGS série {serie}: resposta vazia ou inesperada.")

    # O SGS devolve os registros em ordem cronológica. Percorrer ao contrário
    # garante que seja escolhido o ponto válido mais recente.
    for item in reversed(data):
        if not isinstance(item, dict):
            continue

        raw = str(item.get("valor", "")).strip()
        data_ref = str(item.get("data", "")).strip()
        if not raw or not data_ref:
            continue

        try:
            value = float(raw.replace(",", ".")) / 100.0
        except (TypeError, ValueError):
            continue

        if math.isfinite(value):
            return value, data_ref

    raise RuntimeError(f"SGS série {serie}: nenhum valor válido.")


def _fetch_focus_selic() -> Optional[float]:
    ano_atual = dt.date.today().year

    # Se o ano corrente não estiver disponível, a expectativa do próximo ano
    # ainda é mais útil que um valor referente a um ano já encerrado.
    for ano_referencia in (ano_atual, ano_atual + 1):
        try:
            data = _json_get(
                _FOCUS_URL,
                params={
                    "$filter": (
                        "Indicador eq 'Selic' and "
                        f"DataReferencia eq '{ano_referencia}'"
                    ),
                    "$orderby": "Data desc",
                    "$top": 1,
                    "$format": "json",
                    "$select": "Mediana",
                },
            )
            values = data.get("value", []) if isinstance(data, dict) else []
            if not values:
                continue

            mediana = _validar_taxa(
                float(values[0]["Mediana"]) / 100.0,
                f"Focus SELIC {ano_referencia}",
                minimo=0.0,
                maximo=1.0,
            )
            return mediana
        except (
            KeyError,
            TypeError,
            ValueError,
            requests.exceptions.RequestException,
        ) as exc:
            logger.warning(
                "Erro ao buscar Focus SELIC para %s: %s",
                ano_referencia,
                exc,
            )
        except Exception as exc:
            logger.warning(
                "Resposta inesperada do Focus SELIC para %s: %s",
                ano_referencia,
                exc,
            )

    return None


def _fetch_ibov_cagr_10a() -> Optional[float]:
    if yf is None:
        return None

    try:
        history = yf.Ticker("^BVSP").history(
            period="10y",
            interval="1d",
            auto_adjust=False,
            actions=False,
        )
        if history is None or "Close" not in history:
            return None

        closes = history["Close"].dropna()
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
    except Exception as exc:
        logger.warning(f"Erro ao buscar histórico do Ibovespa: {exc}")
        return None


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
        "selic": lambda: _fetch_sgs_value(SGS_SELIC),
        "ipca": lambda: _fetch_sgs_value(SGS_IPCA_12M),
        "focus_selic": _fetch_focus_selic,
        "ibov_cagr": _fetch_ibov_cagr_10a,
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
                if value is None and key != "focus_selic":
                    failures[key] = "fonte sem valor válido"
            except Exception as exc:
                logger.warning(f"Falha ao obter {key}: {exc}")
                results[key] = None
                if key != "focus_selic":
                    failures[key] = str(exc)

    selic_raw = results.get("selic")
    ipca_raw = results.get("ipca")
    focus_value = results.get("focus_selic")
    ibov_raw = results.get("ibov_cagr")

    selic_value: Optional[float] = None
    ipca_value: Optional[float] = None
    ibov_value: Optional[float] = None
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
        if ibov_raw is None:
            raise ValueError(
                "yfinance ausente, histórico insuficiente ou fonte indisponível"
            )
        ibov_value = _validar_taxa(
            ibov_raw,
            "CAGR do Ibovespa",
            minimo=-0.90,
            maximo=2.0,
        )
    except (TypeError, ValueError) as exc:
        failures["ibov_cagr"] = str(exc)

    if focus_value is not None:
        try:
            focus_value = _validar_taxa(
                focus_value,
                "Focus SELIC",
                minimo=0.0,
                maximo=1.0,
            )
        except (TypeError, ValueError) as exc:
            logger.warning(f"Focus SELIC inválido: {exc}")
            focus_value = None

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
    assert ibov_value is not None

    fontes = [
        (
            f"SELIC {selic_value * 100:.2f}% a.a. — "
            f"BCB/SGS série {SGS_SELIC} (ref. {selic_ref})"
        ),
        (
            f"IPCA 12m {ipca_value * 100:.2f}% a.a. — "
            f"BCB/SGS série {SGS_IPCA_12M} (ref. {ipca_ref})"
        ),
        (
            f"Ibovespa CAGR 10a {ibov_value * 100:.2f}% a.a. — "
            "Yahoo Finance/yfinance"
        ),
    ]
    avisos: list[str] = []

    if focus_value is not None:
        fontes.append(
            f"Previsão SELIC Focus {focus_value * 100:.2f}% a.a. — "
            "BCB/Olinda"
        )
    else:
        avisos.append(
            "⚠️  Focus SELIC indisponível; esse dado opcional não foi usado."
        )

    payload = {
        "_schema_version": CACHE_SCHEMA_VERSION,
        "selic": selic_value,
        "focus_selic": focus_value,
        "ipca": ipca_value,
        "ibov_cagr": ibov_value,
        # Mantido por compatibilidade: representa a referência da SELIC.
        "data_ref": selic_ref,
        "fontes": fontes,
        "avisos": avisos,
        "fetched_at": _utc_now_iso(),
        "cache_status": "fresh",
    }

    _save_market_cache(payload)
    return payload


__all__ = ["load_market_data"]