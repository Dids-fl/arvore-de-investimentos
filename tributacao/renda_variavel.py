"""Estimativa de imposto para ações, ETFs e FIIs."""

from __future__ import annotations

from tributacao.base import (
    ContextoTributario,
    PrecisaoTributaria,
    ResultadoTributario,
    resultado_calculado,
    resultado_indeterminado,
)
from tributacao.regras import (
    FONTE_RECEITA_DIRPF,
    FONTE_RECEITA_GANHO_CAPITAL,
    VIGENCIA_BASE,
)


def calcular_renda_variavel(
    contexto: ContextoTributario,
) -> ResultadoTributario:
    tipo = contexto.tipo_produto
    if tipo not in {"acao", "acoes", "etf", "fii"}:
        return resultado_indeterminado(
            contexto,
            motivo="Informe ação, ETF ou FII.",
            fonte=FONTE_RECEITA_GANHO_CAPITAL,
            vigencia=VIGENCIA_BASE,
            regra_id="rv_tipo_indeterminado",
        )

    if (
        tipo in {"acao", "acoes"}
        and not contexto.day_trade
        and contexto.valor_vendas_mes is not None
        and contexto.valor_vendas_mes <= 20_000
        and contexto.pessoa_fisica
    ):
        return resultado_calculado(
            contexto,
            imposto=0.0,
            aliquota=0.0,
            precisao=PrecisaoTributaria.ESTIMADA,
            premissas=(
                "Operações comuns com ações e vendas mensais até R$ 20 mil.",
                "O usuário confirmou pessoa física e valor total de vendas.",
                "ETFs, FIIs e day trade não usam esta hipótese de isenção.",
            ),
            fonte=FONTE_RECEITA_DIRPF,
            vigencia=VIGENCIA_BASE,
            regra_id="acoes_isencao_mensal_2026",
        )

    aliquota = 0.20 if contexto.day_trade or tipo == "fii" else 0.15
    prejuizo = max(
        0.0,
        float(contexto.metadados.get("prejuizo_compensavel", 0.0)),
    )
    irrf = max(0.0, float(contexto.metadados.get("irrf", 0.0)))
    base = max(0.0, contexto.ganho - prejuizo)
    imposto = max(0.0, base * aliquota - irrf)
    return resultado_calculado(
        contexto,
        imposto=imposto,
        aliquota=(imposto / contexto.ganho if contexto.ganho else 0.0),
        precisao=PrecisaoTributaria.ESTIMADA,
        premissas=(
    "Ganho, prejuízo compensável e IRRF foram fornecidos pelo usuário.",
    "Emolumentos, notas de corretagem e operações simultâneas não foram reconstituídos.",),
        fonte=FONTE_RECEITA_GANHO_CAPITAL,
        vigencia=VIGENCIA_BASE,
        regra_id=f"{tipo}_{'daytrade' if contexto.day_trade else 'comum'}_2026",
    )
