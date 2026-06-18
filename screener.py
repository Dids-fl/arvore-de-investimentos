"""
Motor de score: busca universo dinâmico das APIs, normaliza e rankeia.

Diferenciação por perfil
────────────────────────
  Conservador (1): prioriza DY alto e recorrente.
  Moderado    (2): ROE é o motor; DY razoável (~5%) já é positivo.
  Agressivo   (3): ROE dominante (peso 0.70). DY quase irrelevante.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed

from apis.status_invest import StatusInvestClient
from apis.coingecko import CoinGeckoClient
from ativos import (
    MIN_LIQUIDEZ_ACOES, MIN_LIQUIDEZ_FIIS,
    UNIVERSO_ACOES_N, UNIVERSO_FIIS_N, CRIPTO_TOP_N,
    PESOS_ACOES, PESOS_FIIS, PESOS_CRIPTO,
    REF_ACOES, REF_ACOES_AGRESSIVO, REF_FIIS, REF_CRIPTO,
    LIMIARES_DY_ACOES, LIMIARES_ROE_ACOES, LIMIARES_PL_ACOES,
)


def norm(valor: float, bom: float, ruim: float) -> float:
    if abs(bom - ruim) < 1e-9:
        return 0.5
    return max(0.0, min(1.0, (valor - ruim) / (bom - ruim)))


def _score_acao(ind: dict, perfil: int) -> tuple[float, list[str]]:
    pesos   = PESOS_ACOES[perfil]
    refs    = REF_ACOES_AGRESSIVO if perfil == 3 else REF_ACOES
    lim_dy  = LIMIARES_DY_ACOES[perfil]
    lim_roe = LIMIARES_ROE_ACOES[perfil]
    lim_pl  = LIMIARES_PL_ACOES[perfil]
    score   = 0.0
    motivos: list[str] = []

    # DY
    dy = float(ind.get("dy", 0) or 0)
    score += pesos["dy"] * norm(dy, refs["dy"]["bom"], refs["dy"]["ruim"])
    if perfil == 1:
        if dy >= lim_dy["otimo"]:
            motivos.append(f"✅ DY: {dy:.1f}% (excelente para renda)")
        elif dy >= lim_dy["ok"]:
            motivos.append(f"ℹ️  DY: {dy:.1f}% (razoável)")
        else:
            motivos.append(f"⚠️  DY: {dy:.1f}% (baixo para conservador)")
    elif perfil == 2:
        if dy >= lim_dy["otimo"]:
            motivos.append(f"✅ DY: {dy:.1f}% + crescimento")
        elif dy >= lim_dy["ok"]:
            motivos.append(f"ℹ️  DY: {dy:.1f}%")
    else:
        if dy >= lim_dy["otimo"]:
            motivos.append(f"ℹ️  DY: {dy:.1f}% (bônus — foco é crescimento)")

    # P/L
    pl = float(ind.get("pl", 0) or 0)
    if pl > 0:
        score += pesos["pl"] * norm(pl, refs["pl"]["bom"], refs["pl"]["ruim"])
        if perfil == 1:
            label = "✅" if pl <= lim_pl["otimo"] else ("ℹ️ " if pl <= lim_pl["ok"] else "⚠️ ")
            motivos.append(f"{label} P/L: {pl:.1f}")
        elif perfil == 2:
            label = "✅" if pl <= lim_pl["otimo"] else ("ℹ️ " if pl <= lim_pl["ok"] else "⚠️ ")
            motivos.append(f"{label} P/L: {pl:.1f}")
        else:
            if pl <= lim_pl["otimo"]:
                motivos.append(f"✅ P/L: {pl:.1f} (e ROE alto = oportunidade)")
            elif pl <= lim_pl["ok"]:
                motivos.append(f"ℹ️  P/L: {pl:.1f} (aceitável se ROE justificar)")
            else:
                motivos.append(f"⚠️  P/L: {pl:.1f} (muito esticado)")
    else:
        motivos.append("❌ P/L negativo (prejuízo)" if perfil == 1 else
                       "⚠️  P/L negativo" if perfil == 2 else
                       "ℹ️  P/L negativo (reinvestimento agressivo?)")

    # ROE
    roe = float(ind.get("roe", 0) or 0)
    if roe > 0:
        score += pesos["roe"] * norm(roe, refs["roe"]["bom"], refs["roe"]["ruim"])
        if perfil == 1:
            if roe >= lim_roe["otimo"]:
                motivos.append(f"✅ ROE: {roe:.1f}% (negócio sólido)")
            elif roe >= lim_roe["ok"]:
                motivos.append(f"ℹ️  ROE: {roe:.1f}%")
        elif perfil == 2:
            if roe >= lim_roe["otimo"]:
                motivos.append(f"✅ ROE: {roe:.1f}% (qualidade comprovada)")
            elif roe >= lim_roe["ok"]:
                motivos.append(f"ℹ️  ROE: {roe:.1f}%")
            else:
                motivos.append(f"⚠️  ROE: {roe:.1f}% (abaixo do esperado)")
        else:
            if roe >= lim_roe["otimo"]:
                motivos.append(f"✅ ROE: {roe:.1f}% ← motor de crescimento")
            elif roe >= lim_roe["ok"]:
                motivos.append(f"ℹ️  ROE: {roe:.1f}%")
            else:
                motivos.append(f"❌ ROE: {roe:.1f}% (insuficiente para crescimento)")
    elif perfil == 3:
        motivos.append("❌ ROE zero/negativo — descartável para agressivo")

    # P/VP
    pvp = float(ind.get("pvp", 0) or 0)
    if pvp > 0:
        score += pesos["pvp"] * norm(pvp, refs["pvp"]["bom"], refs["pvp"]["ruim"])
        if perfil == 1:
            label = "✅" if pvp < 1.0 else ("ℹ️ " if pvp < 1.5 else "⚠️ ")
            motivos.append(f"{label} P/VP: {pvp:.2f}")
        elif perfil == 2:
            if pvp < 1.5:
                motivos.append(f"✅ P/VP: {pvp:.2f}")
            elif pvp < 2.5:
                motivos.append(f"ℹ️  P/VP: {pvp:.2f}")
        else:
            if pvp < 2.0:
                motivos.append(f"✅ P/VP: {pvp:.2f}")

    return round(score * 100, 1), motivos[:4]


def _score_fii(ind: dict, perfil: int) -> tuple[float, list[str]]:
    pesos  = PESOS_FIIS[perfil]
    refs   = REF_FIIS
    score  = 0.0
    motivos: list[str] = []

    dy = float(ind.get("dy", 0) or 0)
    score += pesos["dy"] * norm(dy, refs["dy"]["bom"], refs["dy"]["ruim"])
    if perfil == 1:
        label = "✅" if dy >= 11 else ("ℹ️ " if dy >= 8 else "⚠️ ")
        motivos.append(f"{label} DY: {dy:.1f}%")
    elif perfil == 2:
        motivos.append(f"{'✅' if dy >= 10 else 'ℹ️ '} DY: {dy:.1f}%")
    else:
        if dy >= 10:
            motivos.append(f"ℹ️  DY: {dy:.1f}% (bônus de renda)")

    pvp = float(ind.get("pvp", 0) or 0)
    if pvp > 0:
        score += pesos["pvp"] * norm(pvp, refs["pvp"]["bom"], refs["pvp"]["ruim"])
        if perfil == 3:
            label = "✅" if pvp < 0.90 else ("ℹ️ " if pvp < 1.0 else "⚠️ ")
            motivos.append(f"{label} P/VP: {pvp:.2f}")
        else:
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
    elif (perfil == 1 and vac > 5) or vac > 10:
        motivos.append(f"⚠️  Vacância: {vac:.1f}%")

    return round(score * 100, 1), motivos[:4]


def _score_cripto(ind: dict, perfil: int) -> tuple[float, list[str]]:
    pesos  = PESOS_CRIPTO[perfil]
    refs   = REF_CRIPTO
    score  = 0.0
    motivos: list[str] = []

    mc = float(ind.get("market_cap", 0) or 0)
    score += pesos["market_cap"] * norm(mc, refs["market_cap"]["bom"], refs["market_cap"]["ruim"])
    label = "✅" if (perfil == 1 and mc > 500_000_000_000) else "ℹ️ "
    motivos.append(f"{label} Market cap: R${mc/1e9:.0f}B")

    vol = float(ind.get("volume", 0) or 0)
    score += pesos["volume"] * norm(vol, refs["volume"]["bom"], refs["volume"]["ruim"])

    ret = float(ind.get("retorno_12m", 0) or 0)
    score += pesos["retorno_12m"] * norm(ret, refs["retorno_12m"]["bom"], refs["retorno_12m"]["ruim"])
    label = "✅" if ret > (80 if perfil == 3 else 50) else ("ℹ️ " if ret > 0 else "⚠️ ")
    sufixo = " ← critério principal" if perfil == 3 else ""
    motivos.append(f"{label} Retorno 12m: {ret:+.1f}%{sufixo}")

    vol_a = float(ind.get("volatilidade_anual", 0) or 0)
    if vol_a > 0:
        label = "✅" if (perfil == 1 and vol_a < 60) else "⚠️ " if (perfil == 1 and vol_a >= 60) else ""
        motivos.append(f"{label} Volatilidade: {vol_a:.0f}%/ano")

    return round(score * 100, 1), motivos[:4]


def top_acoes(perfil: int, n: int = 5) -> list[dict]:
    import re
    si = StatusInvestClient()
    universo = si.search_stocks(limit=UNIVERSO_ACOES_N)
    if not universo:
        return []

    liquidos = [a for a in universo if float(a.get("liquidez", 0) or 0) >= MIN_LIQUIDEZ_ACOES]
    if not liquidos:
        liquidos = universo

    if perfil == 1:
        com_dy = [a for a in liquidos if float(a.get("dy", 0) or 0) >= 3.0]
        liquidos = com_dy if com_dy else liquidos
    elif perfil == 3:
        com_roe = [a for a in liquidos if float(a.get("roe", 0) or 0) >= 10.0]
        liquidos = com_roe if com_roe else liquidos

    # Deduplicação por empresa (SOND3/SOND5/SOND6 → melhor score)
    candidatos: dict[str, dict] = {}
    for ind in liquidos:
        dy  = float(ind.get("dy",  0) or 0)
        pl  = float(ind.get("pl",  0) or 0)
        roe = float(ind.get("roe", 0) or 0)
        if dy == 0 and pl == 0 and roe == 0:
            continue
        score, motivos = _score_acao(ind, perfil)
        base = re.sub(r"\d+$", "", ind.get("ticker", ""))
        if base not in candidatos or score > candidatos[base]["score"]:
            candidatos[base] = {
                "ticker":  ind.get("ticker", ""),
                "nome":    ind.get("nome", ""),
                "preco":   float(ind.get("cotacao", 0) or 0),
                "score":   score,
                "motivos": motivos,
                "dy":      dy,
                "roe":     roe,
                "pl":      pl,
            }

    return sorted(candidatos.values(), key=lambda x: -x["score"])[:n]


def top_fiis(perfil: int, n: int = 5) -> list[dict]:
    si = StatusInvestClient()
    universo = si.search_fiis(limit=UNIVERSO_FIIS_N)
    if not universo:
        return []

    liquidos = [f for f in universo if float(f.get("liquidez", 0) or 0) >= MIN_LIQUIDEZ_FIIS]
    if not liquidos:
        liquidos = universo

    resultados = []
    for ind in liquidos:
        dy  = float(ind.get("dy",  0) or 0)
        pvp = float(ind.get("pvp", 0) or 0)
        if dy == 0 and pvp == 0:
            continue
        score, motivos = _score_fii(ind, perfil)
        resultados.append({
            "ticker":  ind.get("ticker", ""),
            "nome":    ind.get("nome", ""),
            "tipo":    ind.get("tipo", ""),
            "cotacao": float(ind.get("cotacao", 0) or 0),
            "score":   score,
            "motivos": motivos,
            "dy":      dy,
            "pvp":     pvp,
        })

    return sorted(resultados, key=lambda x: -x["score"])[:n]


def top_cripto(perfil: int, n: int = 4) -> list[dict]:
    cg  = CoinGeckoClient()
    mkt = cg.get_markets_top(top_n=CRIPTO_TOP_N)

    with ThreadPoolExecutor(max_workers=6) as ex:
        rv_futures = {ex.submit(cg.get_retorno_e_volatilidade, c["id"]): c["id"] for c in mkt}
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
