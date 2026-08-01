"""Estimativa conservadora para ganho de capital em criptoativos."""

from __future__ import annotations

from tributacao.base import (
    ContextoTributario,
    PrecisaoTributaria,
    ResultadoTributario,
    resultado_calculado,
    resultado_indeterminado,
)
from tributacao.regras import (
    FONTE_RECEITA_GANHO_CAPITAL,
    FONTE_RFB_APLICACOES_FINANCEIRAS_EXTERIOR,
    IRPF_APLICACOES_FINANCEIRAS_EXTERIOR,
    VIGENCIA_BASE,
    imposto_ganho_capital,
)


def _premissa_confirmada(
    contexto: ContextoTributario,
    chave: str,
) -> bool:
    """Lê uma confirmação explícita sem aceitar strings truthy."""
    valor = contexto.metadados.get(chave, False)
    if not isinstance(valor, bool):
        raise TypeError(f"{chave} deve ser booleano.")
    return valor


def _calcular_exterior(
    contexto: ContextoTributario,
) -> ResultadoTributario:
    """Estima aplicação financeira exterior somente após enquadramento."""
    chave_enquadramento = (
        "enquadramento_aplicacao_financeira_exterior_confirmado"
    )
    if not _premissa_confirmada(contexto, chave_enquadramento):
        return resultado_indeterminado(
            contexto,
            motivo=(
                "Custódia ou negociação no exterior não comprova, sozinha, "
                "o enquadramento como aplicação financeira no exterior."
            ),
            fonte=FONTE_RFB_APLICACOES_FINANCEIRAS_EXTERIOR,
            vigencia=VIGENCIA_BASE,
            regra_id="cripto_exterior_enquadramento_indeterminado",
        )

    imposto = contexto.ganho * IRPF_APLICACOES_FINANCEIRAS_EXTERIOR
    aliquota = (
        IRPF_APLICACOES_FINANCEIRAS_EXTERIOR
        if contexto.ganho
        else 0.0
    )
    return resultado_calculado(
        contexto,
        imposto=imposto,
        aliquota=aliquota,
        precisao=PrecisaoTributaria.ESTIMADA,
        premissas=(
            "Custódia ou negociação no exterior informada.",
            "Enquadramento como aplicação financeira exterior confirmado.",
            (
                "Alíquota anual de 15%; imposto pago no exterior, perdas, "
                "offshore e compensações exigem análise própria."
            ),
            "O valor líquido é projeção econômica, não retenção no resgate.",
        ),
        fonte=FONTE_RFB_APLICACOES_FINANCEIRAS_EXTERIOR,
        vigencia=VIGENCIA_BASE,
        regra_id="cripto_aplicacao_financeira_exterior_2026",
    )


def _calcular_brasil(
    contexto: ContextoTributario,
) -> ResultadoTributario:
    """Estima ganho de capital doméstico com agregação condicionada."""
    acumulado_informado = "ganho_acumulado_ano" in contexto.metadados
    if acumulado_informado and not _premissa_confirmada(
        contexto,
        "alienacoes_parciais_mesmo_bem_confirmadas",
    ):
        return resultado_indeterminado(
            contexto,
            motivo=(
                "Ganho acumulado exige confirmar alienações parciais do "
                "mesmo bem ou direito e o período legal aplicável."
            ),
            fonte=FONTE_RECEITA_GANHO_CAPITAL,
            vigencia=VIGENCIA_BASE,
            regra_id="cripto_acumulacao_indeterminada",
        )

    ganho_acumulado = float(
        contexto.metadados.get(
            "ganho_acumulado_ano",
            contexto.ganho,
        )
    )
    if ganho_acumulado < 0:
        raise ValueError("ganho_acumulado_ano não pode ser negativo.")
    if ganho_acumulado < contexto.ganho:
        raise ValueError(
            "ganho_acumulado_ano não pode ser menor que o ganho atual."
        )

    ganho_anterior = ganho_acumulado - contexto.ganho
    imposto = (
        imposto_ganho_capital(ganho_acumulado)
        - imposto_ganho_capital(ganho_anterior)
    )
    aliquota = imposto / contexto.ganho if contexto.ganho else 0.0
    premissas = [
        "Custódia no Brasil informada.",
        "Custo de aquisição e ganho foram fornecidos.",
        "Permutas, staking, isenções e compensações exigem análise própria.",
    ]
    if acumulado_informado:
        premissas.append(
            "Alienações parciais do mesmo bem e período legal confirmados."
        )

    return resultado_calculado(
        contexto,
        imposto=imposto,
        aliquota=aliquota,
        precisao=PrecisaoTributaria.ESTIMADA,
        premissas=tuple(premissas),
        fonte=FONTE_RECEITA_GANHO_CAPITAL,
        vigencia=VIGENCIA_BASE,
        regra_id="cripto_ganho_capital_brasil_2026",
    )


def calcular_cripto(contexto: ContextoTributario) -> ResultadoTributario:
    """Seleciona o regime sem inferir enquadramentos ausentes."""
    custodia = contexto.metadados.get("jurisdicao_custodia")
    if custodia not in {"brasil", "exterior"}:
        return resultado_indeterminado(
            contexto,
            motivo=(
                "Informe jurisdicao_custodia como brasil ou exterior; "
                "o enquadramento pode mudar."
            ),
            fonte=FONTE_RECEITA_GANHO_CAPITAL,
            vigencia=VIGENCIA_BASE,
            regra_id="cripto_jurisdicao_indeterminada",
        )

    if _premissa_confirmada(contexto, "isencao_confirmada"):
        return resultado_calculado(
            contexto,
            imposto=0.0,
            aliquota=0.0,
            precisao=PrecisaoTributaria.ESTIMADA,
            premissas=(
                "A aplicabilidade da isenção foi confirmada externamente.",
                "O motor não decidiu automaticamente o limite de isenção.",
            ),
            fonte=FONTE_RECEITA_GANHO_CAPITAL,
            vigencia=VIGENCIA_BASE,
            regra_id="cripto_isencao_informada_2026",
        )

    if custodia == "exterior":
        return _calcular_exterior(contexto)
    return _calcular_brasil(contexto)