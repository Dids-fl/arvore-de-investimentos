import math
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from apis.status_invest import StatusInvestClient
from apis.brapi import BrapiClient
from apis.fmp import FMPClient
from apis.coingecko import CoinGeckoClient
from apis.fundamentus import get_stock_data, search_stocks as fundamentus_search
from apis.analise_crescimento import get_cagr_receita, calcular_cagr
from filtros import aplicar_filtros, filtrar_por_setor, filtrar_por_governanca
from validador import validar_universo, resumo_validacao
from ativos import (
    MIN_LIQUIDEZ_ACOES, MIN_LIQUIDEZ_FIIS,
    UNIVERSO_ACOES_N, UNIVERSO_FIIS_N, CRIPTO_TOP_N,
    PESOS_ACOES, PESOS_FIIS, PESOS_CRIPTO,
    REF_ACOES, REF_ACOES_AGRESSIVO, REF_FIIS, REF_CRIPTO,
    LIMIARES_DY_ACOES, LIMIARES_ROE_ACOES, LIMIARES_PL_ACOES,
    PESO_TAMANHO_ACOES, MKTCAP_REF_MAX_B, MKTCAP_REF_MIN_B, LIQ_REF_MAX_M,
)
from config import USE_FUNDAMENTUS, FILTRO_SETORES, FILTRO_GOVERNANCA
from utils.logging_config import get_logger

logger = get_logger(__name__)

# ── Normalização ──────────────────────────────────────────────────────────────

def norm(valor: float, bom: float, ruim: float) -> float:
    if abs(bom - ruim) < 1e-9:
        return 0.5
    return max(0.0, min(1.0, (valor - ruim) / (bom - ruim)))

# ── Score de ações (com CAGR) ────────────────────────────────────────────────

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
                motivos.append(f"ℹ️  ROE: {roe:.1f}% (aceitável)")
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
            if pvp < 2.0:
                motivos.append(f"✅ P/VP: {pvp:.2f}")

    # ── Crescimento de receita (CAGR) ──────────────────────────────────────────
    cagr = ind.get('crescimento_receita', 0)
    if cagr and cagr > 0:
        peso_cresc = 0.10 if perfil == 3 else 0.05 if perfil == 2 else 0.02
        score += peso_cresc * min(1.0, cagr / 0.30)  # normaliza até 30% CAGR
        if perfil == 3:
            if cagr > 0.20:
                motivos.append(f"✅ CAGR receita: {cagr*100:.1f}% (acelerado)")
            elif cagr > 0.10:
                motivos.append(f"ℹ️  CAGR receita: {cagr*100:.1f}%")
            else:
                motivos.append(f"⚠️  Crescimento baixo: {cagr*100:.1f}%")

    return round(score * 100, 1), motivos[:4]

# ── Score de FIIs ─────────────────────────────────────────────────────────────

def _score_fii(ind: dict, perfil: int) -> tuple[float, list[str]]:
    pesos  = PESOS_FIIS[perfil]
    refs   = REF_FIIS
    score  = 0.0
    motivos: list[str] = []

    dy = float(ind.get("dy", 0) or 0)
    score += pesos["dy"] * norm(dy, refs["dy"]["bom"], refs["dy"]["ruim"])
    if perfil == 1:
        label = "✅" if dy >= 11 else ("ℹ️ " if dy >= 8 else "⚠️ ")
        motivos.append(f"{label} DY: {dy:.1f}% {'(excelente renda mensal)' if dy >= 11 else ''}")
    elif perfil == 2:
        label = "✅" if dy >= 10 else "ℹ️ "
        motivos.append(f"{label} DY: {dy:.1f}%")
    else:
        if dy >= 10:
            motivos.append(f"ℹ️  DY: {dy:.1f}% (bônus de renda)")

    pvp = float(ind.get("pvp", 0) or 0)
    if pvp > 0:
        score += pesos["pvp"] * norm(pvp, refs["pvp"]["bom"], refs["pvp"]["ruim"])
        if perfil == 3:
            if pvp < 0.90:
                motivos.append(f"✅ P/VP: {pvp:.2f} (desconto sobre patrimônio = upside)")
            elif pvp < 1.0:
                motivos.append(f"ℹ️  P/VP: {pvp:.2f}")
            else:
                motivos.append(f"⚠️  P/VP: {pvp:.2f} (prêmio limita valorização)")
        else:
            label = "✅" if pvp < 1.0 else ("ℹ️ " if pvp <= 1.15 else "⚠️ ")
            motivos.append(f"{label} P/VP: {pvp:.2f}")

    liq = float(ind.get("liquidez", 0) or 0)
    if liq > 0:
        score += pesos["liquidez"] * norm(liq, refs["liquidez"]["bom"], refs["liquidez"]["ruim"])
        if perfil == 3:
            label = "✅" if liq >= 2_000_000 else "ℹ️ "
            motivos.append(f"{label} Liquidez: R${liq/1e6:.1f}M/dia (agilidade para operar)")
        else:
            motivos.append(f"Liquidez: R${liq/1e6:.1f}M/dia")

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

# ── Funções de busca com fallback ──────────────────────────────────────────────

def _buscar_acoes_status_invest() -> list[dict]:
    try:
        si = StatusInvestClient()
        return si.search_stocks(limit=UNIVERSO_ACOES_N)
    except Exception as e:
        logger.warning(f"Status Invest falhou: {e}")
        return []

def _buscar_acoes_brapi() -> list[dict]:
    try:
        client = BrapiClient()
        tickers = ["PETR4", "VALE3", "ITUB4", "BBDC4", "ABEV3", "BBAS3", "WEGE3", "RENT3", "MGLU3", "B3SA3"]
        dados = []
        for t in tickers:
            try:
                q = client.get_quote(t)
                dados.append({
                    "ticker": t,
                    "nome": q.get("longName", ""),
                    "cotacao": q.get("regularMarketPrice", 0),
                    "dy": 0,
                    "pl": q.get("priceEarnings", 0),
                    "pvp": 0,
                    "roe": 0,
                    "liquidez": 0,
                    "mktcap_proxy": q.get("marketCap", 0),
                })
            except Exception:
                continue
        return dados
    except Exception as e:
        logger.warning(f"BRAPI falhou: {e}")
        return []

def _buscar_acoes_fmp() -> list[dict]:
    try:
        client = FMPClient()
        lista = client._get("stock/list")
        dados = []
        for item in lista[:UNIVERSO_ACOES_N]:
            sym = item.get("symbol", "")
            if not sym.endswith(".SA"):
                continue
            try:
                perfil = client.get_profile(sym)
                dados.append({
                    "ticker": sym,
                    "nome": perfil.get("companyName", ""),
                    "cotacao": perfil.get("price", 0),
                    "dy": 0,
                    "pl": 0,
                    "pvp": 0,
                    "roe": 0,
                    "liquidez": 0,
                    "mktcap_proxy": perfil.get("mktCap", 0),
                })
            except Exception:
                continue
        return dados
    except Exception as e:
        logger.warning(f"FMP falhou: {e}")
        return []

def _enriquecer_com_fundamentus(ativos: list[dict]) -> list[dict]:
    """Tenta enriquecer ativos com dados do Fundamentus (setor, CAGR)."""
    if not USE_FUNDAMENTUS:
        return ativos
    enriquecidos = []
    for ativo in ativos:
        ticker = ativo.get("ticker")
        try:
            dados = get_stock_data(ticker)
            if dados:
                ativo["setor"] = dados.get("setor", "")
                ativo["crescimento_receita"] = dados.get("receita_cagr_5a", 0) / 100.0
        except Exception as e:
            logger.debug(f"Fundamentus para {ticker} falhou: {e}")
        enriquecidos.append(ativo)
    return enriquecidos

# ── Top N ações (com fallback e filtros) ──────────────────────────────────────

def top_acoes(perfil: int, n: int = 5) -> list[dict]:
    universo = _buscar_acoes_status_invest()
    if not universo:
        logger.info("Status Invest sem dados, tentando BRAPI...")
        universo = _buscar_acoes_brapi()
    if not universo:
        logger.info("BRAPI sem dados, tentando FMP...")
        universo = _buscar_acoes_fmp()
    if not universo:
        logger.error("Nenhuma fonte de dados para ações disponível.")
        return []

    # Enriquecer com Fundamentus
    universo = _enriquecer_com_fundamentus(universo)

    liquidos = [a for a in universo if float(a.get("liquidez", 0) or 0) >= MIN_LIQUIDEZ_ACOES]
    if not liquidos:
        liquidos = universo

    liquidos_validados, descartados = validar_universo(liquidos)
    if descartados:
        logger.warning(resumo_validacao(descartados))
    liquidos = liquidos_validados

    if perfil == 1:
        com_dy = [a for a in liquidos if float(a.get("dy", 0) or 0) >= 3.0]
        liquidos = com_dy if com_dy else liquidos
    elif perfil == 3:
        com_roe = [a for a in liquidos if float(a.get("roe", 0) or 0) >= 10.0]
        liquidos = com_roe if com_roe else liquidos

    tamanho_peso = PESO_TAMANHO_ACOES.get(perfil, 0.18)
    candidatos = {}
    for ind in liquidos:
        dy  = float(ind.get("dy",  0) or 0)
        pl  = float(ind.get("pl",  0) or 0)
        roe = float(ind.get("roe", 0) or 0)
        if dy == 0 and pl == 0 and roe == 0:
            continue

        score_fund, motivos = _score_acao(ind, perfil)

        liq_m      = float(ind.get("liquidez",     0) or 0) / 1_000_000
        mktcap_b   = float(ind.get("mktcap_proxy", 0) or 0) / 1_000_000_000

        if liq_m > 0:
            score_liq = min(1.0, math.log10(max(liq_m, 0.001)) / math.log10(LIQ_REF_MAX_M))
        else:
            score_liq = 0.0

        if mktcap_b >= MKTCAP_REF_MIN_B:
            score_mktcap = min(1.0, math.log10(mktcap_b / MKTCAP_REF_MIN_B) /
                                     math.log10(MKTCAP_REF_MAX_B / MKTCAP_REF_MIN_B))
        else:
            score_mktcap = 0.0

        if score_mktcap > 0:
            score_tamanho = score_mktcap * 0.667 + score_liq * 0.333
        else:
            score_tamanho = score_liq

        confianca = ind.get("confianca", 1.0)
        score = (score_fund * (1 - tamanho_peso) + score_tamanho * 100 * tamanho_peso) * confianca

        base = re.sub(r"\d+$", "", ind.get("ticker", ""))
        if base not in candidatos or score > candidatos[base]["score"]:
            candidatos[base] = {
                "ticker":    ind.get("ticker", ""),
                "nome":      ind.get("nome", ""),
                "preco":     float(ind.get("cotacao", 0) or 0),
                "score":     round(score, 1),
                "motivos":   motivos,
                "dy":        dy,
                "roe":       roe,
                "pl":        pl,
                "confianca": confianca,
                "setor":     ind.get("setor", ""),
            }

    # ── Aplicar filtros se configurados ──────────────────────────────────────
    lista_para_filtrar = list(candidatos.values())
    if FILTRO_SETORES:
        lista_para_filtrar = filtrar_por_setor(lista_para_filtrar, FILTRO_SETORES)
    if FILTRO_GOVERNANCA:
        lista_para_filtrar = filtrar_por_governanca(lista_para_filtrar, FILTRO_GOVERNANCA)
    # Reconstruir candidatos
    candidatos = {a['ticker']: a for a in lista_para_filtrar}

    return sorted(candidatos.values(), key=lambda x: -x["score"])[:n]

# ── Top FIIs ──────────────────────────────────────────────────────────────────

def top_fiis(perfil: int, n: int = 5) -> list[dict]:
    try:
        si = StatusInvestClient()
        universo = si.search_fiis(limit=UNIVERSO_FIIS_N)
    except Exception as e:
        logger.error(f"Erro ao buscar FIIs: {e}")
        return []

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

# ── Top Cripto ─────────────────────────────────────────────────────────────────

def top_cripto(perfil: int, n: int = 4) -> list[dict]:
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