"""Estimativa para fundos; come-cotas exige histórico de cotas e eventos."""

from __future__ import annotations

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
    VIGENCIA_BASE,
    aliquota_por_limite,
    aliquota_rf,
)


def calcular_fundo(contexto: ContextoTributario) -> ResultadoTributario:
    tipo = contexto.tipo_produto
    if tipo in {"fundo_acoes", "fundo_etf_acoes"}:
        aliquota = 0.15
        return resultado_calculado(
            contexto,
            imposto=contexto.ganho * aliquota,
            aliquota=aliquota,
            precisao=PrecisaoTributaria.ESTIMADA,
            premissas=(
                "Produto informado como fundo de ações.",
                "Não foram modelados custos, prejuízos ou eventos societários.",
            ),
            fonte=FONTE_RECEITA_FUNDOS,
            vigencia=VIGENCIA_BASE,
            regra_id="fundo_acoes_2026",
        )

    if tipo not in {"fundo_curto_prazo", "fundo_longo_prazo", "fundo_rf"}:
        return resultado_indeterminado(
            contexto,
            motivo=(
                "Informe se o fundo é de curto prazo, longo prazo ou de ações."
            ),
            fonte=FONTE_RECEITA_FUNDOS,
            vigencia=VIGENCIA_BASE,
            regra_id="fundo_tipo_indeterminado",
        )

    aliquota = (
        aliquota_por_limite(
            float(contexto.prazo_dias),
            FUNDO_CURTO_PRAZO_DIAS,
        )
        if tipo == "fundo_curto_prazo"
        else aliquota_rf(contexto.prazo_dias)
    )
    imposto_total = contexto.ganho * aliquota
    antecipado = max(
        0.0,
        float(contexto.metadados.get("come_cotas_pago", 0.0)),
    )
    imposto_resgate = max(0.0, imposto_total - antecipado)
    possui_historico = "come_cotas_pago" in contexto.metadados

    premissas = [
        "Alíquota final estimada conforme tipo e prazo do fundo.",
        "O valor líquido representa o imposto adicional estimado no resgate.",
    ]
    if not possui_historico:
        premissas.append(
            "Come-cotas anterior não informado; resultado não reproduz cotas."
        )
    return resultado_calculado(
        contexto,
        imposto=imposto_resgate,
        aliquota=(imposto_resgate / contexto.ganho if contexto.ganho else 0.0),
        precisao=PrecisaoTributaria.ESTIMADA,
        premissas=tuple(premissas),
        fonte=FONTE_RECEITA_FUNDOS,
        vigencia=VIGENCIA_BASE,
        regra_id=f"{tipo}_2026",
    )
