"""
Motor de score: busca universo dinâmico das APIs, normaliza e rankeia.

Fluxo:
  top_acoes()  → Status Invest (top 150 por liquidez) → filtra → score → top N
  top_fiis()   → Status Invest (top 100 FIIs)         → filtra → score → top N
  top_cripto() → CoinGecko     (top 20 por mkt cap)   → score → top N

Diferenciação por perfil
────────────────────────
  Conservador (1): prioriza DY alto e recorrente. Penaliza duramente
      empresas sem histórico de proventos. P/L baixo confirma preço justo.
      Feedback de DY só é ✅ a partir de 8% a.a.

  Moderado (2): ROE é o motor — busca empresas de qualidade que também
      distribuem. DY razoável (~5%) já é positivo. Aceita P/L moderado
      desde que o ROE justifique. É o único perfil que destaca empresas
      com boa combinação de crescimento + renda.

  Agressivo (3): ROE dominante (peso 0.70). DY quase irrelevante —
      empresa que reinveste lucro cresce mais. P/L alto tolerado se o
      ROE for excepcional. Usa REF_ACOES_AGRESSIVO para não punir
      empresas de crescimento negociadas a múltiplos premium.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed

from apis.status_invest import StatusInvestClient
from apis.coingecko import CoinGeckoClient
from validador import validar_universo, resumo_validacao
from ativos import (
    MIN_LIQUIDEZ_ACOES, MIN_LIQUIDEZ_FIIS,
    UNIVERSO_ACOES_N, UNIVERSO_FIIS_N, CRIPTO_TOP_N,
    PESOS_ACOES, PESOS_FIIS, PESOS_CRIPTO,
    REF_ACOES, REF_ACOES_AGRESSIVO, REF_FIIS, REF_CRIPTO,
    LIMIARES_DY_ACOES, LIMIARES_ROE_ACOES, LIMIARES_PL_ACOES,
)


# ── Normalização ──────────────────────────────────────────────────────────────

def norm(valor: float, bom: float, ruim: float) -> float:
    """Normaliza valor para [0.0, 1.0]. bom→1.0, ruim→0.0."""
    if abs(bom - ruim) < 1e-9:
        return 0.5
    return max(0.0, min(1.0, (valor - ruim) / (bom - ruim)))


# ── Score de ações ────────────────────────────────────────────────────────────

def _score_acao(ind: dict, perfil: int) -> tuple[float, list[str]]:
    pesos   = PESOS_ACOES[perfil]
    # Agressivo usa referências próprias para tolerar P/L e P/VP mais altos
    refs    = REF_ACOES_AGRESSIVO if perfil == 3 else REF_ACOES
    lim_dy  = LIMIARES_DY_ACOES[perfil]
    lim_roe = LIMIARES_ROE_ACOES[perfil]
    lim_pl  = LIMIARES_PL_ACOES[perfil]
    score   = 0.0
    motivos: list[str] = []

    # ── DY ───────────────────────────────────────────────────────────────────
    dy = float(ind.get("dy", 0) or 0)
    score += pesos["dy"] * norm(dy, refs["dy"]["bom"], refs["dy"]["ruim"])

    if perfil == 1:
        # Conservador: DY é critério dominante — penaliza explicitamente DY baixo
        if dy >= lim_dy["otimo"]:
            motivos.append(f"✅ DY: {dy:.1f}% (excelente para renda)")
        elif dy >= lim_dy["ok"]:
            motivos.append(f"ℹ️  DY: {dy:.1f}% (razoável)")
        else:
            motivos.append(f"⚠️  DY: {dy:.1f}% (baixo para conservador)")
    elif perfil == 2:
        # Moderado: DY é complementar — só destaca quando realmente bom
        if dy >= lim_dy["otimo"]:
            motivos.append(f"✅ DY: {dy:.1f}% + crescimento")
        elif dy >= lim_dy["ok"]:
            motivos.append(f"ℹ️  DY: {dy:.1f}%")
        # Abaixo do mínimo moderado: silencia — ROE vai falar mais alto
    else:
        # Agressivo: DY quase ignorado nos pesos; só menciona se for relevante
        if dy >= lim_dy["otimo"]:
            motivos.append(f"ℹ️  DY: {dy:.1f}% (bônus — foco é crescimento)")
        # Silencia DY baixo: esperado em empresas de crescimento

    # ── P/L ──────────────────────────────────────────────────────────────────
    pl = float(ind.get("pl", 0) or 0)
    if pl > 0:
        score += pesos["pl"] * norm(pl, refs["pl"]["bom"], refs["pl"]["ruim"])
        if perfil == 1:
            if pl <= lim_pl["otimo"]:
                motivos.append(f"✅ P/L: {pl:.1f} (preço justo)")
            elif pl <= lim_pl["ok"]:
                motivos.append(f"ℹ️  P/L: {pl:.1f}")
            else:
                motivos.append(f"⚠️  P/L: {pl:.1f} (caro para renda)")
        elif perfil == 2:
            if pl <= lim_pl["otimo"]:
                motivos.append(f"✅ P/L: {pl:.1f}")
            elif pl <= lim_pl["ok"]:
                motivos.append(f"ℹ️  P/L: {pl:.1f}")
            else:
                motivos.append(f"⚠️  P/L: {pl:.1f} (avaliar crescimento)")
        else:
            # Agressivo: P/L alto é aceitável — o ROE que justifica
            if pl <= lim_pl["otimo"]:
                motivos.append(f"✅ P/L: {pl:.1f} (e ROE alto = oportunidade)")
            elif pl <= lim_pl["ok"]:
                motivos.append(f"ℹ️  P/L: {pl:.1f} (aceitável se ROE justificar)")
            else:
                motivos.append(f"⚠️  P/L: {pl:.1f} (muito esticado)")
    else:
        if perfil == 1:
            motivos.append("❌ P/L negativo — empresa com prejuízo")
        elif perfil == 2:
            motivos.append("⚠️  P/L negativo (fase de crescimento?)")
        else:
            motivos.append("ℹ️  P/L negativo (reinvestimento agressivo?)")

    # ── ROE ──────────────────────────────────────────────────────────────────
    roe = float(ind.get("roe", 0) or 0)
    if roe > 0:
        score += pesos["roe"] * norm(roe, refs["roe"]["bom"], refs["roe"]["ruim"])
        if perfil == 1:
            # Para conservador: ROE é filtro de qualidade, não motor
            if roe >= lim_roe["otimo"]:
                motivos.append(f"✅ ROE: {roe:.1f}% (negócio sólido)")
            elif roe >= lim_roe["ok"]:
                motivos.append(f"ℹ️  ROE: {roe:.1f}%")
            # Silencia ROE baixo: DY já sinalizou o problema
        elif perfil == 2:
            # Para moderado: ROE é o motor — sempre aparece nos motivos
            if roe >= lim_roe["otimo"]:
                motivos.append(f"✅ ROE: {roe:.1f}% (qualidade comprovada)")
            elif roe >= lim_roe["ok"]:
                motivos.append(f"ℹ️  ROE: {roe:.1f}% (aceitável)")
            else:
                motivos.append(f"⚠️  ROE: {roe:.1f}% (abaixo do esperado)")
        else:
            # Para agressivo: ROE excepcional é o critério principal
            if roe >= lim_roe["otimo"]:
                motivos.append(f"✅ ROE: {roe:.1f}% ← motor de crescimento")
            elif roe >= lim_roe["ok"]:
                motivos.append(f"ℹ️  ROE: {roe:.1f}%")
            else:
                motivos.append(f"❌ ROE: {roe:.1f}% (insuficiente para crescimento)")
    elif perfil == 3:
        motivos.append("❌ ROE zero/negativo — descartável para agressivo")

    # ── P/VP ─────────────────────────────────────────────────────────────────
    pvp = float(ind.get("pvp", 0) or 0)
    if pvp > 0:
        score += pesos["pvp"] * norm(pvp, refs["pvp"]["bom"], refs["pvp"]["ruim"])
        if perfil == 1:
            if pvp < 1.0:
                motivos.append(f"✅ P/VP: {pvp:.2f} (abaixo do patrimônio)")
            elif pvp < 1.5:
                motivos.append(f"ℹ️  P/VP: {pvp:.2f}")
            else:
                motivos.append(f"⚠️  P/VP: {pvp:.2f} (caro)")
        elif perfil == 2:
            if pvp < 1.5:
                motivos.append(f"✅ P/VP: {pvp:.2f}")
            elif pvp < 2.5:
                motivos.append(f"ℹ️  P/VP: {pvp:.2f}")
        else:
            # Agressivo: P/VP alto é normal em empresas premium de crescimento
            if pvp < 2.0:
                motivos.append(f"✅ P/VP: {pvp:.2f}")
            # Silencia P/VP acima: esperado em crescimento de qualidade

    return round(score * 100, 1), motivos[:4]


# ── Score de FIIs ─────────────────────────────────────────────────────────────

def _score_fii(ind: dict, perfil: int) -> tuple[float, list[str]]:
    pesos  = PESOS_FIIS[perfil]
    refs   = REF_FIIS
    score  = 0.0
    motivos: list[str] = []

    # ── DY ───────────────────────────────────────────────────────────────────
    dy = float(ind.get("dy", 0) or 0)
    score += pesos["dy"] * norm(dy, refs["dy"]["bom"], refs["dy"]["ruim"])
    if perfil == 1:
        label = "✅" if dy >= 11 else ("ℹ️ " if dy >= 8 else "⚠️ ")
        motivos.append(f"{label} DY: {dy:.1f}% {'(excelente renda mensal)' if dy >= 11 else ''}")
    elif perfil == 2:
        label = "✅" if dy >= 10 else "ℹ️ "
        motivos.append(f"{label} DY: {dy:.1f}%")
    else:
        # Agressivo foca em valorização — DY é secundário
        if dy >= 10:
            motivos.append(f"ℹ️  DY: {dy:.1f}% (bônus de renda)")

    # ── P/VP ─────────────────────────────────────────────────────────────────
    pvp = float(ind.get("pvp", 0) or 0)
    if pvp > 0:
        score += pesos["pvp"] * norm(pvp, refs["pvp"]["bom"], refs["pvp"]["ruim"])
        if perfil == 3:
            # Agressivo: P/VP baixo = maior upside de valorização
            if pvp < 0.90:
                motivos.append(f"✅ P/VP: {pvp:.2f} (desconto sobre patrimônio = upside)")
            elif pvp < 1.0:
                motivos.append(f"ℹ️  P/VP: {pvp:.2f}")
            else:
                motivos.append(f"⚠️  P/VP: {pvp:.2f} (prêmio limita valorização)")
        else:
            label = "✅" if pvp < 1.0 else ("ℹ️ " if pvp <= 1.15 else "⚠️ ")
            motivos.append(f"{label} P/VP: {pvp:.2f}")

    # ── Liquidez ─────────────────────────────────────────────────────────────
    liq = float(ind.get("liquidez", 0) or 0)
    if liq > 0:
        score += pesos["liquidez"] * norm(liq, refs["liquidez"]["bom"], refs["liquidez"]["ruim"])
        if perfil == 3:
            label = "✅" if liq >= 2_000_000 else "ℹ️ "
            motivos.append(f"{label} Liquidez: R${liq/1e6:.1f}M/dia (agilidade para operar)")
        else:
            motivos.append(f"Liquidez: R${liq/1e6:.1f}M/dia")

    # ── Vacância ─────────────────────────────────────────────────────────────
    vac = float(ind.get("vacancia", 0) or 0)
    score += pesos["vacancia"] * norm(vac, refs["vacancia"]["bom"], refs["vacancia"]["ruim"])
    if vac == 0:
        motivos.append("✅ Vacância zero")
    elif perfil == 1 and vac > 5:
        motivos.append(f"⚠️  Vacância: {vac:.1f}% (risco ao DY)")
    elif vac > 10:
        motivos.append(f"⚠️  Vacância: {vac:.1f}%")

    return round(score * 100, 1), motivos[:4]


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


# ── Top N por classe ──────────────────────────────────────────────────────────

def top_acoes(perfil: int, n: int = 5) -> list[dict]:
    """
    Busca universo de ações diretamente do Status Invest,
    filtra por liquidez mínima, valida estatisticamente os dados
    e retorna as top N pelo score do perfil.

    Validação intra-universo (validador.py):
      Calcula mediana e IQR de cada campo (dy, pl, pvp, roe) no universo
      e descarta ativos cujos valores fogem mais de 3.5 × IQR da mediana.
      Limites absolutos adicionais: DY > 30%, P/VP < 0.10, ROE > 200%.
      Ativos com 3+ campos suspeitos são excluídos; 1-2 campos suspeitos
      recebem confiança reduzida mas ainda entram no ranking.
    """
    si = StatusInvestClient()
    universo = si.search_stocks(limit=UNIVERSO_ACOES_N)

    if not universo:
        return []

    liquidos = [a for a in universo
                if float(a.get("liquidez", 0) or 0) >= MIN_LIQUIDEZ_ACOES]

    if not liquidos:
        liquidos = universo

    # ── Validação estatística intra-universo ──────────────────────────────────
    # Descarta dados sabidamente corrompidos antes de qualquer filtro de perfil.
    # Usa IQR-fence de Tukey (3.5×IQR) + limites absolutos por campo.
    liquidos_validados, descartados = validar_universo(liquidos)
    if descartados:
        import sys
        print(resumo_validacao(descartados), file=sys.stderr)
    liquidos = liquidos_validados

    # ── Filtros de perfil ─────────────────────────────────────────────────────
    # Conservador: pré-filtra empresas sem DY (sem histórico de proventos)
    if perfil == 1:
        com_dy = [a for a in liquidos if float(a.get("dy", 0) or 0) >= 3.0]
        liquidos = com_dy if com_dy else liquidos

    # Agressivo: pré-filtra empresas sem ROE (negócios sem retorno sobre capital)
    elif perfil == 3:
        com_roe = [a for a in liquidos if float(a.get("roe", 0) or 0) >= 10.0]
        liquidos = com_roe if com_roe else liquidos

    # ── Score e deduplicação por empresa ─────────────────────────────────────
    import re
    candidatos: dict[str, dict] = {}
    for ind in liquidos:
        dy  = float(ind.get("dy",  0) or 0)
        pl  = float(ind.get("pl",  0) or 0)
        roe = float(ind.get("roe", 0) or 0)
        if dy == 0 and pl == 0 and roe == 0:
            continue

        score, motivos = _score_acao(ind, perfil)

        # Deduplica por empresa-base: POMO3/POMO4 → mantém o de maior score
        base = re.sub(r"\d+$", "", ind.get("ticker", ""))
        if base not in candidatos or score > candidatos[base]["score"]:
            confianca = ind.get("confianca", 1.0)
            candidatos[base] = {
                "ticker":    ind.get("ticker", ""),
                "nome":      ind.get("nome", ""),
                "preco":     float(ind.get("cotacao", 0) or 0),
                "score":     score,
                "motivos":   motivos,
                "dy":        dy,
                "roe":       roe,
                "pl":        pl,
                "confianca": confianca,
            }

    return sorted(candidatos.values(), key=lambda x: -(x["score"] * x.get("confianca", 1.0)))[:n]


def top_fiis(perfil: int, n: int = 5) -> list[dict]:
    """
    Busca universo de FIIs do Status Invest,
    filtra por liquidez e retorna os top N pelo score do perfil.
    """
    si = StatusInvestClient()
    universo = si.search_fiis(limit=UNIVERSO_FIIS_N)

    if not universo:
        return []

    liquidos = [f for f in universo
                if float(f.get("liquidez", 0) or 0) >= MIN_LIQUIDEZ_FIIS]

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
    """
    Busca top N criptos por market cap da CoinGecko e rankeia pelo perfil.
    """
    cg  = CoinGeckoClient()
    mkt = cg.get_markets_top(top_n=CRIPTO_TOP_N)

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