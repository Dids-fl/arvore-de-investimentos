"""
Motor de score: busca universo dinâmico das APIs, normaliza e rankeia.

Fluxo:
  top_acoes()  → Status Invest (top 150 por liquidez) → filtra → score → top N
  top_fiis()   → Status Invest (top 100 FIIs)         → filtra → score → top N
  top_cripto() → CoinGecko     (top 20 por mkt cap)   → score → top N
"""

from concurrent.futures import ThreadPoolExecutor, as_completed

from apis.status_invest import StatusInvestClient
from apis.coingecko import CoinGeckoClient
from ativos import (
    MIN_LIQUIDEZ_ACOES, MIN_LIQUIDEZ_FIIS,
    UNIVERSO_ACOES_N, UNIVERSO_FIIS_N, CRIPTO_TOP_N,
    PESOS_ACOES, PESOS_FIIS, PESOS_CRIPTO,
    REF_ACOES, REF_FIIS, REF_CRIPTO,
)


# ── Normalização ──────────────────────────────────────────────────────────────

def norm(valor: float, bom: float, ruim: float) -> float:
    """Normaliza valor para [0.0, 1.0]. bom→1.0, ruim→0.0."""
    if abs(bom - ruim) < 1e-9:
        return 0.5
    return max(0.0, min(1.0, (valor - ruim) / (bom - ruim)))


# ── Score ─────────────────────────────────────────────────────────────────────

def _score_acao(ind: dict, perfil: int) -> tuple[float, list[str]]:
    pesos  = PESOS_ACOES[perfil]
    refs   = REF_ACOES
    score  = 0.0
    motivos: list[str] = []

    pl = float(ind.get("pl", 0) or 0)
    if pl > 0:
        score += pesos["pl"] * norm(pl, refs["pl"]["bom"], refs["pl"]["ruim"])
        label = "✅" if pl <= 12 else ("ℹ️ " if pl <= 20 else "⚠️ ")
        motivos.append(f"{label} P/L: {pl:.1f}")
    else:
        motivos.append("❌ P/L negativo (prejuízo)")

    dy = float(ind.get("dy", 0) or 0)
    score += pesos["dy"] * norm(dy, refs["dy"]["bom"], refs["dy"]["ruim"])
    label = "✅" if dy >= 7 else ("ℹ️ " if dy >= 4 else "⚠️ ")
    motivos.append(f"{label} DY: {dy:.1f}%")

    roe = float(ind.get("roe", 0) or 0)
    if roe > 0:
        score += pesos["roe"] * norm(roe, refs["roe"]["bom"], refs["roe"]["ruim"])
        if roe >= 18:
            motivos.append(f"✅ ROE: {roe:.1f}%")
        elif roe >= 10:
            motivos.append(f"ℹ️  ROE: {roe:.1f}%")

    pvp = float(ind.get("pvp", 0) or 0)
    if pvp > 0:
        score += pesos["pvp"] * norm(pvp, refs["pvp"]["bom"], refs["pvp"]["ruim"])
        if pvp < 1.5:
            motivos.append(f"✅ P/VP: {pvp:.2f}")
        else:
            motivos.append(f"⚠️  P/VP alto: {pvp:.2f}")

    return round(score * 100, 1), motivos[:4]


def _score_fii(ind: dict, perfil: int) -> tuple[float, list[str]]:
    pesos  = PESOS_FIIS[perfil]
    refs   = REF_FIIS
    score  = 0.0
    motivos: list[str] = []

    dy = float(ind.get("dy", 0) or 0)
    score += pesos["dy"] * norm(dy, refs["dy"]["bom"], refs["dy"]["ruim"])
    motivos.append(f"{'✅' if dy >= 10 else 'ℹ️ '} DY: {dy:.1f}%")

    pvp = float(ind.get("pvp", 0) or 0)
    if pvp > 0:
        score += pesos["pvp"] * norm(pvp, refs["pvp"]["bom"], refs["pvp"]["ruim"])
        label = "✅" if pvp < 1.0 else ("ℹ️ " if pvp <= 1.15 else "⚠️ ")
        motivos.append(f"{label} P/VP: {pvp:.2f}")

    liq = float(ind.get("liquidez", 0) or 0)
    if liq > 0:
        score += pesos["liquidez"] * norm(liq, refs["liquidez"]["bom"], refs["liquidez"]["ruim"])
        motivos.append(f"Liquidez: R${liq/1e6:.1f}M/dia")

    vac = float(ind.get("vacancia", 0) or 0)
    score += pesos["vacancia"] * norm(vac, refs["vacancia"]["bom"], refs["vacancia"]["ruim"])
    if vac == 0:
        motivos.append("✅ Vacância zero")
    elif vac > 10:
        motivos.append(f"⚠️  Vacância: {vac:.1f}%")

    return round(score * 100, 1), motivos[:4]


def _score_cripto(ind: dict, perfil: int) -> tuple[float, list[str]]:
    pesos  = PESOS_CRIPTO[perfil]
    refs   = REF_CRIPTO
    score  = 0.0
    motivos: list[str] = []

    mc = float(ind.get("market_cap", 0) or 0)
    score += pesos["market_cap"] * norm(mc, refs["market_cap"]["bom"], refs["market_cap"]["ruim"])
    motivos.append(f"Market cap: R${mc/1e9:.0f}B")

    vol = float(ind.get("volume", 0) or 0)
    score += pesos["volume"] * norm(vol, refs["volume"]["bom"], refs["volume"]["ruim"])

    ret = float(ind.get("retorno_12m", 0) or 0)
    score += pesos["retorno_12m"] * norm(ret, refs["retorno_12m"]["bom"], refs["retorno_12m"]["ruim"])
    label = "✅" if ret > 50 else ("ℹ️ " if ret > 0 else "⚠️ ")
    motivos.append(f"{label} Retorno 12m: {ret:+.1f}%")

    vol_a = float(ind.get("volatilidade_anual", 0) or 0)
    if vol_a > 0:
        motivos.append(f"Volatilidade anual: {vol_a:.0f}%")

    return round(score * 100, 1), motivos[:4]


# ── Top N por classe ──────────────────────────────────────────────────────────

def top_acoes(perfil: int, n: int = 5) -> list[dict]:
    """
    Busca universo de ações diretamente do Status Invest,
    filtra por liquidez mínima e retorna as top N pelo score do perfil.
    """
    si = StatusInvestClient()

    # Busca ampla: top por DY (tende a capturar empresas maduras e lucrativas)
    universo = si.search_stocks(limit=UNIVERSO_ACOES_N)

    # Filtra liquidez mínima
    liquidos = [a for a in universo
                if float(a.get("liquidez", 0) or 0) >= MIN_LIQUIDEZ_ACOES]

    if not liquidos:
        return []

    resultados = []
    for ind in liquidos:
        score, motivos = _score_acao(ind, perfil)
        resultados.append({
            "ticker":  ind.get("ticker", ""),
            "nome":    ind.get("nome", ""),
            "preco":   float(ind.get("cotacao", 0) or 0),
            "score":   score,
            "motivos": motivos,
            "dy":      float(ind.get("dy",  0) or 0),
            "roe":     float(ind.get("roe", 0) or 0),
            "pl":      float(ind.get("pl",  0) or 0),
        })

    return sorted(resultados, key=lambda x: -x["score"])[:n]


def top_fiis(perfil: int, n: int = 5) -> list[dict]:
    """
    Busca universo de FIIs do Status Invest,
    filtra por liquidez e retorna os top N pelo score do perfil.
    """
    si = StatusInvestClient()
    universo = si.search_fiis(limit=UNIVERSO_FIIS_N)

    liquidos = [f for f in universo
                if float(f.get("liquidez", 0) or 0) >= MIN_LIQUIDEZ_FIIS]

    if not liquidos:
        return []

    resultados = []
    for ind in liquidos:
        score, motivos = _score_fii(ind, perfil)
        resultados.append({
            "ticker":  ind.get("ticker", ""),
            "nome":    ind.get("nome", ""),
            "tipo":    ind.get("tipo", ""),
            "cotacao": float(ind.get("cotacao", 0) or 0),
            "score":   score,
            "motivos": motivos,
            "dy":      float(ind.get("dy",  0) or 0),
            "pvp":     float(ind.get("pvp", 0) or 0),
        })

    return sorted(resultados, key=lambda x: -x["score"])[:n]


def top_cripto(perfil: int, n: int = 4) -> list[dict]:
    """
    Busca top N criptos por market cap da CoinGecko e rankeia pelo perfil.
    """
    cg  = CoinGeckoClient()
    mkt = cg.get_markets_top(top_n=CRIPTO_TOP_N)

    # Retorno e volatilidade em paralelo
    with ThreadPoolExecutor(max_workers=6) as ex:
        rv_futures = {ex.submit(cg.get_retorno_e_volatilidade, c["id"]): c["id"]
                      for c in mkt}
        rv_map: dict[str, dict] = {}
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
