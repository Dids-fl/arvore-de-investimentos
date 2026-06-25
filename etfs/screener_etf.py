"""
Motor de score para ETFs usando BRAPI /api/v2/tickers (subType='etf').
Otimizado: pré-filtra por liquidez e pré-seleciona os melhores antes de baixar dados detalhados.
"""

import time
import requests
import yfinance as yf
import numpy as np
from typing import List, Dict, Optional

from utils.logging_config import get_logger
from acoes_fiis.apis.brapi import BrapiClient

logger = get_logger(__name__)

# ── Configurações ─────────────────────────────────────────────────────────────
LIQUIDEZ_MINIMA = 1_000_000  # R$ 1M/dia (exclui ETFs ilíquidos)
PRE_SELECT_N = 30             # Número de ETFs a avaliar detalhadamente
CACHE_TTL = 3600              # 1 hora

# ── Taxas de administração conhecidas (fallback) ─────────────────────────────
TAXAS_ADMIN_FALLBACK = {
    "BOVA11": 0.30,
    "BOVV11": 0.05,
    "IVVB11": 0.24,
    "SMAL11": 0.40,
    "HASH11": 0.50,
    "BITH11": 0.50,
    "USDB11": 0.20,
    "DIVO11": 0.30,
    "GOLD11": 0.40,
    "META11": 0.40,
    "NASD11": 0.30,
    "SPXI11": 0.30,
    "PIBB11": 0.30,
    "XFIX11": 0.40,
}
TAXA_PADRAO = 0.50

_FALLBACK_ETFs = list(TAXAS_ADMIN_FALLBACK.keys())

REF_ETF = {
    "retorno_12m": {"bom": 30.0, "ruim": -10.0},
    "volatilidade": {"bom": 10.0, "ruim": 40.0},
    "sharpe": {"bom": 1.5, "ruim": -0.5},
    "taxa": {"bom": 0.20, "ruim": 1.0},
    "volume": {"bom": 50_000_000, "ruim": 1_000_000},
}

PESOS_ETF = {
    1: {"retorno_12m": 0.25, "volatilidade": 0.30, "sharpe": 0.20, "taxa": 0.15, "volume": 0.10},
    2: {"retorno_12m": 0.30, "volatilidade": 0.20, "sharpe": 0.25, "taxa": 0.15, "volume": 0.10},
    3: {"retorno_12m": 0.40, "volatilidade": 0.10, "sharpe": 0.25, "taxa": 0.10, "volume": 0.15},
}

_CACHE_ETFS = None
_CACHE_TIMESTAMP = 0

def norm(valor: float, bom: float, ruim: float) -> float:
    if abs(bom - ruim) < 1e-9:
        return 0.5
    return max(0.0, min(1.0, (valor - ruim) / (bom - ruim)))

def _get_etf_list_from_brapi(client: BrapiClient) -> List[Dict]:
    """
    Obtém lista de ETFs da BRAPI com dados básicos (preço, volume, etc.).
    Retorna lista de dicts com ticker, nome, preço, volume, etc.
    """
    token = client.token
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    base_url = "https://brapi.dev/api/v2/tickers"
    etfs = []
    page = 1
    total_pages = None
    limit = 200

    while True:
        url = f"{base_url}?limit={limit}&page={page}"
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            logger.warning(f"BRAPI falhou na página {page}: {e}")
            break

        if total_pages is None:
            total_pages = data.get("pagination", {}).get("totalPages", 0)
            logger.info(f"BRAPI tickers: {total_pages} páginas.")

        for item in data.get("results", []):
            if item.get("subType") == "etf":
                symbol = item.get("symbol")
                if not symbol:
                    continue
                quote = item.get("quote", {})
                etf_info = {
                    "ticker": symbol.upper(),
                    "nome": item.get("name", ""),
                    "preco": quote.get("lastPrice", 0),
                    "volume": quote.get("volume", 0) * (quote.get("lastPrice", 1) or 1),
                    "retorno_12m": item.get("ret", {}).get("pct12m", 0),
                }
                etfs.append(etf_info)

        if not data.get("pagination", {}).get("hasNextPage", False):
            break

        page += 1
        time.sleep(0.3)

    logger.info(f"BRAPI retornou {len(etfs)} ETFs com dados básicos.")
    return etfs

def get_all_etf_tickers() -> List[str]:
    """Retorna lista de tickers de ETFs (com cache)."""
    global _CACHE_ETFS, _CACHE_TIMESTAMP

    if _CACHE_ETFS is not None and (time.time() - _CACHE_TIMESTAMP) < CACHE_TTL:
        return _CACHE_ETFS

    try:
        client = BrapiClient()
        etfs_info = _get_etf_list_from_brapi(client)
        if not etfs_info:
            raise ValueError("Nenhum ETF retornado pela BRAPI.")

        # 1. Filtra por liquidez mínima
        etfs_filtrados = [e for e in etfs_info if e.get("volume", 0) >= LIQUIDEZ_MINIMA]
        logger.info(f"Após filtro de liquidez ({LIQUIDEZ_MINIMA}): {len(etfs_filtrados)} ETFs.")

        # 2. Pré-seleciona os top N por retorno 12m (se disponível)
        etfs_ordenados = sorted(etfs_filtrados, key=lambda x: -x.get("retorno_12m", 0))
        etfs_pre = etfs_ordenados[:PRE_SELECT_N]
        logger.info(f"Pré-selecionados {len(etfs_pre)} ETFs para análise detalhada.")

        tickers = [e["ticker"] for e in etfs_pre]

        _CACHE_ETFS = tickers
        _CACHE_TIMESTAMP = time.time()
        return tickers

    except Exception as e:
        logger.warning(f"Falha ao obter ETFs via BRAPI: {e}")

    # Fallback
    logger.warning("Usando lista fixa de ETFs (fallback).")
    _CACHE_ETFS = _FALLBACK_ETFs
    _CACHE_TIMESTAMP = time.time()
    return _FALLBACK_ETFs

def get_etf_data(ticker: str, period: str = "1y") -> Dict:
    """Baixa dados detalhados de um ETF via yfinance."""
    try:
        ticker_yf = ticker if ticker.endswith(".SA") else ticker + ".SA"
        ticker_obj = yf.Ticker(ticker_yf)
        info = ticker_obj.info

        hist = ticker_obj.history(period=period)
        if hist.empty or len(hist) < 30:
            return {}

        prices = hist['Close']
        retorno_12m = (prices.iloc[-1] / prices.iloc[0] - 1) * 100
        retornos_diarios = prices.pct_change().dropna()
        if len(retornos_diarios) < 20:
            return {}

        vol_diaria = retornos_diarios.std()
        vol_anual = vol_diaria * np.sqrt(252) * 100
        retorno_medio_anual = (1 + retornos_diarios.mean()) ** 252 - 1
        sharpe = (retorno_medio_anual - 0.05) / (vol_anual / 100) if vol_anual > 0 else 0

        volume_medio = hist['Volume'].mean() * prices.iloc[-1]

        taxa = info.get("annualReportExpenseRatio")
        if taxa is None:
            ticker_clean = ticker.replace(".SA", "")
            taxa = TAXAS_ADMIN_FALLBACK.get(ticker_clean, TAXA_PADRAO)
        else:
            taxa = taxa * 100

        return {
            "retorno_12m": round(retorno_12m, 2),
            "volatilidade": round(vol_anual, 2),
            "sharpe": round(sharpe, 2),
            "volume": round(volume_medio, 0),
            "taxa": round(taxa, 2),
            "preco": round(prices.iloc[-1], 2),
            "nome": info.get("longName", ticker),
        }
    except Exception as e:
        logger.debug(f"Erro no ETF {ticker}: {e}")
        return {}

def _score_etf(ind: Dict, perfil: int) -> tuple[float, List[str]]:
    pesos = PESOS_ETF.get(perfil, PESOS_ETF[2])
    score = 0.0
    motivos = []

    ret = ind.get("retorno_12m", 0)
    score += pesos["retorno_12m"] * norm(ret, REF_ETF["retorno_12m"]["bom"], REF_ETF["retorno_12m"]["ruim"])
    motivos.append(f"{'✅' if ret > 20 else 'ℹ️' if ret > 10 else '⚠️'} Retorno 12m: {ret:.1f}%")

    vol = ind.get("volatilidade", 0)
    score += pesos["volatilidade"] * norm(vol, REF_ETF["volatilidade"]["bom"], REF_ETF["volatilidade"]["ruim"])
    motivos.append(f"{'✅' if vol < 15 else 'ℹ️' if vol < 25 else '⚠️'} Volatilidade: {vol:.1f}%")

    sharpe = ind.get("sharpe", 0)
    score += pesos["sharpe"] * norm(sharpe, REF_ETF["sharpe"]["bom"], REF_ETF["sharpe"]["ruim"])
    motivos.append(f"{'✅' if sharpe > 1.0 else 'ℹ️' if sharpe > 0.5 else '⚠️'} Sharpe: {sharpe:.2f}")

    taxa = ind.get("taxa", 0.5)
    score += pesos["taxa"] * norm(taxa, REF_ETF["taxa"]["bom"], REF_ETF["taxa"]["ruim"])
    motivos.append(f"{'✅' if taxa < 0.30 else 'ℹ️' if taxa < 0.50 else '⚠️'} Taxa admin: {taxa:.2f}%")

    volume = ind.get("volume", 0)
    score += pesos["volume"] * norm(volume, REF_ETF["volume"]["bom"], REF_ETF["volume"]["ruim"])
    motivos.append(f"{'✅' if volume > 10_000_000 else 'ℹ️'} Volume: R$ {volume/1e6:.1f}M/dia")

    return round(score * 100, 1), motivos[:5]

def top_etfs(perfil: int, n: int = 5) -> List[Dict]:
    tickers = get_all_etf_tickers()
    resultados = []
    for ticker in tickers:
        dados = get_etf_data(ticker)
        if not dados:
            continue
        dados["ticker"] = ticker.replace(".SA", "")
        score, motivos = _score_etf(dados, perfil)
        resultados.append({
            "ticker": dados["ticker"],
            "nome": dados.get("nome", dados["ticker"]),
            "preco": dados.get("preco", 0),
            "score": score,
            "motivos": motivos,
            "retorno_12m": dados.get("retorno_12m", 0),
            "volatilidade": dados.get("volatilidade", 0),
            "sharpe": dados.get("sharpe", 0),
            "taxa": dados.get("taxa", 0),
            "volume": dados.get("volume", 0),
        })
    return sorted(resultados, key=lambda x: -x["score"])[:n]