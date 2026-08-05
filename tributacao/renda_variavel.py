"""Estimativa de imposto para ações, ETFs e FIIs por modalidade."""

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
    FONTE_RECEITA_DIRPF,
    FONTE_RECEITA_GANHO_CAPITAL,
    VIGENCIA_BASE,
)

TIPOS_SUPORTADOS = {"acao", "acoes", "etf", "fii"}
CHAVES_LEGADAS = {"prejuizo_compensavel", "irrf"}


def _modalidade(contexto: ContextoTributario) -> str:
    if contexto.day_trade:
        return "day_trade"
    if contexto.tipo_produto == "fii":
        return "fii"
    return "comum"


def _valor_metadado(contexto: ContextoTributario, chave: str) -> float:
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


def _possui_chave_legada(contexto: ContextoTributario) -> bool:
    return bool(CHAVES_LEGADAS.intersection(contexto.metadados))


def calcular_renda_variavel(
    contexto: ContextoTributario,
) -> ResultadoTributario:
    """Calcula apenas com prejuízo e IRRF da modalidade informada."""
    tipo = contexto.tipo_produto
    if tipo not in TIPOS_SUPORTADOS:
        return resultado_indeterminado(
            contexto,
            motivo="Informe ação, ETF ou FII.",
            fonte=FONTE_RECEITA_GANHO_CAPITAL,
            vigencia=VIGENCIA_BASE,
            regra_id="rv_tipo_indeterminado",
        )

    if _possui_chave_legada(contexto):
        return resultado_indeterminado(
            contexto,
            motivo=(
                "Use prejuizo_compensavel_comum, "
                "prejuizo_compensavel_day_trade ou "
                "prejuizo_compensavel_fii e a chave de IRRF correspondente."
            ),
            fonte=FONTE_RECEITA_DIRPF,
            vigencia=VIGENCIA_BASE,
            regra_id="rv_saldo_sem_modalidade",
        )

    if (
        tipo in {"acao", "acoes"}
        and not contexto.day_trade
        and contexto.valor_vendas_mes is not None
        and contexto.valor_vendas_mes <= 20_000
    ):
        return resultado_calculado(
            contexto,
            imposto=0.0,
            aliquota=0.0,
            precisao=PrecisaoTributaria.ESTIMADA,
            premissas=(
                "Operações comuns com ações e vendas mensais até R$ 20 mil.",
                "O valor informado representa todas as vendas elegíveis do mês.",
                "ETFs, FIIs e day trade não usam esta hipótese de isenção.",
            ),
            fonte=FONTE_RECEITA_DIRPF,
            vigencia=VIGENCIA_BASE,
            regra_id="acoes_isencao_mensal_2026",
        )

    modalidade = _modalidade(contexto)
    aliquota = 0.20 if modalidade in {"day_trade", "fii"} else 0.15
    prejuizo = _valor_metadado(
        contexto,
        f"prejuizo_compensavel_{modalidade}",
    )
    irrf = _valor_metadado(contexto, f"irrf_{modalidade}")
    base = max(0.0, contexto.ganho - prejuizo)
    imposto = max(0.0, base * aliquota - irrf)

    return resultado_calculado(
        contexto,
        imposto=imposto,
        aliquota=(imposto / contexto.ganho if contexto.ganho else 0.0),
        precisao=PrecisaoTributaria.ESTIMADA,
        premissas=(
            f"Modalidade tributária usada: {modalidade}.",
            "Ganho, prejuízo compensável e IRRF foram fornecidos pelo usuário.",
            (
                "Emolumentos, notas de corretagem e operações simultâneas "
                "não foram reconstituídos."
            ),
        ),
        fonte=FONTE_RECEITA_GANHO_CAPITAL,
        vigencia=VIGENCIA_BASE,
        regra_id=f"{tipo}_{'daytrade' if contexto.day_trade else 'comum'}_2026",
    )
