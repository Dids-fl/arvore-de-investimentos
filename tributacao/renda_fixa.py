"""Tributação estimada de renda fixa por prazo."""

from __future__ import annotations

from tributacao.base import (
    ContextoTributario,
    PrecisaoTributaria,
    ResultadoTributario,
    resultado_calculado,
)
from tributacao.regras import (
    FONTE_RECEITA_RENDIMENTOS_CAPITAL,
    IOF_RENDA_FIXA_DIAS,
    VIGENCIA_BASE,
    aliquota_rf,
)

ISENTOS_PF = {
    "lci",
    "lca",
    "cri",
    "cra",
    "debenture_incentivada",
}


def calcular_renda_fixa(
    contexto: ContextoTributario,
) -> ResultadoTributario:
    if contexto.tipo_produto in ISENTOS_PF and contexto.pessoa_fisica:
        return resultado_calculado(
            contexto,
            imposto=0.0,
            aliquota=0.0,
            precisao=PrecisaoTributaria.EXATA_PARA_PREMISSAS,
            premissas=(
                "Pessoa física e produto identificado como isento.",
                "Não foram considerados custos ou desenquadramento do produto.",
            ),
            fonte=FONTE_RECEITA_RENDIMENTOS_CAPITAL,
            vigencia=VIGENCIA_BASE,
            regra_id="rf_isenta_pf_2026",
        )

    ganho = contexto.ganho
    aliquota_ir = aliquota_rf(contexto.prazo_dias)
    aliquota_iof = IOF_RENDA_FIXA_DIAS.get(contexto.prazo_dias, 0.0)
    iof = ganho * aliquota_iof
    base_ir = max(0.0, ganho - iof)
    ir = base_ir * aliquota_ir
    imposto = iof + ir

    return resultado_calculado(
        contexto,
        imposto=imposto,
        aliquota=(imposto / ganho if ganho else 0.0),
        precisao=PrecisaoTributaria.EXATA_PARA_PREMISSAS,
        premissas=(
            "IR calculado sobre o rendimento positivo.",
            "IOF regressivo aplicado quando o resgate ocorre antes de 30 dias.",
            "Perdas, compensações e custos não foram considerados.",
        ),
        fonte=FONTE_RECEITA_RENDIMENTOS_CAPITAL,
        vigencia=VIGENCIA_BASE,
        regra_id="rf_regressiva_2026",
    )
