"""CLI para registrar um calendário anual publicado pela B3."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path

from calendarios.validacao import (
    CalendarioExtraido,
    fonte_b3_oficial,
    validar_calendario_extraido,
)

_DIRETORIO_PADRAO = Path(__file__).with_name("b3")


def registrar_calendario(
    *,
    ano: int,
    fonte: str,
    datas: Sequence[str],
    destino: Path = _DIRETORIO_PADRAO,
) -> Path:
    """Valida e grava um calendário confirmado sem inferir datas ausentes."""
    if not fonte_b3_oficial(fonte):
        raise ValueError("A fonte deve ser uma página HTTPS oficial da B3.")
    datas_convertidas = tuple(sorted(date.fromisoformat(valor) for valor in datas))
    if not datas_convertidas:
        raise ValueError("Informe ao menos um dia sem negociação.")
    validar_calendario_extraido(
        CalendarioExtraido(ano=ano, datas=datas_convertidas),
        anos_permitidos=(ano,),
    )
    normalizadas = [valor.isoformat() for valor in datas_convertidas]

    destino.mkdir(parents=True, exist_ok=True)
    arquivo = destino / f"{ano}.json"
    conteudo = {
        "ano": ano,
        "status": "confirmado",
        "publicado_em": datetime.now(UTC).date().isoformat(),
        "fonte": fonte,
        "dias_sem_negociacao": normalizadas,
    }
    arquivo.write_text(
        json.dumps(conteudo, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return arquivo


def _datas_do_arquivo(caminho: Path) -> list[str]:
    texto = caminho.read_text(encoding="utf-8")
    if caminho.suffix.casefold() == ".json":
        dados = json.loads(texto)
        if isinstance(dados, dict):
            dados = dados.get("dias_sem_negociacao")
        if not isinstance(dados, list):
            raise TypeError("O JSON deve ser uma lista ou conter dias_sem_negociacao.")
        return [str(valor) for valor in dados]
    return [linha.strip() for linha in texto.splitlines() if linha.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Registra datas oficiais já conferidas no calendário B3.",
    )
    parser.add_argument("--ano", type=int, required=True)
    parser.add_argument("--fonte", required=True)
    parser.add_argument("--datas", type=Path, required=True)
    argumentos = parser.parse_args()
    arquivo = registrar_calendario(
        ano=argumentos.ano,
        fonte=argumentos.fonte,
        datas=_datas_do_arquivo(argumentos.datas),
    )
    print(f"Calendário registrado: {arquivo}")


if __name__ == "__main__":
    main()
