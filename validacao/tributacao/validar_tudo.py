"""Executa todos os validadores tributários determinísticos."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from validacao.tributacao.comum import (
    DIVERGENTE,
    FORA_ESCOPO,
    PENDENTE_EVIDENCIA,
    STATUS_VALIDACAO,
    VALIDADO_CALCULO,
    VALIDADO_GUARDRAIL,
)
from validacao.tributacao.validar_cripto_independente import (
    validar as validar_cripto,
)
from validacao.tributacao.validar_estruturados_independente import (
    validar as validar_estruturados,
)
from validacao.tributacao.validar_fundos_independente import (
    validar as validar_fundos,
)
from validacao.tributacao.validar_previdencia_independente import (
    validar as validar_previdencia,
)
from validacao.tributacao.validar_renda_fixa_independente import (
    validar as validar_renda_fixa,
)
from validacao.tributacao.validar_renda_variavel_independente import (
    validar as validar_renda_variavel,
)

VALIDADORES = (
    validar_renda_fixa,
    validar_estruturados,
    validar_fundos,
    validar_previdencia,
    validar_renda_variavel,
    validar_cripto,
)


def executar(saida_dir: Path) -> dict[str, Any]:
    """Executa as categorias e consolida seus totais."""
    relatorios = [validador(saida_dir) for validador in VALIDADORES]
    totais = {
        status: sum(relatorio["resumo"][status] for relatorio in relatorios)
        for status in STATUS_VALIDACAO
    }
    consolidado = {
        "_schema_version": 2,
        "escopo": "validacao_tributaria_independente_seis_categorias",
        "categorias": [relatorio["categoria"] for relatorio in relatorios],
        "resumo": {
            "total": sum(relatorio["resumo"]["total"] for relatorio in relatorios),
            **totais,
        },
        "relatorios": {
            relatorio["categoria"]: relatorio["arquivo"] for relatorio in relatorios
        },
        "criterio_ci": (
            "falha quando DIVERGENTE > 0; fontes e governança são "
            "auditadas em etapa própria"
        ),
    }
    saida_dir.mkdir(parents=True, exist_ok=True)
    destino = saida_dir / "relatorio_tributario_consolidado.json"
    destino.write_text(
        json.dumps(consolidado, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    consolidado["arquivo"] = str(destino)
    return consolidado


def _argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--saida",
        type=Path,
        default=Path(__file__).resolve().parent / "relatorios",
    )
    return parser.parse_args()


def main() -> int:
    argumentos = _argumentos()
    consolidado = executar(argumentos.saida)
    resumo = consolidado["resumo"]
    print("VALIDAÇÃO TRIBUTÁRIA INDEPENDENTE — CONSOLIDADO")
    print(f"Total: {resumo['total']}")
    print(f"Cálculos validados: {resumo[VALIDADO_CALCULO]}")
    print(f"Guardrails validados: {resumo[VALIDADO_GUARDRAIL]}")
    print(f"Pendentes por evidência: {resumo[PENDENTE_EVIDENCIA]}")
    print(f"Fora do escopo: {resumo[FORA_ESCOPO]}")
    print(f"Divergentes: {resumo[DIVERGENTE]}")
    print(f"Relatório: {consolidado['arquivo']}")
    return int(resumo[DIVERGENTE] > 0)


if __name__ == "__main__":
    sys.exit(main())
