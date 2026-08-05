"""Recalcula renda variável com saldos separados por modalidade."""

from __future__ import annotations

import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from validacao.tributacao.comum import (
    codigo_saida,
    ganho,
    imprimir_resumo,
    resultado_calculado,
    resultado_indeterminado,
    validar_categoria,
)

FONTES = {
    "receita_renda_variavel": (
        "https://www.gov.br/receitafederal/pt-br/assuntos/"
        "meu-imposto-de-renda/pagamento/renda-variavel/"
        "bolsa-de-valores-1"
    ),
    "servico_revar": (
        "https://www.gov.br/pt-br/servicos/"
        "apurar-imposto-sobre-renda-variavel"
    ),
}


def _modalidade(
    entrada: Mapping[str, Any],
) -> str:
    """Retorna a modalidade fiscal da operação."""
    if bool(entrada.get("day_trade", False)):
        return "day_trade"

    if str(entrada["tipo_produto"]).casefold() == "fii":
        return "fii"

    return "comum"


def calcular_independente(
    entrada: Mapping[str, Any],
) -> dict[str, Any]:
    """Calcula renda variável conforme modalidade e saldos informados."""
    if not bool(entrada.get("pessoa_fisica", True)):
        return resultado_indeterminado(
            regra_id="pessoa_juridica_fora_escopo",
            motivo=(
                "A apuração para pessoa jurídica está fora do escopo."
            ),
            fora_escopo=True,
        )

    tipo = str(entrada["tipo_produto"]).casefold()

    if tipo not in {"acao", "acoes", "etf", "fii"}:
        return resultado_indeterminado(
            regra_id="produto_nao_suportado",
            motivo=f"Produto não suportado pela fachada: {tipo}.",
            fora_escopo=True,
        )

    metadados = dict(entrada.get("metadados", {}))

    if {"prejuizo_compensavel", "irrf"}.intersection(metadados):
        return resultado_indeterminado(
            regra_id="rv_saldo_sem_modalidade",
            motivo=(
                "Prejuízo ou IRRF foi informado sem modalidade."
            ),
        )

    vendas = entrada.get("valor_vendas_mes")

    if (
        tipo in {"acao", "acoes"}
        and not bool(entrada.get("day_trade", False))
        and vendas is not None
        and float(vendas) <= 20_000
    ):
        return resultado_calculado(
            entrada,
            imposto=0.0,
            aliquota=0.0,
            precisao="estimada",
            regra_id="acoes_isencao_mensal_2026",
            pendencias=(
                (
                    "O total mensal de vendas foi aceito como informado "
                    "pelo usuário."
                ),
            ),
            fundamentos=(
                (
                    "Isenção aplicada apenas a operações comuns com "
                    "ações elegíveis."
                ),
            ),
        )

    modalidade = _modalidade(entrada)
    aliquota = (
        0.20
        if modalidade in {"day_trade", "fii"}
        else 0.15
    )

    prejuizo = max(
        0.0,
        float(
            metadados.get(
                f"prejuizo_compensavel_{modalidade}",
                0.0,
            )
        ),
    )

    irrf = max(
        0.0,
        float(
            metadados.get(
                f"irrf_{modalidade}",
                0.0,
            )
        ),
    )

    rendimento = ganho(entrada)
    base = max(0.0, rendimento - prejuizo)
    imposto = max(0.0, base * aliquota - irrf)

    sufixo_regra = (
        "daytrade"
        if modalidade == "day_trade"
        else "comum"
    )

    return resultado_calculado(
        entrada,
        imposto=imposto,
        aliquota=(
            imposto / rendimento
            if rendimento
            else 0.0
        ),
        precisao="estimada",
        regra_id=f"{tipo}_{sufixo_regra}_2026",
        pendencias=(
            (
                "Custos, notas de corretagem e operações simultâneas "
                "não foram reconstruídos."
            ),
            (
                "Prejuízo acumulado e IRRF foram aceitos como "
                "informados pelo usuário."
            ),
        ),
        fundamentos=(
            (
                f"Alíquota de {aliquota:.0%} aplicada à modalidade "
                f"{modalidade}."
            ),
            "Compensação limitada ao saldo da modalidade informada.",
        ),
    )


def validar(
    saida_dir: Path | None = None,
) -> dict[str, Any]:
    """Executa a validação independente de renda variável."""
    return validar_categoria(
        "renda_variavel",
        calcular_independente,
        fontes_oficiais=FONTES,
        saida_dir=saida_dir,
    )


def main() -> int:
    """Executa o validador pela linha de comando."""
    relatorio = validar()
    imprimir_resumo(relatorio)
    return codigo_saida(relatorio)


if __name__ == "__main__":
    sys.exit(main())