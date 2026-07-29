"""
Motor de análise e score para ETFs negociados na B3.

Fontes:
- BRAPI /api/v2/tickers: descoberta dos tickers de ETFs.
- Yahoo Finance/yfinance: histórico de preços, volume e metadados opcionais.

Dados ausentes nunca são substituídos por valores inventados. Quando a taxa
de administração não está disponível, ela permanece como ``None`` e seu peso
é retirado do cálculo do score.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from typing import Dict, List

import numpy as np
import requests
import yfinance as yf

from utils.exceptions import DadosIndisponiveisError
from utils.logging_config import get_logger

logger = get_logger(__name__)


REF_ETF = {
    "retorno_12m": {"bom": 30.0, "ruim": -10.0},
    "volatilidade": {"bom": 10.0, "ruim": 40.0},
    "sharpe": {"bom": 1.5, "ruim": -0.5},
    "taxa": {"bom": 0.20, "ruim": 1.0},
    "volume": {"bom": 50_000_000, "ruim": 1_000_000},
}

PESOS_ETF = {
    1: {
        "retorno_12m": 0.25,
        "volatilidade": 0.30,
        "sharpe": 0.20,
        "taxa": 0.15,
        "volume": 0.10,
    },
    2: {
        "retorno_12m": 0.30,
        "volatilidade": 0.20,
        "sharpe": 0.25,
        "taxa": 0.15,
        "volume": 0.10,
    },
    3: {
        "retorno_12m": 0.40,
        "volatilidade": 0.10,
        "sharpe": 0.25,
        "taxa": 0.10,
        "volume": 0.15,
    },
}

_CACHE_ETFS: List[str] | None = None
_CACHE_TIMESTAMP = 0.0
_CACHE_TTL = 3600

_CACHE_DADOS_ETF: Dict[tuple[str, str], tuple[float, Dict]] = {}
_CACHE_DADOS_ETF_TTL = 3600
_CACHE_DADOS_LOCK = Lock()

MAX_WORKERS_ETF = 6


def norm(valor: float, bom: float, ruim: float) -> float:
    """Normaliza um indicador entre zero e um."""
    if abs(bom - ruim) < 1e-9:
        return 0.5
    return max(0.0, min(1.0, (valor - ruim) / (bom - ruim)))


def _get_etfs_from_brapi() -> List[str]:
    """
    Obtém a lista de ETFs da BRAPI.

    A função consulta todas as páginas públicas e mantém somente registros
    identificados pela API como ETF.
    """
    base_url = "https://brapi.dev/api/v2/tickers"
    etfs: List[str] = []
    page = 1
    limit = 200
    total_pages = None

    while True:
        try:
            response = requests.get(
                base_url,
                params={"limit": limit, "page": page},
                timeout=10,
                headers={"User-Agent": "arvore-de-investimentos/1.0"},
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            logger.warning(
                "BRAPI /api/v2/tickers falhou na página %s: %s",
                page,
                exc,
            )
            break

        pagination = data.get("pagination", {})

        if total_pages is None:
            total_pages = pagination.get("totalPages", 0)
            logger.info("BRAPI tickers: %s páginas.", total_pages)

        for item in data.get("results", []):
            if str(item.get("subType", "")).lower() != "etf":
                continue

            symbol = str(item.get("symbol", "")).strip().upper()
            if symbol:
                etfs.append(symbol.replace(".SA", ""))

        if not pagination.get("hasNextPage", False):
            break

        page += 1
        time.sleep(0.3)

    # Remove duplicatas sem perder a ordem fornecida pela fonte.
    etfs_unicos = list(dict.fromkeys(etfs))
    logger.info(
        "BRAPI retornou %s ETFs públicos.",
        len(etfs_unicos),
    )
    return etfs_unicos


def get_all_etf_tickers() -> List[str]:
    """Retorna os tickers de ETF, usando cache por uma hora."""
    global _CACHE_ETFS, _CACHE_TIMESTAMP

    if (
        _CACHE_ETFS is not None
        and (time.time() - _CACHE_TIMESTAMP) < _CACHE_TTL
    ):
        return list(_CACHE_ETFS)

    try:
        etfs = _get_etfs_from_brapi()
    except Exception as exc:
        raise DadosIndisponiveisError(
            "Lista de ETFs (BRAPI /api/v2/tickers)",
            str(exc),
        ) from exc

    if not etfs:
        raise DadosIndisponiveisError(
            "Lista de ETFs (BRAPI /api/v2/tickers)",
            "API não retornou nenhum ETF no momento.",
        )

    _CACHE_ETFS = list(etfs)
    _CACHE_TIMESTAMP = time.time()
    return list(etfs)


def _ler_cache_dados(ticker: str, period: str) -> Dict | None:
    chave = (ticker, period)

    with _CACHE_DADOS_LOCK:
        item = _CACHE_DADOS_ETF.get(chave)

        if item is None:
            return None

        timestamp, dados = item
        if time.time() - timestamp >= _CACHE_DADOS_ETF_TTL:
            _CACHE_DADOS_ETF.pop(chave, None)
            return None

        return dict(dados)


def _salvar_cache_dados(
    ticker: str,
    period: str,
    dados: Dict,
) -> None:
    chave = (ticker, period)
    with _CACHE_DADOS_LOCK:
        _CACHE_DADOS_ETF[chave] = (time.time(), dict(dados))


def _taxa_percentual(info: Dict) -> float | None:
    """
    Converte a taxa informada pelo Yahoo para percentual.

    O Yahoo normalmente fornece ``annualReportExpenseRatio`` em formato
    decimal: 0.0025 representa 0,25%.
    """
    taxa_raw = info.get("annualReportExpenseRatio")
    if taxa_raw is None:
        return None

    try:
        taxa = float(taxa_raw)
    except (TypeError, ValueError):
        return None

    if not np.isfinite(taxa) or taxa < 0:
        return None

    if taxa <= 1:
        taxa *= 100

    return taxa


def get_etf_data(ticker: str, period: str = "1y") -> Dict:
    """
    Carrega e calcula indicadores de um ETF.

    A falta de metadados, incluindo taxa de administração e nome longo, não
    invalida o histórico de preços. Um dicionário vazio só é retornado quando
    não há dados suficientes para calcular as métricas obrigatórias.
    """
    ticker_limpo = str(ticker).strip().upper().replace(".SA", "")

    if not ticker_limpo:
        return {}

    cached = _ler_cache_dados(ticker_limpo, period)
    if cached is not None:
        return cached

    ticker_yf = f"{ticker_limpo}.SA"

    try:
        ticker_obj = yf.Ticker(ticker_yf)
        hist = ticker_obj.history(
            period=period,
            auto_adjust=True,
            actions=False,
        )

        if hist is None or hist.empty or len(hist) < 30:
            logger.warning(
                "ETF %s: histórico insuficiente (%s registros).",
                ticker_limpo,
                0 if hist is None else len(hist),
            )
            return {}

        if "Close" not in hist.columns or "Volume" not in hist.columns:
            logger.warning(
                "ETF %s: colunas Close/Volume indisponíveis.",
                ticker_limpo,
            )
            return {}

        prices = hist["Close"].dropna().astype(float)
        if len(prices) < 30:
            return {}

        retornos_diarios = prices.pct_change().dropna()
        if len(retornos_diarios) < 20:
            return {}

        retorno_12m = (
            float(prices.iloc[-1]) / float(prices.iloc[0]) - 1
        ) * 100

        vol_diaria = float(retornos_diarios.std())
        vol_anual = vol_diaria * float(np.sqrt(252)) * 100

        retorno_medio_anual = (
            (1 + float(retornos_diarios.mean())) ** 252
        ) - 1

        sharpe = (
            (retorno_medio_anual - 0.05) / (vol_anual / 100)
            if vol_anual > 0
            else 0.0
        )

        volumes = (
            hist["Volume"]
            .reindex(prices.index)
            .fillna(0)
            .astype(float)
        )
        volume_medio = float((volumes * prices).mean())

        # Metadados são opcionais e não devem invalidar as cotações.
        info: Dict = {}
        try:
            info = ticker_obj.get_info() or {}
        except Exception as exc:
            logger.debug(
                "ETF %s: metadados indisponíveis: %s",
                ticker_limpo,
                exc,
            )

        taxa = _taxa_percentual(info)

        resultado = {
            "retorno_12m": round(float(retorno_12m), 2),
            "volatilidade": round(float(vol_anual), 2),
            "sharpe": round(float(sharpe), 2),
            "volume": round(volume_medio, 0),
            "taxa": round(taxa, 2) if taxa is not None else None,
            "preco": round(float(prices.iloc[-1]), 2),
            "nome": info.get("longName") or ticker_limpo,
        }

        _salvar_cache_dados(ticker_limpo, period, resultado)
        return dict(resultado)

    except Exception as exc:
        logger.warning(
            "Erro ao carregar ETF %s: %s: %s",
            ticker_limpo,
            type(exc).__name__,
            exc,
        )
        return {}


def _score_etf(
    ind: Dict,
    perfil: int,
) -> tuple[float, List[str]]:
    """
    Calcula o score usando somente métricas disponíveis.

    Se uma métrica opcional estiver ausente, seu peso é retirado e os demais
    pesos são implicitamente renormalizados. Isso evita atribuir uma taxa
    fictícia ao ETF.
    """
    pesos = PESOS_ETF.get(perfil, PESOS_ETF[2])
    soma_ponderada = 0.0
    soma_pesos = 0.0

    for nome in (
        "retorno_12m",
        "volatilidade",
        "sharpe",
        "taxa",
        "volume",
    ):
        valor = ind.get(nome)
        if valor is None:
            continue

        referencia = REF_ETF[nome]
        peso = pesos[nome]
        nota = norm(
            float(valor),
            referencia["bom"],
            referencia["ruim"],
        )

        soma_ponderada += peso * nota
        soma_pesos += peso

    score = (
        soma_ponderada / soma_pesos
        if soma_pesos > 0
        else 0.0
    )

    motivos: List[str] = []
    retorno = ind.get("retorno_12m")
    volatilidade = ind.get("volatilidade")
    sharpe = ind.get("sharpe")
    taxa = ind.get("taxa")
    volume = ind.get("volume")

    if retorno is not None:
        motivos.append(f"Retorno em 12 meses: {retorno:.1f}%")

    if volatilidade is not None:
        motivos.append(
            f"Volatilidade anual: {volatilidade:.1f}%"
        )

    if sharpe is not None:
        motivos.append(f"Índice de Sharpe: {sharpe:.2f}")

    if taxa is not None:
        motivos.append(
            f"Taxa de administração: {taxa:.2f}%"
        )
    else:
        motivos.append(
            "Taxa de administração indisponível; "
            "critério não usado no score."
        )

    if volume is not None:
        motivos.append(
            "Volume financeiro médio: "
            f"R$ {volume / 1e6:.1f} milhões/dia"
        )

    return round(score * 100, 1), motivos[:5]


def top_etfs(perfil: int, n: int = 5) -> List[Dict]:
    """Calcula e retorna os ETFs com maior score para o perfil."""
    if n <= 0:
        return []

    tickers = get_all_etf_tickers()
    if not tickers:
        return []

    dados_por_ticker: Dict[str, Dict] = {}
    max_workers = min(MAX_WORKERS_ETF, len(tickers))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(get_etf_data, ticker): ticker
            for ticker in tickers
        }

        for future in as_completed(futures):
            ticker = futures[future]
            try:
                dados = future.result()
            except Exception as exc:
                logger.warning(
                    "Falha inesperada ao analisar ETF %s: %s",
                    ticker,
                    exc,
                )
                continue

            if dados:
                dados_por_ticker[ticker] = dados

    resultados: List[Dict] = []

    for ticker, dados_originais in dados_por_ticker.items():
        dados = dict(dados_originais)
        ticker_limpo = ticker.replace(".SA", "")
        score, motivos = _score_etf(dados, perfil)

        resultados.append(
            {
                "ticker": ticker_limpo,
                "nome": dados.get("nome") or ticker_limpo,
                "preco": dados.get("preco"),
                "score": score,
                "motivos": motivos,
                "retorno_12m": dados.get("retorno_12m"),
                "volatilidade": dados.get("volatilidade"),
                "sharpe": dados.get("sharpe"),
                "taxa": dados.get("taxa"),
                "volume": dados.get("volume"),
            }
        )

    return sorted(
        resultados,
        key=lambda item: (-item["score"], item["ticker"]),
    )[:n]