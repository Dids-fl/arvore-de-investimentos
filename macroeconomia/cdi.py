"""Obtenção do CDI oficial com cache e contenção de falhas da API SGS."""

from __future__ import annotations

import json
import logging
import math
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests
from bcb import sgs
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

SERIE_CDI_DIARIO = 12
SERIE_CDI_MENSAL = 4391
DIAS_UTEIS_ANO = 252

_CACHE_FILE = (
    Path.home()
    / ".cache"
    / "recomendador_investimentos"
    / "cdi_periodos.json"
)
_CACHE_TTL_SECONDS = 24 * 60 * 60
_CACHE_HISTORICO_TTL_SECONDS = 30 * 24 * 60 * 60
_CIRCUIT_BREAKER_SECONDS = 5 * 60
_LOCK = threading.Lock()
_MEMORIA: dict[str, float] = {}
_CIRCUITO_ABERTO_ATE = 0.0

_HTTP = requests.Session()
_retry = Retry(
    total=2,
    connect=2,
    read=2,
    backoff_factor=0.5,
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=frozenset({"GET"}),
)
_HTTP.mount("https://", HTTPAdapter(max_retries=_retry))


def _chave_periodo(data_inicio: str, data_fim: str) -> str:
    return f"{data_inicio}:{data_fim}"


def _carregar_cache() -> dict:
    try:
        if not _CACHE_FILE.exists():
            return {"periodos": {}}
        payload = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return {"periodos": {}}
        periodos = payload.get("periodos")
        if not isinstance(periodos, dict):
            return {"periodos": {}}
        return payload
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        logger.warning("Cache de CDI inválido; será reconstruído: %s", exc)
        return {"periodos": {}}


def _salvar_cache(payload: dict) -> None:
    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        temporario = _CACHE_FILE.with_suffix(".tmp")
        temporario.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporario.replace(_CACHE_FILE)
    except OSError as exc:
        logger.warning("Não foi possível salvar o cache de CDI: %s", exc)


def _ler_periodo_cache(
    chave: str,
    *,
    aceitar_expirado: bool = False,
) -> float | None:
    payload = _carregar_cache()
    registro = payload.get("periodos", {}).get(chave)
    if not isinstance(registro, dict):
        return None
    try:
        valor = float(registro["valor"])
        armazenado_em = float(registro["armazenado_em"])
    except (KeyError, TypeError, ValueError):
        return None
    if not math.isfinite(valor) or valor <= -1:
        return None
    if aceitar_expirado:
        return valor
    data_fim = date.fromisoformat(chave.split(":", maxsplit=1)[1])
    ttl = (
        _CACHE_HISTORICO_TTL_SECONDS
        if data_fim
        < datetime.now(timezone.utc).date() - timedelta(days=7)
        else _CACHE_TTL_SECONDS
    )
    if time.time() - armazenado_em > ttl:
        return None
    return valor


def _gravar_periodo_cache(chave: str, valor: float) -> None:
    payload = _carregar_cache()
    payload.setdefault("periodos", {})[chave] = {
        "valor": valor,
        "armazenado_em": time.time(),
    }
    _salvar_cache(payload)


def _anualizar_valores_percentuais(valores) -> float | None:
    serie = valores.dropna()
    if serie.empty:
        return None
    fator_acumulado = (1 + serie.astype(float) / 100).prod()
    dias_uteis = len(serie)
    if dias_uteis == 0 or fator_acumulado <= 0:
        return None
    return float(fator_acumulado ** (DIAS_UTEIS_ANO / dias_uteis) - 1)


def _buscar_cdi_python_bcb(data_inicio: str, data_fim: str) -> float | None:
    dataframe = sgs.get(
        {"cdi_diario": SERIE_CDI_DIARIO},
        start=data_inicio,
        end=data_fim,
    )
    if dataframe.empty:
        return None
    return _anualizar_valores_percentuais(dataframe.iloc[:, 0])


def _buscar_cdi_http(data_inicio: str, data_fim: str) -> float | None:
    url = (
        "https://api.bcb.gov.br/dados/serie/"
        f"bcdata.sgs.{SERIE_CDI_DIARIO}/dados"
    )
    resposta = _HTTP.get(
        url,
        params={
            "formato": "json",
            "dataInicial": date.fromisoformat(data_inicio).strftime(
                "%d/%m/%Y"
            ),
            "dataFinal": date.fromisoformat(data_fim).strftime("%d/%m/%Y"),
        },
        headers={"User-Agent": "recomendador-investimentos/1.0"},
        timeout=20,
    )
    resposta.raise_for_status()
    dados = resposta.json()
    if not isinstance(dados, list):
        return None

    valores = pd.Series(
        [
            str(item.get("valor", "")).replace(",", ".")
            for item in dados
            if isinstance(item, dict)
        ],
        dtype="object",
    )
    valores = pd.to_numeric(valores, errors="coerce")
    return _anualizar_valores_percentuais(valores)


def _buscar_cdi_online(data_inicio: str, data_fim: str) -> float | None:
    erros: list[str] = []
    try:
        valor = _buscar_cdi_python_bcb(data_inicio, data_fim)
        if valor is not None:
            return valor
        erros.append("python-bcb retornou série vazia")
    except Exception as exc:  # noqa: BLE001
        erros.append(f"python-bcb: {type(exc).__name__}: {exc}")

    try:
        valor = _buscar_cdi_http(data_inicio, data_fim)
        if valor is not None:
            return valor
        erros.append("API SGS direta retornou série vazia")
    except (requests.RequestException, ValueError, TypeError) as exc:
        erros.append(f"API SGS direta: {type(exc).__name__}: {exc}")

    logger.warning(
        "CDI indisponível para %s a %s (%s).",
        data_inicio,
        data_fim,
        "; ".join(erros),
    )
    return None


def obter_cdi_diario(data: str | None = None) -> float | None:
    """Retorna a taxa diária em decimal para a data ou último dia útil."""
    try:
        data = data or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        dataframe = sgs.get(
            {"cdi_diario": SERIE_CDI_DIARIO},
            start=data,
            end=data,
        )
        if dataframe.empty:
            dataframe = sgs.get({"cdi_diario": SERIE_CDI_DIARIO}, end=data)
        if dataframe.empty:
            return None
        return float(dataframe.iloc[-1, 0]) / 100
    except Exception as exc:  # noqa: BLE001
        logger.warning("Erro ao buscar CDI diário: %s", exc)
        return None


def obter_cdi_mensal(ano: int, mes: int) -> float | None:
    """Retorna o CDI acumulado mensal em decimal."""
    if not 1 <= mes <= 12:
        raise ValueError("mes deve estar entre 1 e 12.")
    inicio = date(ano, mes, 1)
    proximo_mes = date(ano + (mes == 12), mes % 12 + 1, 1)
    fim = proximo_mes - timedelta(days=1)
    try:
        dataframe = sgs.get(
            {"cdi_mensal": SERIE_CDI_MENSAL},
            start=inicio.isoformat(),
            end=fim.isoformat(),
        )
        if dataframe.empty:
            return None
        return float(dataframe.iloc[-1, 0]) / 100
    except Exception as exc:  # noqa: BLE001
        logger.warning("Erro ao buscar CDI mensal: %s", exc)
        return None


def obter_cdi_periodo(data_inicio: str, data_fim: str) -> float | None:
    """Retorna o CDI anualizado e consulta a rede no máximo uma vez."""
    global _CIRCUITO_ABERTO_ATE

    inicio = date.fromisoformat(data_inicio)
    fim = date.fromisoformat(data_fim)
    if inicio >= fim:
        logger.warning("Data de início deve ser anterior à data de fim.")
        return None

    chave = _chave_periodo(data_inicio, data_fim)
    with _LOCK:
        if chave in _MEMORIA:
            return _MEMORIA[chave]
        valor_cache = _ler_periodo_cache(chave)
        if valor_cache is not None:
            _MEMORIA[chave] = valor_cache
            return valor_cache
        circuito_aberto = time.monotonic() < _CIRCUITO_ABERTO_ATE

    if circuito_aberto:
        return _ler_periodo_cache(chave, aceitar_expirado=True)

    valor = _buscar_cdi_online(data_inicio, data_fim)
    if valor is None:
        with _LOCK:
            _CIRCUITO_ABERTO_ATE = (
                time.monotonic() + _CIRCUIT_BREAKER_SECONDS
            )
        antigo = _ler_periodo_cache(chave, aceitar_expirado=True)
        if antigo is not None:
            logger.warning("Usando CDI expirado em cache após falha da fonte.")
        return antigo

    with _LOCK:
        _MEMORIA[chave] = valor
        _CIRCUITO_ABERTO_ATE = 0.0
        _gravar_periodo_cache(chave, valor)
    return valor


def obter_cdi_anualizado() -> float | None:
    """Retorna o CDI equivalente anual calculado nos últimos 12 meses."""
    hoje = datetime.now(timezone.utc)
    inicio = hoje - timedelta(days=365)
    return obter_cdi_periodo(
        inicio.strftime("%Y-%m-%d"),
        hoje.strftime("%Y-%m-%d"),
    )


def limpar_cache_memoria() -> None:
    """Limpa estado em memória; destinada a testes e atualização forçada."""
    global _CIRCUITO_ABERTO_ATE
    with _LOCK:
        _MEMORIA.clear()
        _CIRCUITO_ABERTO_ATE = 0.0
