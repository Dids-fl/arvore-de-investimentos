"""Tributação estimada de renda fixa por prazo e elegibilidade."""

from __future__ import annotations

from tributacao.base import (
    ContextoTributario,
    PrecisaoTributaria,
    ResultadoTributario,
    resultado_calculado,
    resultado_indeterminado,
)
from tributacao.regras import (
    FONTE_LEI_11033_ISENCOES,
    FONTE_LEI_12431_DEBENTURES,
    FONTE_RECEITA_RENDIMENTOS_CAPITAL,
    IOF_RENDA_FIXA_DIAS,
    VIGENCIA_BASE,
    aliquota_rf,
)

ISENTOS_PF_DIRETOS = {"lci", "lca"}
ISENTOS_PF_CONDICIONAIS = {
    "cri",
    "cra",
    "debenture_incentivada",
}


def _fonte_isencao(tipo_produto: str) -> str:
    if tipo_produto == "debenture_incentivada":
        return FONTE_LEI_12431_DEBENTURES
    return FONTE_LEI_11033_ISENCOES


def _elegibilidade_confirmada(contexto: ContextoTributario) -> bool:
    valor = contexto.metadados.get(
        "elegibilidade_isencao_confirmada",
        False,
    )
    if not isinstance(valor, bool):
        raise TypeError(
            "elegibilidade_isencao_confirmada deve ser booleano."
        )
    return valor


def _resultado_isento(
    contexto: ContextoTributario,
    *,
    elegibilidade_condicional: bool,
) -> ResultadoTributario:
    premissas = [
        "Pessoa física e produto identificado como isento.",
        "Não foram considerados custos ou desenquadramento do produto.",
    ]
    if elegibilidade_condicional:
        premissas.append(
            "A elegibilidade legal do instrumento foi confirmada externamente."
        )
    return resultado_calculado(
        contexto,
        imposto=0.0,
        aliquota=0.0,
        precisao=PrecisaoTributaria.EXATA_PARA_PREMISSAS,
        premissas=tuple(premissas),
        fonte=_fonte_isencao(contexto.tipo_produto),
        vigencia=VIGENCIA_BASE,
        regra_id="rf_isenta_pf_2026",
    )


def calcular_renda_fixa(
    contexto: ContextoTributario,
) -> ResultadoTributario:
    tipo = contexto.tipo_produto
    if tipo in ISENTOS_PF_DIRETOS:
        return _resultado_isento(
            contexto,
            elegibilidade_condicional=False,
        )

    if tipo in ISENTOS_PF_CONDICIONAIS:
        if not _elegibilidade_confirmada(contexto):
            return resultado_indeterminado(
                contexto,
                motivo=(
                    "Confirme a elegibilidade legal do instrumento para "
                    "aplicar a isenção de pessoa física."
                ),
                fonte=_fonte_isencao(tipo),
                vigencia=VIGENCIA_BASE,
                regra_id="rf_isencao_elegibilidade_indeterminada",
            )
        return _resultado_isento(
            contexto,
            elegibilidade_condicional=True,
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
