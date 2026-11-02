"""Histórico das suas decisões, salvo só no seu computador.

Cada análise salva guarda a data, a carteira e as taxas previstas. Depois, o
app compara o previsto com o que a carteira teria rendido de verdade desde
então (pelos índices de ``decisao.historico``). Arquivo JSON Lines em
``~/.local/share/arvore_investimentos/decisoes.jsonl`` (ou na variável de
ambiente ``ARVORE_DIARIO``).
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from .historico import retornos_carteira


def arquivo_padrao() -> Path:
    personalizado = os.environ.get("ARVORE_DIARIO")
    if personalizado:
        return Path(personalizado)
    return Path.home() / ".local" / "share" / "arvore_investimentos" / "decisoes.jsonl"


def registro_da_analise(analise: dict, observacao: str = "") -> dict:
    resultado = analise["resultado"]
    respostas = analise.get("respostas", {})
    carteira = {k: float(v) for k, v in resultado["portfolio"].items() if float(v) > 0}
    return {
        "id": uuid.uuid4().hex[:12],
        "data": analise.get("data_referencia") or date.today().isoformat(),
        "salvo_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "perfil": resultado.get("nivel_risco_display"),
        "carteira": carteira,
        "valor": float(respostas.get("cap_inicial") or 0.0),
        "taxa_prevista": float(resultado["taxa_perfil"]),
        "taxa_pessimista": float(resultado["taxa_pess"]),
        "observacao": observacao.strip(),
    }


def salvar(registro: dict, arquivo: Path | None = None) -> None:
    arquivo = arquivo or arquivo_padrao()
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    with arquivo.open("a", encoding="utf-8") as saida:
        saida.write(json.dumps(registro, ensure_ascii=False) + "\n")


def listar(arquivo: Path | None = None) -> list[dict]:
    arquivo = arquivo or arquivo_padrao()
    if not arquivo.is_file():
        return []
    registros = []
    for linha in arquivo.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha:
            continue
        try:
            registros.append(json.loads(linha))
        except ValueError:
            continue  # linha corrompida: ignora sem perder as outras
    return sorted(registros, key=lambda r: r.get("data", ""), reverse=True)


def remover(identificador: str, arquivo: Path | None = None) -> bool:
    arquivo = arquivo or arquivo_padrao()
    registros = listar(arquivo)
    restantes = [r for r in registros if r.get("id") != identificador]
    if len(restantes) == len(registros):
        return False
    temporario = arquivo.with_suffix(".tmp")
    temporario.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in reversed(restantes)),
        encoding="utf-8",
    )
    temporario.replace(arquivo)
    return True


def avaliar(registro: dict, indices: pd.DataFrame) -> dict:
    """Previsto x realizado desde a data da decisão (meses completos)."""
    data = pd.Timestamp(registro["data"])
    meses = indices.loc[indices.index > data + pd.offsets.MonthEnd(0)]
    meses = meses.loc[meses["cdi"].notna()]
    n = len(meses)
    if n == 0:
        return {"meses": 0}
    retornos = retornos_carteira(registro["carteira"], meses)
    anos = n / 12
    realizado = float((1 + retornos).prod() - 1)
    cdi = float((1 + meses["cdi"]).prod() - 1)
    previsto = (1 + registro["taxa_prevista"]) ** anos - 1
    pessimista = (1 + registro["taxa_pessimista"]) ** anos - 1
    valor = float(registro.get("valor") or 0)
    if realizado >= previsto:
        situacao = "acima do previsto"
    elif realizado >= pessimista:
        situacao = "dentro da faixa prevista"
    else:
        situacao = "abaixo do cenário pessimista"
    return {
        "meses": n,
        "ate": meses.index.max().strftime("%m/%Y"),
        "realizado": realizado,
        "previsto": previsto,
        "pessimista": pessimista,
        "cdi": cdi,
        "valor_hoje": valor * (1 + realizado),
        "valor_previsto": valor * (1 + previsto),
        "situacao": situacao,
    }
