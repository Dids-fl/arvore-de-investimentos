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
    VIGENCIA_BASE,
    imposto_ganho_capital,
)


def calcular_cripto(contexto: ContextoTributario) -> ResultadoTributario:
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

    if bool(contexto.metadados.get("isencao_confirmada", False)):
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

    ganho_acumulado = float(
        contexto.metadados.get(
            "ganho_acumulado_ano",
            contexto.ganho,
        )
    )
    if ganho_acumulado < 0:
        raise ValueError("ganho_acumulado_ano não pode ser negativo.")
    ganho_anterior = max(0.0, ganho_acumulado - contexto.ganho)
    imposto = (
        imposto_ganho_capital(ganho_acumulado)
        - imposto_ganho_capital(ganho_anterior)
    )
    aliquota = imposto / contexto.ganho if contexto.ganho else 0.0
    return resultado_calculado(
        contexto,
        imposto=imposto,
        aliquota=aliquota,
        precisao=PrecisaoTributaria.ESTIMADA,
        premissas=(
            f"Custódia informada: {custodia}.",
            "Custo de aquisição e ganho acumulado foram fornecidos.",
            "Permutas, staking, offshore e compensações exigem análise própria.",
        ),
        fonte=FONTE_RECEITA_GANHO_CAPITAL,
        vigencia=VIGENCIA_BASE,
        regra_id=f"cripto_ganho_capital_{custodia}_2026",
    )
