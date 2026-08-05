"""Recalcula fundos sem reutilizar fórmulas do motor tributário."""

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
    "lei_14754_2023": (
        "https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2023/"
        "lei/l14754.htm"
    ),
    "decreto_iof_6306_2007": (
        "https://www.planalto.gov.br/ccivil_03/_ato2007-2010/2007/"
        "decreto/d6306.htm"
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


def _prazo(entrada: Mapping[str, Any]) -> int:
    inicio = date.fromisoformat(str(entrada["data_aplicacao"]))
    fim = date.fromisoformat(str(entrada["data_resgate"]))
    return (fim - inicio).days


def _aliquota_longo(prazo: int) -> float:
    if prazo <= 180:
        return 0.225
    if prazo <= 360:
        return 0.20
    if prazo <= 720:
        return 0.175
    return 0.15


def calcular_independente(entrada: Mapping[str, Any]) -> dict[str, Any]:
    tipo = str(entrada["tipo_produto"]).casefold()
    rendimento = ganho(entrada)
    pendencias = []
    fim = date.fromisoformat(str(entrada["data_resgate"]))
    if fim.year > 2026:
        pendencias.append(
            "A legislação de 2026 foi mantida como hipótese até o resgate."
        )

    if tipo in {"fundo_acoes", "fundo_etf_acoes"}:
        if tipo == "fundo_etf_acoes":
            pendencias.append(
                "A classificação concreta do ETF como fundo de ações deve "
                "ser confirmada."
            )
        imposto = rendimento * 0.15
        return resultado_calculado(
            entrada,
            imposto=imposto,
            aliquota=(0.15 if rendimento else 0.0),
            precisao="estimada",
            regra_id="fundo_acoes_2026",
            pendencias=tuple(pendencias),
            fundamentos=("Alíquota de 15% para fundo de ações informado.",),
        )

    if tipo not in {
        "fundo_curto_prazo",
        "fundo_longo_prazo",
        "fundo_rf",
    }:
        return resultado_indeterminado(
            regra_id="fundo_tipo_indeterminado",
            motivo="A classificação tributária do fundo não foi informada.",
        )

    if tipo == "fundo_rf":
        pendencias.append(
            "Fundo RF genérico foi tratado como fundo de longo prazo."
        )
    prazo = _prazo(entrada)
    aliquota_ir = (
        0.225
        if tipo == "fundo_curto_prazo" and prazo <= 180
        else 0.20
        if tipo == "fundo_curto_prazo"
        else _aliquota_longo(prazo)
    )
    iof = rendimento * IOF.get(prazo, 0.0)
    ir_total = max(0.0, rendimento - iof) * aliquota_ir
    metadados = dict(entrada.get("metadados", {}))
    antecipado = max(0.0, float(metadados.get("come_cotas_pago", 0.0)))
    if antecipado:
        pendencias.append(
            "Come-cotas foi aceito como total informado, sem reconstrução de cotas."
        )
    ir_resgate = max(0.0, ir_total - antecipado)
    imposto = iof + ir_resgate
    return resultado_calculado(
        entrada,
        imposto=imposto,
        aliquota=(imposto / rendimento if rendimento else 0.0),
        precisao="estimada",
        regra_id=f"{tipo}_2026",
        pendencias=tuple(pendencias),
        fundamentos=(
            "IOF calculado antes do IR quando o prazo é inferior a 30 dias.",
            "Come-cotas informado reduz somente o IR adicional no resgate.",
        ),
    )


def validar(saida_dir: Path | None = None) -> dict[str, Any]:
    return validar_categoria(
        "fundos",
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
