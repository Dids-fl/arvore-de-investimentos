"""
Motor de score para Ações (ON/PN) e FIIs.
Usa Fundamentus + BRAPI (via data_merger) para enriquecer dados.
"""

import math
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

# Módulos internos da pasta acoes_fiis (imports relativos)
from .apis.fundamentus_scraper import get_all_bulk, get_fiis_bulk
from .apis.brapi import BrapiClient
from .apis.status_invest import StatusInvestClient
from .apis.data_merger import merge_ticker_data
from .filtros import aplicar_filtros, filtrar_por_setor, filtrar_por_governanca
from .validador import validar_universo, resumo_validacao, validar_com_brapi
from .ativos import (
    MIN_LIQUIDEZ_ACOES, MIN_LIQUIDEZ_FIIS,
    UNIVERSO_ACOES_N, UNIVERSO_FIIS_N,
    PESOS_ACOES, PESOS_FIIS,
    REF_ACOES, REF_ACOES_AGRESSIVO, REF_FIIS,
    LIMIARES_DY_ACOES, LIMIARES_ROE_ACOES, LIMIARES_PL_ACOES,
    PESO_TAMANHO_ACOES, MKTCAP_REF_MAX_B, MKTCAP_REF_MIN_B, LIQ_REF_MAX_M,
)

# Módulos externos
from utils.logging_config import get_logger

# Importa configurações com fallback
try:
    from config import USE_FUNDAMENTUS, FILTRO_SETORES, FILTRO_GOVERNANCA, LIMITE_MKTCAP
except ImportError:
    USE_FUNDAMENTUS = True
    FILTRO_SETORES = []
    FILTRO_GOVERNANCA = []
    LIMITE_MKTCAP = {1: 2_000_000_000, 2: 1_000_000_000, 3: 500_000_000}

logger = get_logger(__name__)

# ── Normalização ──────────────────────────────────────────────────────────────

def norm(valor: float, bom: float, ruim: float) -> float:
    if abs(bom - ruim) < 1e-9:
        return 0.5
    return max(0.0, min(1.0, (valor - ruim) / (bom - ruim)))

# ── Score de ações (com CAGR e consistência de dividendos) ──────────────────

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
        score += peso_cresc * min(1.0, cagr / 0.30)
        if perfil == 3:
            if cagr > 0.20:
                motivos.append(f"✅ CAGR receita: {cagr*100:.1f}% (acelerado)")
            elif cagr > 0.10:
                motivos.append(f"ℹ️  CAGR receita: {cagr*100:.1f}%")
            else:
                motivos.append(f"⚠️  Crescimento baixo: {cagr*100:.1f}%")

    # ── Bônus por consistência de dividendos (BRAPI) ──────────────────────────
    if ind.get("dividendos_consistentes", False):
        if perfil == 1:
            score += 5
            motivos.append("✅ Dividendos consistentes (5+ anos)")
        elif perfil == 2:
            score += 3
            motivos.append("ℹ️  Dividendos consistentes")

    # ── Endividamento (Dívida/PL) – essencial para conservador ──────────────
    divida_pl = ind.get('divida_patrimonio', 0)
    if perfil == 1 and divida_pl > 0:
        if divida_pl < 0.5:
            score += 5
            motivos.append("✅ Dívida controlada (Dív/PL < 0.5)")
        elif divida_pl < 1.0:
            score += 2
            motivos.append(f"ℹ️  Dívida moderada: {divida_pl:.2f}x PL")
        else:
            score -= 5
            motivos.append(f"⚠️  Endividamento alto: {divida_pl:.2f}x PL")

    return round(score * 100, 1), motivos[:6]

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

# ── Top N ações ──────────────────────────────────────────────────────────────────

def top_acoes(perfil: int, n: int = 5) -> list[dict]:
    """
    Usa Fundamentus (bulk) como fonte primária e enriquece com BRAPI.
    """
    universo = []

    # 1. Tenta Fundamentus
    if USE_FUNDAMENTUS:
        try:
            bulk_data = get_all_bulk()
            if bulk_data:
                universo = list(bulk_data.values())
                logger.info(f"Fundamentus: {len(universo)} ações carregadas")
        except Exception as e:
            logger.warning(f"Fundamentus bulk falhou: {e}")

    # 2. Fallback para Status Invest
    if not universo:
        logger.info("Fallback: buscando ações via Status Invest...")
        universo = _buscar_acoes_status_invest()
    if not universo:
        logger.info("Fallback: buscando ações via BRAPI...")
        universo = _buscar_acoes_brapi()
    if not universo:
        logger.error("Nenhuma fonte de dados para ações disponível.")
        return []

    # ── FILTRO DE LIQUIDEZ ──────────────────────────────────────────────────
    liquidos = [a for a in universo if float(a.get("liquidez", 0) or 0) >= MIN_LIQUIDEZ_ACOES]
    if not liquidos:
        liquidos = universo

    # ── ENRIQUECE COM BRAPI (Market Cap e consistência de dividendos) ──────
    enriquecidos = []
    for ind in liquidos:
        ticker = ind.get('ticker')
        if ticker:
            try:
                dados_br = merge_ticker_data(ticker)
                ind['mktcap_proxy'] = dados_br.get('market_cap', 0)
                ind['dividendos_consistentes'] = dados_br.get('dividendos_consistentes', False)
                if not ind.get('pl'):
                    ind['pl'] = dados_br.get('pl', 0)
                if not ind.get('cotacao'):
                    ind['cotacao'] = dados_br.get('preco', 0)
                if not ind.get('divida_patrimonio'):
                    ind['divida_patrimonio'] = dados_br.get('divida_patrimonio', 0)
                if not ind.get('crescimento_receita'):
                    ind['crescimento_receita'] = dados_br.get('receita_cagr_5a', 0) / 100.0
            except Exception as e:
                logger.debug(f"Erro ao enriquecer {ticker} com BRAPI: {e}")
        enriquecidos.append(ind)

    # ── FILTRO DE MARKET CAP ─────────────────────────────────────────────────
    mktcap_min = LIMITE_MKTCAP.get(perfil, 1_000_000_000)
    liquidos_filtrados = []
    for a in enriquecidos:
        mcap = a.get('mktcap_proxy', 0)
        if mcap == 0:
            liquidos_filtrados.append(a)
        elif mcap >= mktcap_min:
            liquidos_filtrados.append(a)
        else:
            logger.debug(f"Excluído {a.get('ticker')} - market cap R${mcap/1e9:.2f}B (min: R${mktcap_min/1e9:.1f}B)")
    if liquidos_filtrados:
        liquidos = liquidos_filtrados
    else:
        logger.warning("Nenhum ativo passou no filtro de market cap. Usando todos (fallback).")

    # ── VALIDAÇÃO ESTATÍSTICA ──────────────────────────────────────────────
    liquidos_validados, descartados = validar_universo(liquidos)
    if descartados:
        logger.warning(resumo_validacao(descartados))
    liquidos = liquidos_validados

    # ── FILTROS POR PERFIL ──────────────────────────────────────────────────
    if perfil == 1:
        com_dy = [a for a in liquidos if float(a.get("dy", 0) or 0) >= 3.0]
        liquidos = com_dy if com_dy else liquidos
    elif perfil == 3:
        com_roe = [a for a in liquidos if float(a.get("roe", 0) or 0) >= 10.0]
        liquidos = com_roe if com_roe else liquidos

    # ── SCORE E RANKING ──────────────────────────────────────────────────────
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

    # ── FILTROS DE SETOR E GOVERNANÇA ──────────────────────────────────────
    lista_para_filtrar = list(candidatos.values())
    if FILTRO_SETORES:
        lista_para_filtrar = filtrar_por_setor(lista_para_filtrar, FILTRO_SETORES)
    if FILTRO_GOVERNANCA:
        lista_para_filtrar = filtrar_por_governanca(lista_para_filtrar, FILTRO_GOVERNANCA)
    candidatos = {a['ticker']: a for a in lista_para_filtrar}

    # ── CROSS-VALIDAÇÃO COM BRAPI ──────────────────────────────────────────
    candidatos_lista = list(candidatos.values())
    if candidatos_lista:
        candidatos_lista = validar_com_brapi(candidatos_lista)
        candidatos = {a['ticker']: a for a in candidatos_lista}

    return sorted(candidatos.values(), key=lambda x: -x["score"])[:n]

# ── Top FIIs ──────────────────────────────────────────────────────────────────

def top_fiis(perfil: int, n: int = 5) -> list[dict]:
    """
    Usa get_fiis_bulk() para obter FIIs do Fundamentus.
    Fallback para Status Invest se o Fundamentus falhar.
    """
    fiis_data = get_fiis_bulk()
    if not fiis_data:
        logger.warning("Fundamentus FIIs bulk vazio, tentando Status Invest...")
        try:
            si = StatusInvestClient()
            universo = si.search_fiis(limit=UNIVERSO_FIIS_N)
            if universo:
                fiis_data = {f['ticker']: f for f in universo}
        except Exception as e:
            logger.error(f"Erro ao buscar FIIs do Status Invest: {e}")
            return []

    if not fiis_data:
        return []

    todos_fiis = list(fiis_data.values())
    liquidos = [f for f in todos_fiis if f.get('liquidez', 0) >= MIN_LIQUIDEZ_FIIS]
    if not liquidos:
        liquidos = todos_fiis

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