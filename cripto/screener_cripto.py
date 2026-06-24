"""
Motor de score para Criptomoedas.
Usa CoinGecko para obter dados de market cap, volume e retorno.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from .apis.coingecko import CoinGeckoClient
from acoes_fiis.ativos import PESOS_CRIPTO, REF_CRIPTO, CRIPTO_TOP_N
from utils.logging_config import get_logger

logger = get_logger(__name__)

# ── Normalização ──────────────────────────────────────────────────────────────

def norm(valor: float, bom: float, ruim: float) -> float:
    if abs(bom - ruim) < 1e-9:
        return 0.5
    return max(0.0, min(1.0, (valor - ruim) / (bom - ruim)))

# ── Score de cripto ───────────────────────────────────────────────────────────

def _score_cripto(ind: dict, perfil: int) -> tuple[float, list[str]]:
    pesos  = PESOS_CRIPTO[perfil]
    refs   = REF_CRIPTO
    score  = 0.0
    motivos: list[str] = []

    mc = float(ind.get("market_cap", 0) or 0)
    score += pesos["market_cap"] * norm(mc, refs["market_cap"]["bom"], refs["market_cap"]["ruim"])
    if perfil == 1:
        label = "✅" if mc > 500_000_000_000 else "ℹ️ "
        motivos.append(f"{label} Market cap: R${mc/1e9:.0f}B {'(reserva de valor)' if mc > 500_000_000_000 else ''}")
    else:
        motivos.append(f"Market cap: R${mc/1e9:.0f}B")

    vol = float(ind.get("volume", 0) or 0)
    score += pesos["volume"] * norm(vol, refs["volume"]["bom"], refs["volume"]["ruim"])

    ret = float(ind.get("retorno_12m", 0) or 0)
    score += pesos["retorno_12m"] * norm(ret, refs["retorno_12m"]["bom"], refs["retorno_12m"]["ruim"])
    if perfil == 3:
        label = "✅" if ret > 80 else ("ℹ️ " if ret > 20 else "⚠️ ")
        motivos.append(f"{label} Retorno 12m: {ret:+.1f}% ← critério principal")
    else:
        label = "✅" if ret > 50 else ("ℹ️ " if ret > 0 else "⚠️ ")
        motivos.append(f"{label} Retorno 12m: {ret:+.1f}%")

    vol_a = float(ind.get("volatilidade_anual", 0) or 0)
    if vol_a > 0:
        if perfil == 1:
            motivos.append(f"{'✅' if vol_a < 60 else '⚠️ '} Volatilidade: {vol_a:.0f}%/ano")
        else:
            motivos.append(f"Volatilidade anual: {vol_a:.0f}%")

    return round(score * 100, 1), motivos[:4]

# ── Top Cripto ─────────────────────────────────────────────────────────────────

def top_cripto(perfil: int, n: int = 4) -> list[dict]:
    """
    Busca top N criptos por market cap da CoinGecko e rankeia pelo perfil.
    """
    try:
        cg = CoinGeckoClient()
        mkt = cg.get_markets_top(top_n=CRIPTO_TOP_N)
    except Exception as e:
        logger.error(f"Erro ao buscar cripto: {e}")
        return []

    with ThreadPoolExecutor(max_workers=6) as ex:
        rv_futures = {ex.submit(cg.get_retorno_e_volatilidade, c["id"]): c["id"] for c in mkt}
        rv_map = {}
        for fut in as_completed(rv_futures):
            cid = rv_futures[fut]
            try:
                rv_map[cid] = fut.result()
            except Exception:
                rv_map[cid] = {"retorno_12m_pct": 0.0, "volatilidade_anual": 0.0}

    resultados = []
    for item in mkt:
        cid = item["id"]
        rv  = rv_map.get(cid, {})
        ind = {
            "market_cap":         item.get("market_cap",   0),
            "volume":             item.get("total_volume", 0),
            "retorno_12m":        rv.get("retorno_12m_pct", 0),
            "volatilidade_anual": rv.get("volatilidade_anual", 0),
        }
        score, motivos = _score_cripto(ind, perfil)
        resultados.append({
            "ticker":      item.get("symbol", "").upper(),
            "nome":        item.get("name", ""),
            "preco":       item.get("current_price", 0),
            "score":       score,
            "motivos":     motivos,
            "retorno_12m": ind["retorno_12m"],
            "market_cap":  ind["market_cap"],
        })

    return sorted(resultados, key=lambda x: -x["score"])[:n]