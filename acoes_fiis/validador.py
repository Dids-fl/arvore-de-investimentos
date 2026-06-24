"""
Validação de qualidade de dados dos ativos.

Duas camadas de validação:
  1. validar_universo()  — filtros estatísticos (IQR) + limites absolutos
                           aplicado a TODOS os ativos antes do ranking
  2. validar_com_brapi() — cross-validação P/L entre Status Invest e BRAPI
                           aplicado apenas ao top N candidatos (evita 150 chamadas)

Após a validação, cada ativo recebe:
  confianca: float  — 0.0 (descartado) a 1.0 (dados confiáveis)
  _avisos_validacao: list[str] — motivos de suspeita (campo debug)
"""

import statistics
from typing import Optional, Tuple, List
from concurrent.futures import ThreadPoolExecutor, as_completed

from utils.logging_config import get_logger

logger = get_logger(__name__)

# ── Limites absolutos — regras físicas que nunca mudam ───────────────────────
MAX_DY_ABS   = 30.0    # DY > 30% → provavelmente dividendo extraordinário único
MIN_PVP_ABS  = 0.40    # P/VP < 0.40 → dado incorreto ou liquidação judicial
MAX_ROE_ABS  = 200.0   # ROE > 200% → artefato contábil ou dado errado
MIN_PL_ABS   = 0.50    # P/L entre 0 e 0.5 → artefato de divisão com lucro mínimo

# ── Parâmetros IQR ────────────────────────────────────────────────────────────
LIMITE_IQR  = 3.5      # fence = Q1 - 3.5×IQR  /  Q3 + 3.5×IQR (conservador)
CONF_MINIMA = 0.5      # abaixo disso, ativo excluído do ranking

# ── Cross-validação com BRAPI ─────────────────────────────────────────────────
DIVERGENCIA_PL_MAX   = 0.40  # diferença > 40% entre SI e BRAPI → suspeito
BRAPI_BATCH_SIZE     = 10    # tickers por chamada BRAPI
BRAPI_CANDIDATES_MAX = 30    # valida no máximo os 30 melhores candidatos


# ── 1. Validação estatística (IQR + limites absolutos) ───────────────────────

def _iqr_fence(valores: List[float]) -> Tuple[Optional[float], Optional[float]]:
    limpos = [v for v in valores if v is not None and v > 0]
    if len(limpos) < 10:
        return None, None
    q1 = statistics.quantiles(limpos, n=4)[0]
    q3 = statistics.quantiles(limpos, n=4)[2]
    iqr = q3 - q1
    if iqr < 1e-9:
        return None, None
    return q1 - LIMITE_IQR * iqr, q3 + LIMITE_IQR * iqr


def _validar_ativo(ind: dict, fences: dict) -> Tuple[float, List[str]]:
    suspeitos: List[str] = []
    dy  = float(ind.get("dy",  0) or 0)
    pl  = float(ind.get("pl",  0) or 0)
    pvp = float(ind.get("pvp", 0) or 0)
    roe = float(ind.get("roe", 0) or 0)

    # DY
    if dy > MAX_DY_ABS:
        suspeitos.append(f"DY={dy:.1f}% acima do limite ({MAX_DY_ABS}%) — provável dividendo extraordinário")
    else:
        lo, hi = fences.get("dy", (None, None))
        if hi and dy > hi:
            suspeitos.append(f"DY={dy:.1f}% acima da fence estatística ({hi:.1f}%)")

    # P/L
    if 0 < pl < MIN_PL_ABS:
        suspeitos.append(f"P/L={pl:.2f} suspeito (artefato de divisão com lucro mínimo)")
    elif pl > 0:
        lo, hi = fences.get("pl", (None, None))
        if hi and pl > hi:
            suspeitos.append(f"P/L={pl:.1f} acima da fence ({hi:.1f})")
        if lo and lo > 0.5 and pl < lo:
            suspeitos.append(f"P/L={pl:.1f} abaixo da fence ({lo:.1f})")

    # P/VP
    if 0 < pvp < MIN_PVP_ABS:
        suspeitos.append(f"P/VP={pvp:.3f} abaixo do limite ({MIN_PVP_ABS}) — possível erro de dado")
    else:
        lo, hi = fences.get("pvp", (None, None))
        if hi and pvp > hi:
            suspeitos.append(f"P/VP={pvp:.2f} acima da fence ({hi:.2f})")

    # ROE
    if roe > MAX_ROE_ABS:
        suspeitos.append(f"ROE={roe:.1f}% acima do limite ({MAX_ROE_ABS}%) — artefato contábil")
    elif roe > 0:
        lo, hi = fences.get("roe", (None, None))
        if hi and roe > hi:
            suspeitos.append(f"ROE={roe:.1f}% acima da fence ({hi:.1f}%)")

    n = len(suspeitos)
    confianca = 1.0 if n == 0 else 0.7 if n == 1 else 0.4 if n == 2 else 0.0
    return confianca, suspeitos


def validar_universo(universo: List[dict]) -> Tuple[List[dict], List[dict]]:
    """
    Camada 1: validação estatística.
    Retorna (validados, descartados).
    Validados mantêm campo 'confianca' ∈ (0, 1].
    Descartados têm confianca == 0.
    """
    if not universo:
        return [], []

    fences = {}
    for campo in ("dy", "pl", "pvp", "roe"):
        vals = [float(ind.get(campo, 0) or 0) for ind in universo
                if float(ind.get(campo, 0) or 0) > 0]
        fences[campo] = _iqr_fence(vals)

    validados, descartados = [], []
    for ind in universo:
        confianca, suspeitos = _validar_ativo(ind, fences)
        ticker = ind.get("ticker", "?")
        if confianca > 0:
            item = dict(ind)
            item["confianca"] = confianca
            if suspeitos:
                item["_avisos_validacao"] = suspeitos
                logger.debug(f"{ticker}: confiança {confianca:.0%} — {'; '.join(suspeitos)}")
            validados.append(item)
        else:
            descartados.append({
                "ticker":    ticker,
                "confianca": confianca,
                "suspeitos": suspeitos,
                "dy":  float(ind.get("dy",  0) or 0),
                "pl":  float(ind.get("pl",  0) or 0),
                "pvp": float(ind.get("pvp", 0) or 0),
                "roe": float(ind.get("roe", 0) or 0),
            })

    return validados, descartados


# ── 2. Cross-validação com BRAPI (2ª fonte para P/L) ─────────────────────────

def _buscar_pl_brapi(tickers: List[str]) -> dict[str, float]:
    """
    Busca P/L de uma lista de tickers via BRAPI em chamadas batch.
    BRAPI aceita múltiplos tickers separados por vírgula em uma chamada.
    Retorna {ticker: pl_brapi}.
    """
    try:
        from apis.brapi import BrapiClient
        client  = BrapiClient()
        pl_map: dict[str, float] = {}

        for i in range(0, len(tickers), BRAPI_BATCH_SIZE):
            batch = tickers[i:i + BRAPI_BATCH_SIZE]
            try:
                quotes = client.get_quotes(batch)
                for q in quotes:
                    sym = q.get("symbol", "").upper()
                    pl  = float(q.get("priceEarnings", 0) or 0)
                    if sym and pl > 0:
                        pl_map[sym] = pl
            except Exception as e:
                logger.debug(f"BRAPI batch {batch}: {e}")

        return pl_map

    except ImportError:
        logger.debug("BrapiClient não disponível para cross-validação")
        return {}
    except Exception as e:
        logger.warning(f"Cross-validação BRAPI falhou: {e}")
        return {}


def validar_com_brapi(candidatos: List[dict]) -> List[dict]:
    """
    Camada 2: cross-validação P/L entre Status Invest e BRAPI.
    Aplicada somente ao top N candidatos (não ao universo inteiro).

    Comportamento:
      - Divergência > 40%: confiança reduzida para 0.7, aviso registrado
      - Divergência > 70%: confiança reduzida para 0.4
      - Consistentes: confiança mantida (ou ligeiramente melhorada se já era 1.0)

    Retorna a mesma lista com campos 'confianca' e '_avisos_validacao' atualizados.
    """
    if not candidatos:
        return candidatos

    tickers = [c["ticker"] for c in candidatos[:BRAPI_CANDIDATES_MAX]]
    pl_brapi = _buscar_pl_brapi(tickers)

    if not pl_brapi:
        logger.debug("Cross-validação BRAPI sem dados — ignorada")
        return candidatos

    for ativo in candidatos:
        ticker = ativo.get("ticker", "")
        si_pl  = float(ativo.get("pl", 0) or 0)
        b_pl   = pl_brapi.get(ticker, 0)

        if si_pl <= 0 or b_pl <= 0:
            continue  # sem dados suficientes para comparar

        divergencia = abs(si_pl - b_pl) / max(si_pl, b_pl)

        if divergencia > 0.70:
            # Alta divergência — dado muito suspeito
            novo_conf = min(ativo.get("confianca", 1.0), 0.4)
            aviso = (f"P/L muito divergente entre fontes: "
                     f"SI={si_pl:.1f} vs BRAPI={b_pl:.1f} "
                     f"({divergencia*100:.0f}% de diferença)")
            logger.debug(f"{ticker}: {aviso}")

        elif divergencia > DIVERGENCIA_PL_MAX:
            # Divergência moderada — suspeito mas não descartado
            novo_conf = min(ativo.get("confianca", 1.0), 0.7)
            aviso = (f"P/L diverge entre fontes: "
                     f"SI={si_pl:.1f} vs BRAPI={b_pl:.1f} "
                     f"({divergencia*100:.0f}% de diferença)")
            logger.debug(f"{ticker}: {aviso}")

        else:
            # Dados consistentes — aumenta confiança marginalmente
            novo_conf = min(1.0, ativo.get("confianca", 1.0) * 1.05)
            aviso = ""

        ativo["confianca"] = novo_conf
        if aviso:
            avisos = ativo.get("_avisos_validacao", [])
            avisos.append(aviso)
            ativo["_avisos_validacao"] = avisos
            # Usa P/L mediano (média dos dois) como valor mais conservador
            ativo["pl"] = (si_pl + b_pl) / 2

    return candidatos


# ── Utilitários ───────────────────────────────────────────────────────────────

def resumo_validacao(descartados: List[dict]) -> str:
    if not descartados:
        return "✅ Todos os ativos passaram na validação de dados."
    linhas = [f"⚠️  {len(descartados)} ativo(s) descartado(s) por dados suspeitos:"]
    for d in descartados[:10]:
        motivos = "; ".join(d.get("suspeitos", []))
        linhas.append(f"   {d['ticker']}: {motivos}")
    if len(descartados) > 10:
        linhas.append(f"   ... e mais {len(descartados) - 10} outros")
    return "\n".join(linhas)