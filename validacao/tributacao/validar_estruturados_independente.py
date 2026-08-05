"""Recalcula estruturados por subtipo e confirmação de elegibilidade."""

from __future__ import annotations

import sys
from collections.abc import Mapping
from datetime import date
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
from validacao.tributacao.validar_renda_fixa_independente import (
    IOF,
    aliquota_ir,
    prazo_dias,
)

FONTES = {
    "receita_tabelas_2026": (
        "https://www.gov.br/receitafederal/pt-br/assuntos/"
        "meu-imposto-de-renda/tabelas/2026"
    ),
    "lei_11033_2004": (
        "https://www.planalto.gov.br/ccivil_03/_ato2004-2006/2004/"
        "lei/l11033compilado.htm"
    ),
    "lei_12431_2011": (
        "https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2011/"
        "lei/l12431.htm"
    ),
}

ISENTOS_CONDICIONAIS = {
    "cri",
    "cra",
    "debenture_incentivada",
}

TRIBUTAVEIS = {
    "coe",
    "debenture_comum",
}


def calcular_independente(
    entrada: Mapping[str, Any],
) -> dict[str, Any]:
    """Calcula estruturados conforme o subtipo informado."""
    if not bool(entrada.get("pessoa_fisica", True)):
        return resultado_indeterminado(
            regra_id="pessoa_juridica_fora_escopo",
            motivo=(
                "A tributação da pessoa jurídica está fora do escopo."
            ),
            fora_escopo=True,
        )

    tipo = str(entrada["tipo_produto"]).casefold()

    if tipo == "estruturado":
        return resultado_indeterminado(
            regra_id="estruturado_subtipo_indeterminado",
            motivo=(
                "O subtipo do produto estruturado não foi informado."
            ),
        )

    if tipo not in ISENTOS_CONDICIONAIS | TRIBUTAVEIS:
        return resultado_indeterminado(
            regra_id="produto_nao_suportado",
            motivo=f"Subtipo estruturado não suportado: {tipo}.",
            fora_escopo=True,
        )

    pendencias = []
    fim = date.fromisoformat(str(entrada["data_resgate"]))

    if fim.year > 2026:
        pendencias.append(
            "A legislação de 2026 foi mantida como hipótese até o resgate."
        )

    if tipo in ISENTOS_CONDICIONAIS:
        metadados = dict(entrada.get("metadados", {}))
        confirmado = metadados.get(
            "elegibilidade_isencao_confirmada",
            False,
        )

        if confirmado is not True:
            return resultado_indeterminado(
                regra_id="rf_isencao_elegibilidade_indeterminada",
                motivo=(
                    "A elegibilidade legal do instrumento não foi "
                    "confirmada."
                ),
            )

        pendencias.append(
            "A confirmação foi aceita sem inspeção do documento do "
            "instrumento."
        )

        return resultado_calculado(
            entrada,
            imposto=0.0,
            aliquota=0.0,
            precisao="exata_para_premissas",
            regra_id="rf_isenta_pf_2026",
            pendencias=tuple(pendencias),
            fundamentos=(
                (
                    "Isenção condicionada à elegibilidade confirmada "
                    "para pessoa física."
                ),
            ),
        )

    prazo = prazo_dias(entrada)
    rendimento = ganho(entrada)
    iof = rendimento * IOF.get(prazo, 0.0)
    ir = max(0.0, rendimento - iof) * aliquota_ir(prazo)
    imposto = iof + ir

    return resultado_calculado(
        entrada,
        imposto=imposto,
        aliquota=(
            imposto / rendimento
            if rendimento
            else 0.0
        ),
        precisao="exata_para_premissas",
        regra_id="rf_regressiva_2026",
        pendencias=tuple(pendencias),
        fundamentos=(
            (
                "COE e debênture comum tratados pela tabela regressiva "
                "informada."
            ),
            "IOF aplicado antes do IR quando o prazo é inferior a 30 dias.",
        ),
    )


def validar(
    saida_dir: Path | None = None,
) -> dict[str, Any]:
    """Executa a validação independente de estruturados."""
    return validar_categoria(
        "estruturados",
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