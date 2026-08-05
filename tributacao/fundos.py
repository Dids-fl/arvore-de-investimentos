"""Estimativa para fundos com IR, IOF e antecipações informadas."""

from __future__ import annotations

import math

from tributacao.base import (
    ContextoTributario,
    PrecisaoTributaria,
    ResultadoTributario,
    resultado_calculado,
    resultado_indeterminado,
)
from tributacao.regras import (
    FONTE_RECEITA_FUNDOS,
    FUNDO_CURTO_PRAZO_DIAS,
    IOF_RENDA_FIXA_DIAS,
    VIGENCIA_BASE,
    aliquota_por_limite,
    aliquota_rf,
)

FUNDOS_RENDA_FIXA = {
    "fundo_curto_prazo",
    "fundo_longo_prazo",
    "fundo_rf",
}
FUNDOS_ACOES = {"fundo_acoes", "fundo_etf_acoes"}


def _valor_nao_negativo(contexto: ContextoTributario, chave: str) -> float:
    valor = contexto.metadados.get(chave, 0.0)
    if isinstance(valor, bool):
        raise TypeError(f"{chave} não pode ser booleano.")
    try:
        numero = float(valor)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{chave} deve ser numérico.") from exc
    if not math.isfinite(numero) or numero < 0:
        raise ValueError(f"{chave} deve ser finito e não negativo.")
    return numero


def _calcular_fundo_acoes(
    contexto: ContextoTributario,
) -> ResultadoTributario:
    aliquota = 0.15
    return resultado_calculado(
        contexto,
        imposto=contexto.ganho * aliquota,
        aliquota=aliquota if contexto.ganho else 0.0,
        precisao=PrecisaoTributaria.ESTIMADA,
        premissas=(
            "Produto informado como fundo de ações.",
            "Não foram modelados custos, prejuízos ou eventos societários.",
            "IOF regressivo não foi aplicado à categoria de ações.",
        ),
        fonte=FONTE_RECEITA_FUNDOS,
        vigencia=VIGENCIA_BASE,
        regra_id="fundo_acoes_2026",
    )


def _calcular_fundo_renda_fixa(
    contexto: ContextoTributario,
) -> ResultadoTributario:
    tipo = contexto.tipo_produto
    aliquota_ir = (
        aliquota_por_limite(
            float(contexto.prazo_dias),
            FUNDO_CURTO_PRAZO_DIAS,
        )
        if tipo == "fundo_curto_prazo"
        else aliquota_rf(contexto.prazo_dias)
    )

    ganho = contexto.ganho
    aliquota_iof = IOF_RENDA_FIXA_DIAS.get(contexto.prazo_dias, 0.0)
    iof = ganho * aliquota_iof
    base_ir = max(0.0, ganho - iof)
    ir_total = base_ir * aliquota_ir

    antecipado = _valor_nao_negativo(contexto, "come_cotas_pago")
    ir_no_resgate = max(0.0, ir_total - antecipado)
    imposto_no_resgate = iof + ir_no_resgate
    possui_historico = "come_cotas_pago" in contexto.metadados

    premissas = [
        "IR final estimado conforme tipo e prazo do fundo.",
        "IOF sobre o rendimento aplicado em resgates antes de 30 dias.",
        "Come-cotas informado reduz apenas o IR adicional, não o IOF.",
        "O líquido representa os tributos adicionais estimados no resgate.",
    ]
    if not possui_historico:
        premissas.append(
            "Come-cotas anterior não informado; o histórico de cotas não foi reconstruído."
        )

    return resultado_calculado(
        contexto,
        imposto=imposto_no_resgate,
        aliquota=(imposto_no_resgate / ganho if ganho else 0.0),
        precisao=PrecisaoTributaria.ESTIMADA,
        premissas=tuple(premissas),
        fonte=FONTE_RECEITA_FUNDOS,
        vigencia=VIGENCIA_BASE,
        regra_id=f"{tipo}_2026",
    )


def calcular_fundo(contexto: ContextoTributario) -> ResultadoTributario:
    """Seleciona a regra do fundo sem inferir uma categoria ausente."""
    tipo = contexto.tipo_produto
    if tipo in FUNDOS_ACOES:
        return _calcular_fundo_acoes(contexto)
    if tipo in FUNDOS_RENDA_FIXA:
        return _calcular_fundo_renda_fixa(contexto)
    return resultado_indeterminado(
        contexto,
        motivo="Informe se o fundo é de curto prazo, longo prazo ou de ações.",
        fonte=FONTE_RECEITA_FUNDOS,
        vigencia=VIGENCIA_BASE,
        regra_id="fundo_tipo_indeterminado",
    )
