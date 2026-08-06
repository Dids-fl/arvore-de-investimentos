"""Registra revisão humana vinculada criptograficamente a um relatório."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DECISOES = {"em_revisao", "aprovado_com_ressalvas", "reprovado"}


def sha256_arquivo(caminho: Path) -> str:
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


def criar_registro(
    relatorio: Path,
    *,
    revisor: str,
    credencial: str,
    registro_profissional: str,
    decisao: str,
    escopo: str,
    ressalvas: list[str],
    declarou_responsabilidade: bool,
) -> dict[str, Any]:
    if decisao not in DECISOES:
        raise ValueError(f"Decisão inválida: {decisao}.")
    if decisao == "aprovado_com_ressalvas" and not declarou_responsabilidade:
        raise ValueError("A aprovação exige declaração explícita de responsabilidade.")
    for nome, valor in {
        "revisor": revisor,
        "credencial": credencial,
        "registro_profissional": registro_profissional,
        "escopo": escopo,
    }.items():
        if not valor.strip():
            raise ValueError(f"{nome} não pode ficar vazio.")

    return {
        "_schema_version": 1,
        "tipo": "registro_de_revisao_humana",
        "relatorio": str(relatorio),
        "relatorio_sha256": sha256_arquivo(relatorio),
        "revisor": revisor,
        "credencial_declarada": credencial,
        "registro_profissional_declarado": registro_profissional,
        "decisao": decisao,
        "escopo": escopo,
        "ressalvas": ressalvas,
        "declarou_responsabilidade": declarou_responsabilidade,
        "registrado_em": datetime.now(UTC).isoformat(),
        "aviso": (
            "O software registra a declaração, mas não autentica identidade, "
            "habilitação ou situação do registro profissional."
        ),
    }


def verificar_registro(registro: dict[str, Any], relatorio: Path) -> bool:
    return registro.get("relatorio_sha256") == sha256_arquivo(relatorio)


def _argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("relatorio", type=Path)
    parser.add_argument("--saida", type=Path, required=True)
    parser.add_argument("--revisor", required=True)
    parser.add_argument("--credencial", required=True)
    parser.add_argument("--registro-profissional", required=True)
    parser.add_argument("--decisao", choices=sorted(DECISOES), required=True)
    parser.add_argument("--escopo", required=True)
    parser.add_argument("--ressalva", action="append", default=[])
    parser.add_argument("--declaro-responsabilidade", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _argumentos()
    registro = criar_registro(
        args.relatorio,
        revisor=args.revisor,
        credencial=args.credencial,
        registro_profissional=args.registro_profissional,
        decisao=args.decisao,
        escopo=args.escopo,
        ressalvas=args.ressalva,
        declarou_responsabilidade=args.declaro_responsabilidade,
    )
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    args.saida.write_text(
        json.dumps(registro, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    sys.stdout.write(f"Registro criado: {args.saida}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
