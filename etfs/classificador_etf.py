"""
Classificador de ETFs: dado uma lista de tickers e um perfil,
retorna os top N ETFs com score e motivos.
"""

import yfinance as yf
import numpy as np
from typing import List, Dict, Optional

from utils.logging_config import get_logger

logger = get_logger(__name__)

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

def norm(valor: float, bom: float, ruim: float) -> float:
    """Normaliza valor entre 0 e 1 onde bom=1.0 e ruim=0.0."""
    if abs(bom - ruim) < 1e-9:
        return 0.5
    return max(0.0, min(1.0, (valor - ruim) / (bom - ruim)))

def get_etf_data(ticker: str, period: str = "1y") -> Dict:
    """
    Obtém dados de um ETF via yfinance.
    Retorna dict com métricas relevantes.
    """
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
        logger.debug(f"Erro ao obter dados do ETF {ticker}: {e}")
        return {}

def calcular_score_etf(dados: Dict, perfil: int) -> tuple[float, List[str]]:
    """
    Calcula o score de um ETF com base nos pesos do perfil.
    Retorna (score, motivos).
    """
    pesos = PESOS_ETF.get(perfil, PESOS_ETF[2])
    score = 0.0
    motivos = []

    ret = dados.get("retorno_12m", 0)
    score += pesos["retorno_12m"] * norm(ret, REF_ETF["retorno_12m"]["bom"], REF_ETF["retorno_12m"]["ruim"])
    motivos.append(f"{'✅' if ret > 20 else 'ℹ️' if ret > 10 else '⚠️'} Retorno 12m: {ret:.1f}%")

    vol = dados.get("volatilidade", 0)
    score += pesos["volatilidade"] * norm(vol, REF_ETF["volatilidade"]["bom"], REF_ETF["volatilidade"]["ruim"])
    motivos.append(f"{'✅' if vol < 15 else 'ℹ️' if vol < 25 else '⚠️'} Volatilidade: {vol:.1f}%")

    sharpe = dados.get("sharpe", 0)
    score += pesos["sharpe"] * norm(sharpe, REF_ETF["sharpe"]["bom"], REF_ETF["sharpe"]["ruim"])
    motivos.append(f"{'✅' if sharpe > 1.0 else 'ℹ️' if sharpe > 0.5 else '⚠️'} Sharpe: {sharpe:.2f}")

    taxa = dados.get("taxa", 0.5)
    score += pesos["taxa"] * norm(taxa, REF_ETF["taxa"]["bom"], REF_ETF["taxa"]["ruim"])
    motivos.append(f"{'✅' if taxa < 0.30 else 'ℹ️' if taxa < 0.50 else '⚠️'} Taxa admin: {taxa:.2f}%")

    volume = dados.get("volume", 0)
    score += pesos["volume"] * norm(volume, REF_ETF["volume"]["bom"], REF_ETF["volume"]["ruim"])
    motivos.append(f"{'✅' if volume > 10_000_000 else 'ℹ️'} Volume: R$ {volume/1e6:.1f}M/dia")

    return round(score * 100, 1), motivos

def rankear_etfs(tickers: List[str], perfil: int, n: int = 5) -> List[Dict]:
    """
    Recebe uma lista de tickers de ETFs, calcula scores e retorna os top N.
    """
    resultados = []
    for ticker in tickers:
        dados = get_etf_data(ticker)
        if not dados:
            continue
        dados["ticker"] = ticker.replace(".SA", "")
        score, motivos = calcular_score_etf(dados, perfil)
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