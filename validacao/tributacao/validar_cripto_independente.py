"""Recalcula criptoativos sem reutilizar tabelas do motor tributário."""

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
    "receita_aliquotas_ganho_capital": (
        "https://www.gov.br/receitafederal/pt-br/assuntos/"
        "meu-imposto-de-renda/pagamento/ganhos-de-capital/aliquotas"
    ),
    "lei_13259_2016": (
        "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2016/lei/l13259.htm"
    ),
    "lei_14754_2023": (
        "https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2023/lei/l14754.htm"
    ),
    "in_rfb_2180_2024": (
        "https://normas.receita.fazenda.gov.br/sijut2consulta/link.action?idAto=136603"
    ),
}

FAIXAS_GANHO_CAPITAL = (
    (5_000_000.0, 0.15),
    (10_000_000.0, 0.175),
    (30_000_000.0, 0.20),
    (None, 0.225),
)


def _imposto_ganho_capital(ganho_acumulado: float) -> float:
    restante = max(0.0, float(ganho_acumulado))
    imposto = 0.0
    limite_anterior = 0.0
    for limite, aliquota in FAIXAS_GANHO_CAPITAL:
        if limite is None:
            imposto += restante * aliquota
            break
        largura = limite - limite_anterior
        parcela = min(restante, largura)
        imposto += parcela * aliquota
        restante -= parcela
        if restante <= 0:
            break
        limite_anterior = limite
    return imposto


def _confirmacao_booleana(
    metadados: Mapping[str, Any],
    chave: str,
) -> bool:
    valor = metadados.get(chave, False)
    if not isinstance(valor, bool):
        raise TypeError(f"{chave} deve ser booleano.")
    return valor


def calcular_independente(entrada: Mapping[str, Any]) -> dict[str, Any]:
    """Aplica somente regras explicitamente sustentadas pela entrada."""
    metadados = dict(entrada.get("metadados", {}))
    jurisdicao = str(metadados.get("jurisdicao_custodia", "")).casefold()
    if jurisdicao not in {"brasil", "exterior"}:
        return resultado_indeterminado(
            regra_id="cripto_jurisdicao_indeterminada",
            motivo="A jurisdição de custódia não foi informada.",
            fundamentos=("O enquadramento depende da jurisdição.",),
        )

    if _confirmacao_booleana(metadados, "isencao_confirmada"):
        return resultado_calculado(
            entrada,
            imposto=0.0,
            aliquota=0.0,
            precisao="estimada",
            regra_id="cripto_isencao_informada_2026",
            pendencias=(
                (
                    "A isenção foi aceita como informação externa; anexar a "
                    "memória jurídica que sustenta o enquadramento."
                ),
            ),
            fundamentos=("O validador não cria automaticamente hipótese de isenção.",),
        )

    rendimento = ganho(entrada)
    if jurisdicao == "exterior":
        if not _confirmacao_booleana(
            metadados,
            "enquadramento_aplicacao_financeira_exterior_confirmado",
        ):
            return resultado_indeterminado(
                regra_id="cripto_exterior_enquadramento_indeterminado",
                motivo=(
                    "A localização no exterior não comprova o enquadramento "
                    "como aplicação financeira no exterior."
                ),
            )
        imposto = rendimento * 0.15
        return resultado_calculado(
            entrada,
            imposto=imposto,
            aliquota=(0.15 if rendimento else 0.0),
            precisao="estimada",
            regra_id="cripto_aplicacao_financeira_exterior_2026",
            pendencias=(
                (
                    "O enquadramento informado deve ser confirmado por "
                    "documento e revisão profissional."
                ),
            ),
            fundamentos=("Alíquota anual de 15% para aplicação financeira exterior.",),
        )

    acumulado_informado = "ganho_acumulado_ano" in metadados
    if acumulado_informado and not _confirmacao_booleana(
        metadados,
        "alienacoes_parciais_mesmo_bem_confirmadas",
    ):
        return resultado_indeterminado(
            regra_id="cripto_acumulacao_indeterminada",
            motivo=(
                "A agregação exige confirmar alienações parciais do mesmo "
                "bem ou direito e o período legal aplicável."
            ),
        )

    acumulado = float(metadados.get("ganho_acumulado_ano", rendimento))
    if acumulado < rendimento:
        raise ValueError("ganho_acumulado_ano não pode ser menor que o ganho atual.")
    anterior = acumulado - rendimento
    imposto = _imposto_ganho_capital(acumulado) - _imposto_ganho_capital(anterior)
    pendencias = ()
    if acumulado_informado:
        pendencias = (
            (
                "A identidade do bem e o período de agregação foram aceitos "
                "como informados; anexar memória de alienações."
            ),
        )
    return resultado_calculado(
        entrada,
        imposto=imposto,
        aliquota=(imposto / rendimento if rendimento else 0.0),
        precisao="estimada",
        regra_id="cripto_ganho_capital_brasil_2026",
        pendencias=pendencias,
        fundamentos=("Faixas progressivas aplicadas sobre o ganho de capital.",),
    )


def validar(saida_dir: Path | None = None) -> dict[str, Any]:
    return validar_categoria(
        "cripto",
        calcular_independente,
        fontes_oficiais=FONTES,
        saida_dir=saida_dir,
    )


def main() -> int:
    relatorio = validar()
    imprimir_resumo(relatorio)
    return codigo_saida(relatorio)


if __name__ == "__main__":
    sys.exit(main())
