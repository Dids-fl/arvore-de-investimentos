"""
Taxas e scores de Renda Fixa e Fundos derivados de dados reais de mercado.
(versão fixa – usada como fallback quando a busca dinâmica falha)
"""

from __future__ import annotations
from typing import Optional


# ── Spreads e parâmetros de produto ───────────────────────────────────────────
CDB_SPREAD     = 1.15
LCI_LCA_IR_EQ  = 0.175
IPCA_SPREAD_TD  = 0.055
IPCA_SPREAD_DEBN= 0.065
IPCA_SPREAD_CRI = 0.070
CUSTÓDIA_B3    = 0.002
COME_COTAS_RF   = 0.003
COME_COTAS_MM   = 0.005
IR_LONG_PRAZO   = 0.15


def _retorno_liquido_real(ret_bruto: float, deducoes: float,
                          ir: float, ipca: float,
                          isento_ir: bool = False) -> float:
    ganho = ret_bruto - deducoes
    if isento_ir:
        ret_liq = ganho
    else:
        ret_liq = deducoes + ganho * (1 - ir)
    return (1 + ret_liq) / (1 + ipca) - 1


def calcular_rf(selic: float, ipca: float,
                ibov_cagr: Optional[float] = None) -> list[dict]:
    cdi = selic - 0.001
    produtos = []

    # Tesouro Selic
    ret_ts = cdi - CUSTÓDIA_B3
    rlr_ts = _retorno_liquido_real(ret_ts, 0, IR_LONG_PRAZO, ipca)
    produtos.append({
        "ticker":  "SELIC",
        "nome":    "Tesouro Selic",
        "ret_bruto_pct": round(ret_ts * 100, 2),
        "ret_real_pct":  round(rlr_ts * 100, 2),
        "garantia":      "Governo federal",
        "liquidez":      "D+1",
        "ir":            "15% sobre ganhos (>720 dias)",
        "score":         0,
        "motivos":       [],
        "_bonus_seg":    8,
        "_bonus_liq":    4,
        "_isento":       False,
        "_ret_liq_real": rlr_ts,
    })

    # CDB DI
    ret_cdb = cdi * CDB_SPREAD
    rlr_cdb = _retorno_liquido_real(ret_cdb, 0, IR_LONG_PRAZO, ipca)
    produtos.append({
        "ticker":  "CDB-DI",
        "nome":    f"CDB {CDB_SPREAD*100:.0f}% CDI (banco digital)",
        "ret_bruto_pct": round(ret_cdb * 100, 2),
        "ret_real_pct":  round(rlr_cdb * 100, 2),
        "garantia":      "FGC até R$250k",
        "liquidez":      "Diária",
        "ir":            "15% sobre ganhos (>720 dias)",
        "score":         0,
        "motivos":       [],
        "_bonus_seg":    5,
        "_bonus_liq":    4,
        "_isento":       False,
        "_ret_liq_real": rlr_cdb,
    })

    # LCI/LCA
    ret_lci_equiv = cdi * CDB_SPREAD * (1 - LCI_LCA_IR_EQ)
    rlr_lci = (1 + ret_lci_equiv) / (1 + ipca) - 1
    produtos.append({
        "ticker":  "LCI/LCA",
        "nome":    "LCI / LCA (banco sólido)",
        "ret_bruto_pct": round(ret_lci_equiv * 100, 2),
        "ret_real_pct":  round(rlr_lci * 100, 2),
        "garantia":      "FGC até R$250k",
        "liquidez":      "Carência mínima",
        "ir":            "ISENTO de IR",
        "score":         0,
        "motivos":       [],
        "_bonus_seg":    5,
        "_bonus_liq":    2,
        "_isento":       True,
        "_ret_liq_real": rlr_lci,
    })

    # IPCA+
    spread_ipca = IPCA_SPREAD_TD * (1 + max(0, selic - 0.10) * 2)
    spread_ipca = min(spread_ipca, 0.075)
    ret_ipca = ipca + spread_ipca
    rlr_ipca = _retorno_liquido_real(ret_ipca - ipca, 0, IR_LONG_PRAZO, 0)
    produtos.append({
        "ticker":  "IPCA+",
        "nome":    f"Tesouro IPCA+ ({ipca*100:.1f}% + {spread_ipca*100:.1f}%)",
        "ret_bruto_pct": round(ret_ipca * 100, 2),
        "ret_real_pct":  round(spread_ipca * (1 - IR_LONG_PRAZO) * 100, 2),
        "garantia":      "Governo federal",
        "liquidez":      "D+1 (MtM)",
        "ir":            "15% sobre ganho real",
        "score":         0,
        "motivos":       [],
        "_bonus_seg":    8,
        "_bonus_liq":    3,
        "_isento":       False,
        "_ret_liq_real": spread_ipca * (1 - IR_LONG_PRAZO),
    })

    # Debênture incentivada
    spread_debn = IPCA_SPREAD_DEBN * (1 + max(0, selic - 0.10) * 1.5)
    spread_debn = min(spread_debn, 0.085)
    rlr_debn = spread_debn
    produtos.append({
        "ticker":  "DEBN",
        "nome":    f"Debênture incentivada (IPCA+ {spread_debn*100:.1f}%)",
        "ret_bruto_pct": round((ipca + spread_debn) * 100, 2),
        "ret_real_pct":  round(rlr_debn * 100, 2),
        "garantia":      "Sem FGC — risco do emissor",
        "liquidez":      "Secundária (restrita)",
        "ir":            "ISENTO de IR (Lei 12.431)",
        "score":         0,
        "motivos":       [],
        "_bonus_seg":    0,
        "_bonus_liq":    0,
        "_isento":       True,
        "_ret_liq_real": rlr_debn,
    })

    # CRI/CRA
    spread_cri = IPCA_SPREAD_CRI * (1 + max(0, selic - 0.10) * 1.5)
    spread_cri = min(spread_cri, 0.090)
    rlr_cri = spread_cri
    produtos.append({
        "ticker":  "CRI/CRA",
        "nome":    f"CRI / CRA (IPCA+ {spread_cri*100:.1f}%)",
        "ret_bruto_pct": round((ipca + spread_cri) * 100, 2),
        "ret_real_pct":  round(rlr_cri * 100, 2),
        "garantia":      "Sem FGC — lastro imobiliário/agro",
        "liquidez":      "Secundária (restrita)",
        "ir":            "ISENTO de IR",
        "score":         0,
        "motivos":       [],
        "_bonus_seg":    2,
        "_bonus_liq":    0,
        "_isento":       True,
        "_ret_liq_real": rlr_cri,
    })

    # Score
    for p in produtos:
        rlr = p["_ret_liq_real"]
        score = round(rlr * 100 * 6 + p["_bonus_seg"] + p["_bonus_liq"], 1)
        score = max(0.0, min(100.0, score))
        p["score"] = score

        motivos = []
        if p["_isento"]:
            motivos.append(f"✅ Isento de IR — retorno real líquido: {rlr*100:.2f}% a.a.")
        else:
            motivos.append(f"ℹ️  Retorno real líquido: {rlr*100:.2f}% a.a. (após IR e IPCA {ipca*100:.1f}%)")

        if "FGC" in p["garantia"]:
            motivos.append(f"✅ {p['garantia']}")
        elif "Governo" in p["garantia"]:
            motivos.append(f"✅ {p['garantia']}")
        else:
            motivos.append(f"⚠️  {p['garantia']}")

        motivos.append(f"💧 Liquidez: {p['liquidez']}")
        motivos.append(f"📋 IR: {p['ir']}")
        p["motivos"] = motivos[:4]

        for k in ["_bonus_seg", "_bonus_liq", "_isento", "_ret_liq_real"]:
            del p[k]

    return sorted(produtos, key=lambda x: -x["score"])


def calcular_fundos(selic: float, ipca: float,
                    ibov_cagr: Optional[float] = None) -> list[dict]:
    cdi = selic - 0.001
    ibov = ibov_cagr if ibov_cagr else 0.13

    fundos = []

    # Fundo RF DI
    ret_fdo_rf = cdi * 0.99 - 0.005 - COME_COTAS_RF
    rlr_fdo_rf = (1 + ret_fdo_rf) / (1 + ipca) - 1
    fundos.append({
        "ticker": "FDO-RF",
        "nome":   f"Fundo RF DI — taxa admin 0.5% (CDI×99% − 0.8%)",
        "ret_bruto_pct": round(ret_fdo_rf * 100, 2),
        "ret_real_pct":  round(rlr_fdo_rf * 100, 2),
        "_rlr":   rlr_fdo_rf,
        "_seg":   4,
        "_liq":   4,
        "alerta": "Come-cotas maio/nov reduz retorno efetivo",
        "onde":   "XP, BTG, Rico (taxa admin <0.5%)",
    })

    # Multimercado
    ret_mm_bruto = cdi + 0.02
    perf_efetiva = max(0, (ret_mm_bruto - cdi) * 0.20)
    ret_mm = ret_mm_bruto - 0.015 - perf_efetiva - COME_COTAS_MM
    rlr_mm = (1 + ret_mm) / (1 + ipca) - 1
    fundos.append({
        "ticker": "FDO-MULTI",
        "nome":   f"Multimercado macro — CDI+2% gross, admin 1.5%",
        "ret_bruto_pct": round(ret_mm * 100, 2),
        "ret_real_pct":  round(rlr_mm * 100, 2),
        "_rlr":   rlr_mm,
        "_seg":   3,
        "_liq":   3,
        "alerta": "Come-cotas semestral — gestoras: SPX, Verde, Ibiúna, Kinea",
        "onde":   "XP, BTG, Órama (aporte mínimo varia)",
    })

    # Debêntures Incentivadas
    spread_fdo_debn = IPCA_SPREAD_DEBN * (1 + max(0, selic - 0.10) * 1.5)
    spread_fdo_debn = min(spread_fdo_debn, 0.085)
    ret_fdo_debn = ipca + spread_fdo_debn - 0.008
    rlr_fdo_debn = (1 + ret_fdo_debn) / (1 + ipca) - 1
    fundos.append({
        "ticker": "FDO-DEBN",
        "nome":   f"Fundo Debêntures Incentivadas — IPCA+{spread_fdo_debn*100:.1f}% líq.",
        "ret_bruto_pct": round(ret_fdo_debn * 100, 2),
        "ret_real_pct":  round(rlr_fdo_debn * 100, 2),
        "_rlr":   rlr_fdo_debn,
        "_seg":   2,
        "_liq":   2,
        "alerta": "Isento IR para cotista — diversifica crédito privado",
        "onde":   "XP, BTG, Órama",
    })

    # Previdência
    ret_prev_bruto    = cdi * 0.95 - 0.008
    vantagem_cc       = COME_COTAS_RF * (1 + ret_prev_bruto) * 0.5
    ret_prev_efetivo  = ret_prev_bruto + vantagem_cc
    rlr_prev = ((1 + ret_prev_efetivo) * (1 - 0.10)) / (1 + ipca) - 1
    fundos.append({
        "ticker": "FDO-PREV",
        "nome":   "VGBL/PGBL RF — sem come-cotas, IR 10% (>10 anos)",
        "ret_bruto_pct": round(ret_prev_efetivo * 100, 2),
        "ret_real_pct":  round(rlr_prev * 100, 2),
        "_rlr":   rlr_prev,
        "_seg":   4,
        "_liq":   1,
        "alerta": "Portabilidade sem IR entre planos; PGBL deduz 12% renda bruta",
        "onde":   "Icatu, XP Seguros, Zurich (taxa carregamento ZERO)",
    })

    # Long biased
    ret_lb_bruto = ibov * 0.70 + cdi * 0.30
    ret_lb = ret_lb_bruto - 0.02 - COME_COTAS_MM
    rlr_lb = (1 + ret_lb) / (1 + ipca) - 1
    fundos.append({
        "ticker": "FDO-LONG",
        "nome":   f"Long biased ({ibov*100:.1f}%×70% + CDI×30% − 2%)",
        "ret_bruto_pct": round(ret_lb * 100, 2),
        "ret_real_pct":  round(rlr_lb * 100, 2),
        "_rlr":   rlr_lb,
        "_seg":   1,
        "_liq":   2,
        "alerta": "Exposição direcional a ações — volatilidade alta",
        "onde":   "Gestoras: Kapitalo, Vinland, Constellation",
    })

    # IVVB11
    ret_ivvb = 0.155 - 0.0024
    rlr_ivvb = (1 + ret_ivvb) / (1 + ipca) - 1
    fundos.append({
        "ticker": "IVVB11",
        "nome":   "IVVB11 — S&P 500 BRL (taxa 0.24% a.a.)",
        "ret_bruto_pct": round(ret_ivvb * 100, 2),
        "ret_real_pct":  round(rlr_ivvb * 100, 2),
        "_rlr":   rlr_ivvb,
        "_seg":   2,
        "_liq":   4,
        "alerta": "Risco cambial: lucra com alta do dólar, perde com queda",
        "onde":   "Qualquer corretora (ETF de bolsa)",
    })

    # Score
    for f in fundos:
        rlr   = f["_rlr"]
        score = round(rlr * 100 * 5 + f["_seg"] + f["_liq"], 1)
        score = max(15.0 if f["ticker"] == "FDO-PREV" else 0.0, min(100.0, score))
        f["score"] = score

        motivos = []
        sinal = "✅" if rlr > 0.05 else ("ℹ️ " if rlr > 0.02 else "⚠️ ")
        motivos.append(f"{sinal} Retorno real estimado: {rlr*100:.2f}% a.a. (líq. de taxa e IPCA)")
        motivos.append(f"ℹ️  Retorno bruto estimado: {f['ret_bruto_pct']:.2f}% a.a.")
        motivos.append(f"ℹ️  {f['alerta']}")
        motivos.append(f"🏦 {f['onde']}")
        f["motivos"] = motivos

        for k in ["_rlr", "_seg", "_liq", "alerta", "onde"]:
            del f[k]

    return sorted(fundos, key=lambda x: -x["score"])