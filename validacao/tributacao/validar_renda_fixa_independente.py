"""Recalcula renda fixa sem reutilizar tabelas do motor tributário."""

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

FONTES = {
    "receita_tabelas_2026": (
        "https://www.gov.br/receitafederal/pt-br/assuntos/"
        "meu-imposto-de-renda/tabelas/2026"
    ),
    "decreto_iof_6306_2007": (
        "https://www.planalto.gov.br/ccivil_03/_ato2007-2010/2007/"
        "decreto/d6306.htm"
    ),
    "lei_11033_2004": (
        "https://www.planalto.gov.br/ccivil_03/_ato2004-2006/2004/"
        "lei/l11033compilado.htm"
    ),
}

IOF = {
    1: 0.96,
    2: 0.93,
    3: 0.90,
    4: 0.86,
    5: 0.83,
    6: 0.80,
    7: 0.76,
    8: 0.73,
    9: 0.70,
    10: 0.66,
    11: 0.63,
    12: 0.60,
    13: 0.56,
    14: 0.53,
    15: 0.50,
    16: 0.46,
    17: 0.43,
    18: 0.40,
    19: 0.36,
    20: 0.33,
    21: 0.30,
    22: 0.26,
    23: 0.23,
    24: 0.20,
    25: 0.16,
    26: 0.13,
    27: 0.10,
    28: 0.06,
    29: 0.03,
}


def prazo_dias(entrada: Mapping[str, Any]) -> int:
    """Calcula o prazo do investimento em dias corridos."""
    inicio = date.fromisoformat(str(entrada["data_aplicacao"]))
    fim = date.fromisoformat(str(entrada["data_resgate"]))
    return (fim - inicio).days


def aliquota_ir(prazo: int) -> float:
    """Retorna a alíquota regressiva de IR aplicável ao prazo."""
    if prazo <= 180:
        return 0.225
    if prazo <= 360:
        return 0.20
    if prazo <= 720:
        return 0.175
    return 0.15


def calcular_independente(
    entrada: Mapping[str, Any],
) -> dict[str, Any]:
    """Calcula o caso diretamente a partir das tabelas oficiais."""
    if not bool(entrada.get("pessoa_fisica", True)):
        return resultado_indeterminado(
            regra_id="pessoa_juridica_fora_escopo",
            motivo="IRPJ e CSLL não pertencem ao escopo deste motor.",
            fundamentos=("Escopo declarado: pessoa física.",),
            fora_escopo=True,
        )

    tipo = str(entrada["tipo_produto"]).casefold()
    pendencias = []

    if date.fromisoformat(str(entrada["data_resgate"])).year > 2026:
        pendencias.append(
            "A legislação de 2026 foi mantida como hipótese até o resgate."
        )

    if tipo in {"lci", "lca"}:
        return resultado_calculado(
            entrada,
            imposto=0.0,
            aliquota=0.0,
            precisao="exata_para_premissas",
            regra_id="rf_isenta_pf_2026",
            pendencias=tuple(pendencias),
            fundamentos=(
                "Isenção informada para pessoa física.",
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
            "IOF calculado antes do IR para prazos inferiores a 30 dias.",
            "IR regressivo por prazo sobre o rendimento líquido de IOF.",
        ),
    )


def validar(
    saida_dir: Path | None = None,
) -> dict[str, Any]:
    """Executa a validação independente de renda fixa."""
    return validar_categoria(
        "renda_fixa",
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