"""
Validador de dados fundamentalistas.

Problema resolvido
──────────────────
O Status Invest às vezes retorna outliers graves — DY 33% quando o real é 8%,
P/L 1.4 quando o real é ~9, P/VP 0.31 quando o real é ~1.1. Esses dados
distorcidos inflam o score e empurram ações suspeitas para o topo do ranking.

Abordagem: validação estatística intra-universo
───────────────────────────────────────────────
Não dependemos de uma segunda API (BRAPI bloqueada no env de produção,
Fundamentus inacessível externamente). Em vez disso, usamos o próprio
universo retornado pelo Status Invest para calcular mediana e IQR de cada
campo — e descartamos ativos cujos valores fogem mais de LIMITE_IQR × IQR
da mediana (fence do box-plot de Tukey ampliado).

Lógica por campo
────────────────
  dy  — valores acima de MAX_DY_ABS (30%) são suspeitos mesmo sem contexto
         estatístico (nenhuma ação saudável paga 30%+ de dividendo em base
         recorrente; se aparecer, é retroativo, evento único ou erro de dado)
  pl  — valores negativos passam (prejuízo real); mas pl muito próximo de 0
         (0 < pl < 0.5) são ruins (artefato de divisão) e removidos
  pvp — valor < 0.10 é quase sempre erro (empresa não vale 90% a menos do
         que o patrimônio contábil sem ser insolvente)
  roe — ROE > 100% pode ser real (bancos alavancados, empresas de capital
         mínimo) mas ROE > 200% é sinal de erro de dado

Confiança
─────────
  Cada ativo recebe um score de confiança [0.0, 1.0]:
    1.0 — todos os campos dentro dos limites
    0.7 — 1 campo suspeito
    0.4 — 2 campos suspeitos
    0.0 — 3+ campos suspeitos → ativo excluído do ranking

Uso no screener
───────────────
  universo_validado, relatorio = validar_universo(universo)
  # universo_validado contém apenas ativos com confiança >= CONF_MINIMA
  # relatorio lista os descartados e o motivo
"""

import statistics
from typing import Optional

# ── Constantes de validação ───────────────────────────────────────────────────

LIMITE_IQR   = 3.5      # multiplica o IQR para definir a fence superior/inferior
CONF_MINIMA  = 0.5      # confiança mínima para entrar no ranking

# Limites absolutos independentes do universo
MAX_DY_ABS   = 30.0     # DY acima de 30% é suspeito
MIN_PVP_ABS  = 0.40     # P/VP abaixo de 0.40 é suspeito (empresa listada e líquida não vale 60% abaixo do patrimônio sem ser insolvente)
MAX_ROE_ABS  = 200.0    # ROE acima de 200% é suspeito
MIN_PL_ABS   = 0.5      # P/L entre 0 e 0.5 é artefato de divisão


def _iqr_fence(valores: list[float]) -> tuple[Optional[float], Optional[float]]:
    """
    Calcula a fence de Tukey ampliada: [Q1 - k*IQR, Q3 + k*IQR].
    Retorna (lower, upper). None se não houver dados suficientes.
    """
    limpos = [v for v in valores if v is not None]
    if len(limpos) < 10:
        return None, None
    q1 = statistics.quantiles(limpos, n=4)[0]   # 25%
    q3 = statistics.quantiles(limpos, n=4)[2]   # 75%
    iqr = q3 - q1
    if iqr < 1e-9:
        return None, None
    return q1 - LIMITE_IQR * iqr, q3 + LIMITE_IQR * iqr


def _validar_ativo(ind: dict, fences: dict[str, tuple]) -> tuple[float, list[str]]:
    """
    Valida um ativo contra os limites estatísticos do universo.
    Retorna (confiança, lista de motivos de suspeita).
    """
    suspeitos: list[str] = []

    dy  = float(ind.get("dy",  0) or 0)
    pl  = float(ind.get("pl",  0) or 0)
    pvp = float(ind.get("pvp", 0) or 0)
    roe = float(ind.get("roe", 0) or 0)

    # ── DY ────────────────────────────────────────────────────────────────────
    if dy > MAX_DY_ABS:
        suspeitos.append(f"DY={dy:.1f}% acima do limite absoluto ({MAX_DY_ABS}%)")
    else:
        lo, hi = fences.get("dy", (None, None))
        if hi is not None and dy > hi:
            suspeitos.append(f"DY={dy:.1f}% acima da fence estatística ({hi:.1f}%)")

    # ── P/L ───────────────────────────────────────────────────────────────────
    if 0 < pl < MIN_PL_ABS:
        suspeitos.append(f"P/L={pl:.2f} suspeito (artefato de divisão: 0 < PL < {MIN_PL_ABS})")
    elif pl > 0:
        lo, hi = fences.get("pl", (None, None))
        if hi is not None and pl > hi:
            suspeitos.append(f"P/L={pl:.1f} acima da fence estatística ({hi:.1f})")
        # Fence inferior do P/L: valor abaixo do Q1−IQR é suspeito
        # (ex: P/L=1.4 quando a mediana é ~10 dispara esse alerta)
        if lo is not None and lo > 0.5 and pl < lo:
            suspeitos.append(f"P/L={pl:.1f} abaixo da fence estatística ({lo:.1f}) — possível erro de dado")

    # ── P/VP ──────────────────────────────────────────────────────────────────
    if 0 < pvp < MIN_PVP_ABS:
        suspeitos.append(f"P/VP={pvp:.3f} abaixo do limite absoluto ({MIN_PVP_ABS})")
    elif pvp > 0:
        lo, hi = fences.get("pvp", (None, None))
        if hi is not None and pvp > hi:
            suspeitos.append(f"P/VP={pvp:.2f} acima da fence estatística ({hi:.2f})")

    # ── ROE ───────────────────────────────────────────────────────────────────
    if roe > MAX_ROE_ABS:
        suspeitos.append(f"ROE={roe:.1f}% acima do limite absoluto ({MAX_ROE_ABS}%)")
    elif roe > 0:
        lo, hi = fences.get("roe", (None, None))
        if hi is not None and roe > hi:
            suspeitos.append(f"ROE={roe:.1f}% acima da fence estatística ({hi:.1f}%)")

    # ── Confiança final ───────────────────────────────────────────────────────
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


def validar_universo(
    universo: list[dict],
    campo_ticker: str = "ticker",
) -> tuple[list[dict], list[dict]]:
    """
    Valida estatisticamente o universo de ações.

    Parâmetros
    ──────────
      universo     — lista de dicts com campos dy, pl, pvp, roe
      campo_ticker — nome do campo que contém o ticker (padrão: "ticker")

    Retorna
    ───────
      (validados, descartados)

      validados   — lista com campo extra "confianca" (float 0-1)
      descartados — lista com campos "ticker", "confianca", "suspeitos" (list[str])
    """
    if not universo:
        return [], []

    # ── Calcula fences do universo ────────────────────────────────────────────
    campos = ["dy", "pl", "pvp", "roe"]
    fences: dict[str, tuple] = {}

    for campo in campos:
        # P/L: considera apenas valores positivos para a estatística
        # (pl negativo = prejuízo real, não outlier de dado)
        if campo == "pl":
            vals = [float(ind.get("pl", 0) or 0)
                    for ind in universo
                    if float(ind.get("pl", 0) or 0) > 0]
        else:
            vals = [float(ind.get(campo, 0) or 0)
                    for ind in universo
                    if float(ind.get(campo, 0) or 0) > 0]

        fences[campo] = _iqr_fence(vals)

    # ── Valida cada ativo ─────────────────────────────────────────────────────
    validados:   list[dict] = []
    descartados: list[dict] = []

    for ind in universo:
        confianca, suspeitos = _validar_ativo(ind, fences)
        ticker = ind.get(campo_ticker, "?")

        if confianca >= CONF_MINIMA:
            item = dict(ind)
            item["confianca"] = confianca
            # Campos suspeitos ficam marcados, mas o ativo não é excluído
            if suspeitos:
                item["_avisos_validacao"] = suspeitos
            validados.append(item)
        else:
            descartados.append({
                "ticker":     ticker,
                "confianca":  confianca,
                "suspeitos":  suspeitos,
                "dy":         float(ind.get("dy",  0) or 0),
                "pl":         float(ind.get("pl",  0) or 0),
                "pvp":        float(ind.get("pvp", 0) or 0),
                "roe":        float(ind.get("roe", 0) or 0),
            })

    return validados, descartados


def resumo_validacao(descartados: list[dict]) -> str:
    """Formata um resumo legível dos ativos descartados."""
    if not descartados:
        return "✅ Todos os ativos passaram na validação de dados."

    linhas = [f"⚠️  {len(descartados)} ativo(s) descartado(s) por dados suspeitos:"]
    for d in descartados[:10]:   # mostra no máximo 10
        motivos = "; ".join(d.get("suspeitos", []))
        linhas.append(f"   {d['ticker']}: {motivos}")
    if len(descartados) > 10:
        linhas.append(f"   ... e mais {len(descartados) - 10} outros")

    return "\n".join(linhas)
