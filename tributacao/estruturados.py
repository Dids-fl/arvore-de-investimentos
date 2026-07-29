"""Tributação por subtipo de produto estruturado."""

from __future__ import annotations

from tributacao.base import (
    ContextoTributario,
    ResultadoTributario,
    resultado_indeterminado,
)
from tributacao.regras import FONTE_RECEITA_RENDIMENTOS_CAPITAL, VIGENCIA_BASE
from tributacao.renda_fixa import calcular_renda_fixa


def calcular_estruturado(
    contexto: ContextoTributario,
) -> ResultadoTributario:
    if contexto.tipo_produto in {
        "coe",
        "cri",
        "cra",
        "debenture_incentivada",
        "debenture_comum",
    }:
        return calcular_renda_fixa(contexto)
    return resultado_indeterminado(
        contexto,
        motivo=(
            "Produtos estruturados não podem compartilhar uma alíquota única. "
            "Informe COE, CRI, CRA, debênture incentivada ou comum."
        ),
        fonte=FONTE_RECEITA_RENDIMENTOS_CAPITAL,
        vigencia=VIGENCIA_BASE,
        regra_id="estruturado_subtipo_indeterminado",
    )
