import statistics
from typing import Optional, Tuple, List

LIMITE_IQR   = 3.5
CONF_MINIMA  = 0.5   # confiança mínima para entrar no ranking (0 = excluído)
MAX_DY_ABS   = 30.0
MIN_PVP_ABS  = 0.40
MAX_ROE_ABS  = 200.0
MIN_PL_ABS   = 0.5

def _iqr_fence(valores: List[float]) -> Tuple[Optional[float], Optional[float]]:
    limpos = [v for v in valores if v is not None]
    if len(limpos) < 10:
        return None, None
    q1 = statistics.quantiles(limpos, n=4)[0]
    q3 = statistics.quantiles(limpos, n=4)[2]
    iqr = q3 - q1
    if iqr < 1e-9:
        return None, None
    return q1 - LIMITE_IQR * iqr, q3 + LIMITE_IQR * iqr

def _validar_ativo(ind: dict, fences: dict) -> Tuple[float, List[str]]:
    suspeitos = []
    dy  = float(ind.get("dy",  0) or 0)
    pl  = float(ind.get("pl",  0) or 0)
    pvp = float(ind.get("pvp", 0) or 0)
    roe = float(ind.get("roe", 0) or 0)

    if dy > MAX_DY_ABS:
        suspeitos.append(f"DY={dy:.1f}% acima do limite absoluto ({MAX_DY_ABS}%)")
    else:
        lo, hi = fences.get("dy", (None, None))
        if hi is not None and dy > hi:
            suspeitos.append(f"DY={dy:.1f}% acima da fence estatística ({hi:.1f}%)")

    if 0 < pl < MIN_PL_ABS:
        suspeitos.append(f"P/L={pl:.2f} suspeito (artefato de divisão)")
    elif pl > 0:
        lo, hi = fences.get("pl", (None, None))
        if hi is not None and pl > hi:
            suspeitos.append(f"P/L={pl:.1f} acima da fence ({hi:.1f})")
        if lo is not None and lo > 0.5 and pl < lo:
            suspeitos.append(f"P/L={pl:.1f} abaixo da fence ({lo:.1f})")

    if 0 < pvp < MIN_PVP_ABS:
        suspeitos.append(f"P/VP={pvp:.3f} abaixo do limite absoluto ({MIN_PVP_ABS})")
    elif pvp > 0:
        lo, hi = fences.get("pvp", (None, None))
        if hi is not None and pvp > hi:
            suspeitos.append(f"P/VP={pvp:.2f} acima da fence ({hi:.2f})")

    if roe > MAX_ROE_ABS:
        suspeitos.append(f"ROE={roe:.1f}% acima do limite absoluto ({MAX_ROE_ABS}%)")
    elif roe > 0:
        lo, hi = fences.get("roe", (None, None))
        if hi is not None and roe > hi:
            suspeitos.append(f"ROE={roe:.1f}% acima da fence ({hi:.1f}%)")

    n = len(suspeitos)
    if n == 0:
        confianca = 1.0
    elif n == 1:
        confianca = 0.7
    elif n == 2:
        confianca = 0.4
    else:
        confianca = 0.0
    return confianca, suspeitos

def validar_universo(universo: List[dict]) -> Tuple[List[dict], List[dict]]:
    """
    Retorna (validados, descartados).
    validados mantém todos com confianca > 0, com campo 'confianca'.
    descartados são os com confianca == 0.
    """
    if not universo:
        return [], []

    campos = ["dy", "pl", "pvp", "roe"]
    fences = {}
    for campo in campos:
        if campo == "pl":
            vals = [float(ind.get("pl", 0) or 0) for ind in universo if float(ind.get("pl", 0) or 0) > 0]
        else:
            vals = [float(ind.get(campo, 0) or 0) for ind in universo if float(ind.get(campo, 0) or 0) > 0]
        fences[campo] = _iqr_fence(vals)

    validados = []
    descartados = []
    for ind in universo:
        confianca, suspeitos = _validar_ativo(ind, fences)
        ticker = ind.get("ticker", "?")
        if confianca > 0:
            item = dict(ind)
            item["confianca"] = confianca
            if suspeitos:
                item["_avisos_validacao"] = suspeitos
            validados.append(item)
        else:
            descartados.append({
                "ticker": ticker,
                "confianca": confianca,
                "suspeitos": suspeitos,
                "dy": float(ind.get("dy", 0) or 0),
                "pl": float(ind.get("pl", 0) or 0),
                "pvp": float(ind.get("pvp", 0) or 0),
                "roe": float(ind.get("roe", 0) or 0),
            })
    return validados, descartados

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