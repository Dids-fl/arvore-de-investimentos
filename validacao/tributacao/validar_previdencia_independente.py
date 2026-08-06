"""Recalcula previdência sem reutilizar as tabelas do motor."""

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
    "receita_pgbl_vgbl": (
        "https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/"
        "perguntas-frequentes/imposto-de-renda/dirpf/declaracao/pgvl-vgbl"
    ),
    "previdencia_faq": (
        "https://www.gov.br/previdencia/pt-br/assuntos/"
        "previdencia-complementar/mais-informacoes/"
        "perguntas-frequentes-de-previdencia-complementar"
    ),
}


def _prazo_anos(entrada: Mapping[str, Any]) -> float:
    inicio = date.fromisoformat(str(entrada["data_aplicacao"]))
    fim = date.fromisoformat(str(entrada["data_resgate"]))
    return (fim - inicio).days / 365.2425


def _aliquota_regressiva(anos: float) -> float:
    if anos <= 2:
        return 0.35
    if anos <= 4:
        return 0.30
    if anos <= 6:
        return 0.25
    if anos <= 8:
        return 0.20
    if anos <= 10:
        return 0.15
    return 0.10


def _ir_bruto(base: float) -> float:
    if base <= 29_145.60:
        return 0.0
    if base <= 33_919.80:
        return max(0.0, base * 0.075 - 2_185.92)
    if base <= 45_012.60:
        return max(0.0, base * 0.15 - 4_729.91)
    if base <= 55_976.16:
        return max(0.0, base * 0.225 - 8_105.85)
    return max(0.0, base * 0.275 - 10_904.66)


def _ir_anual(base: float, rendimentos: float) -> float:
    bruto = _ir_bruto(max(0.0, base))
    if rendimentos <= 60_000:
        reducao = 2_694.15
    elif rendimentos <= 88_200:
        reducao = max(0.0, 8_429.73 - 0.095575 * rendimentos)
    else:
        reducao = 0.0
    return max(0.0, bruto - min(bruto, reducao))


def calcular_independente(entrada: Mapping[str, Any]) -> dict[str, Any]:
    tipo = str(entrada["tipo_produto"]).casefold()
    regime = entrada.get("regime")
    if tipo not in {"pgbl", "vgbl"}:
        return resultado_indeterminado(
            regra_id="previdencia_tipo_indeterminado",
            motivo="O produto não foi identificado como PGBL ou VGBL.",
        )
    if regime not in {"regressivo", "progressivo"}:
        return resultado_indeterminado(
            regra_id="previdencia_regime_indeterminado",
            motivo="O regime progressivo ou regressivo não foi informado.",
        )

    base_resgate = float(entrada["valor_bruto"]) if tipo == "pgbl" else ganho(entrada)
    pendencias = []
    fim = date.fromisoformat(str(entrada["data_resgate"]))
    if fim.year > 2026:
        pendencias.append(
            "A legislação de 2026 foi mantida como hipótese até o resgate."
        )

    if regime == "regressivo":
        pendencias.append("Todo o saldo foi tratado como um lote com uma única idade.")
        aliquota = _aliquota_regressiva(_prazo_anos(entrada))
        imposto = base_resgate * aliquota
        return resultado_calculado(
            entrada,
            imposto=imposto,
            aliquota=(aliquota if base_resgate else 0.0),
            precisao="estimada",
            regra_id=f"{tipo}_regressivo_2026",
            pendencias=tuple(pendencias),
            fundamentos=(
                "PGBL sobre o saldo total; VGBL apenas sobre o rendimento.",
                "Tabela regressiva aplicada pela idade do lote simplificado.",
            ),
        )

    renda = entrada.get("renda_tributavel")
    if renda is None:
        return resultado_indeterminado(
            regra_id=f"{tipo}_progressivo_sem_renda",
            motivo="A renda tributável anual não foi informada.",
        )

    rendimentos_antes = float(renda)
    metadados = dict(entrada.get("metadados", {}))
    base_antes = float(metadados.get("base_calculo_irpf_anual", rendimentos_antes))
    if "base_calculo_irpf_anual" not in metadados:
        pendencias.append(
            "A renda tributável foi usada como aproximação da base anual."
        )
    imposto_antes = _ir_anual(base_antes, rendimentos_antes)
    imposto_depois = _ir_anual(
        base_antes + base_resgate,
        rendimentos_antes + base_resgate,
    )
    imposto = max(0.0, imposto_depois - imposto_antes)
    return resultado_calculado(
        entrada,
        imposto=imposto,
        aliquota=(imposto / base_resgate if base_resgate else 0.0),
        precisao="estimada",
        regra_id=f"{tipo}_progressivo_2026",
        pendencias=tuple(pendencias),
        fundamentos=(
            "Tabela anual e redução anual de 2026 recalculadas separadamente.",
            "Imposto incremental calculado com e sem o resgate.",
        ),
    )


def validar(saida_dir: Path | None = None) -> dict[str, Any]:
    return validar_categoria(
        "previdencia",
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
