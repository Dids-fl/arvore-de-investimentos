"""Importação auditável de lotes previdenciários e de fundos."""

from __future__ import annotations

import io
import math
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import BinaryIO

import pandas as pd

COLUNAS_OBRIGATORIAS = {
    "categoria",
    "tipo_lote",
    "principal",
    "saldo_atual",
    "data_aplicacao",
}


@dataclass(frozen=True)
class ResultadoImportacaoLotes:
    """Metadados prontos para o engine, acompanhados de avisos e resumo."""

    metadados_por_categoria: dict[str, dict[str, object]]
    quantidade_lotes: int
    saldo_total: float
    avisos: tuple[str, ...]
    resumo: tuple[dict[str, object], ...]


def _normalizar_texto(valor: object) -> str:
    texto = unicodedata.normalize("NFKD", str(valor).strip().casefold())
    return "".join(char for char in texto if not unicodedata.combining(char))


def _numero(nome: str, valor: object, *, padrao: float | None = None) -> float:
    if valor is None or pd.isna(valor) or str(valor).strip() == "":
        if padrao is not None:
            return padrao
        raise ValueError(f"{nome} é obrigatório.")
    if isinstance(valor, bool):
        raise TypeError(f"{nome} não pode ser booleano.")
    if isinstance(valor, str):
        texto = valor.strip().replace("R$", "").replace(" ", "")
        if "," in texto:
            texto = texto.replace(".", "").replace(",", ".")
        valor = texto
    try:
        numero = float(valor)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{nome} deve ser numérico.") from exc
    if not math.isfinite(numero) or numero < 0:
        raise ValueError(f"{nome} deve ser finito e não negativo.")
    return numero


def _data(nome: str, valor: object) -> date:
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if valor is None or pd.isna(valor):
        raise ValueError(f"{nome} é obrigatório.")
    texto = str(valor).strip()
    try:
        return date.fromisoformat(texto)
    except ValueError:
        pass
    try:
        dia, mes, ano = (int(parte) for parte in texto.split("/"))
        return date(ano, mes, dia)
    except (TypeError, ValueError):
        pass
    raise ValueError(f"{nome} deve usar AAAA-MM-DD ou DD/MM/AAAA.")


def _ler_tabela(
    arquivo: str | Path | bytes | BinaryIO,
    *,
    nome_arquivo: str | None,
) -> pd.DataFrame:
    if isinstance(arquivo, (str, Path)):
        caminho = Path(arquivo)
        sufixo = caminho.suffix.casefold()
        origem: object = caminho
    else:
        sufixo = Path(nome_arquivo or "").suffix.casefold()
        if isinstance(arquivo, bytes):
            origem = io.BytesIO(arquivo)
        else:
            origem = arquivo

    if sufixo == ".csv":
        try:
            return pd.read_csv(origem, sep=None, engine="python", dtype=object)
        except UnicodeDecodeError:
            if hasattr(origem, "seek"):
                origem.seek(0)
            return pd.read_csv(
                origem,
                sep=None,
                engine="python",
                dtype=object,
                encoding="latin-1",
            )
    if sufixo in {".xlsx", ".xlsm"}:
        return pd.read_excel(origem, engine="openpyxl", dtype=object)
    raise ValueError("O extrato deve ser CSV, XLSX ou XLSM.")


def importar_lotes_tributarios(
    arquivo: str | Path | bytes | BinaryIO,
    *,
    nome_arquivo: str | None = None,
    data_referencia: date | None = None,
) -> ResultadoImportacaoLotes:
    """Valida o arquivo e converte lotes para o contrato fiscal do engine."""
    referencia = data_referencia or datetime.now(UTC).date()
    tabela = _ler_tabela(arquivo, nome_arquivo=nome_arquivo)
    tabela.columns = [_normalizar_texto(coluna) for coluna in tabela.columns]
    ausentes = sorted(COLUNAS_OBRIGATORIAS - set(tabela.columns))
    if ausentes:
        raise ValueError("Colunas obrigatórias ausentes: " + ", ".join(ausentes))
    if tabela.empty:
        raise ValueError("O arquivo não contém lotes.")

    metadados: dict[str, dict[str, object]] = {}
    resumos: dict[tuple[str, str], dict[str, object]] = {}
    saldos_esperados: dict[str, float] = {}
    ids: set[str] = set()
    saldo_total = 0.0
    avisos: list[str] = []

    for posicao, (_, linha) in enumerate(tabela.iterrows(), start=2):
        categoria = str(linha["categoria"]).strip()
        if not categoria or categoria.casefold() == "nan":
            raise ValueError(f"Linha {posicao}: categoria é obrigatória.")
        tipo = _normalizar_texto(linha["tipo_lote"]).replace(" ", "_")
        aliases = {
            "fundo": "fundo",
            "fundos": "fundo",
            "previdencia": "previdencia",
            "previdenciario": "previdencia",
        }
        if tipo not in aliases:
            raise ValueError(
                f"Linha {posicao}: tipo_lote deve ser fundo ou previdencia."
            )
        tipo = aliases[tipo]

        identificador = str(linha.get("id_lote", "")).strip()
        if identificador and identificador.casefold() != "nan":
            if identificador in ids:
                raise ValueError(f"id_lote duplicado: {identificador}.")
            ids.add(identificador)

        principal = _numero(
            f"Linha {posicao}: principal",
            linha["principal"],
        )
        saldo = _numero(
            f"Linha {posicao}: saldo_atual",
            linha["saldo_atual"],
        )
        aplicacao = _data(
            f"Linha {posicao}: data_aplicacao",
            linha["data_aplicacao"],
        )
        if aplicacao > referencia:
            raise ValueError(f"Linha {posicao}: data_aplicacao está no futuro.")

        lote: dict[str, object] = {
            "principal": principal,
            "saldo_atual": saldo,
            "data_aplicacao": aplicacao.isoformat(),
        }
        chave_destino = "lotes_previdencia_existentes"
        if tipo == "fundo":
            chave_destino = "lotes_fundo_existentes"
            lote.update(
                {
                    "base_tributaria_atual": _numero(
                        f"Linha {posicao}: base_tributaria_atual",
                        linha.get("base_tributaria_atual"),
                    ),
                    "ganho_antecipado": _numero(
                        f"Linha {posicao}: ganho_antecipado",
                        linha.get("ganho_antecipado"),
                        padrao=0.0,
                    ),
                    "come_cotas_pago_historico": _numero(
                        f"Linha {posicao}: come_cotas_pago_historico",
                        linha.get("come_cotas_pago_historico"),
                        padrao=0.0,
                    ),
                }
            )

        destino = metadados.setdefault(categoria, {})
        destino.setdefault(chave_destino, []).append(lote)
        chave_resumo = (categoria, tipo)
        resumo = resumos.setdefault(
            chave_resumo,
            {"categoria": categoria, "tipo_lote": tipo, "lotes": 0, "saldo": 0.0},
        )
        resumo["lotes"] = int(resumo["lotes"]) + 1
        resumo["saldo"] = float(resumo["saldo"]) + saldo
        saldo_total += saldo

        esperado_bruto = linha.get("saldo_categoria_esperado")
        if esperado_bruto is not None and not pd.isna(esperado_bruto):
            esperado = _numero(
                f"Linha {posicao}: saldo_categoria_esperado",
                esperado_bruto,
            )
            anterior = saldos_esperados.setdefault(categoria, esperado)
            if not math.isclose(anterior, esperado, abs_tol=0.01):
                raise ValueError(
                    f"Linha {posicao}: saldo_categoria_esperado inconsistente."
                )

    for categoria, esperado in saldos_esperados.items():
        apurado = sum(
            float(resumo["saldo"])
            for (chave, _), resumo in resumos.items()
            if chave == categoria
        )
        tolerancia = max(0.01, esperado * 1e-6)
        if not math.isclose(apurado, esperado, abs_tol=tolerancia):
            raise ValueError(
                f"Categoria {categoria}: saldo importado {apurado:.2f} difere "
                f"do saldo esperado {esperado:.2f}."
            )

    sem_reconciliacao = sorted(set(metadados) - set(saldos_esperados))
    if sem_reconciliacao:
        avisos.append(
            "Sem saldo_categoria_esperado para: "
            + ", ".join(sem_reconciliacao)
            + ". O engine ainda validará a soma contra o capital projetado."
        )
    avisos.append(
        "A importação não certifica a correção fiscal do extrato; confirme "
        "bases, datas e come-cotas com o informe da instituição."
    )
    return ResultadoImportacaoLotes(
        metadados_por_categoria=metadados,
        quantidade_lotes=len(tabela),
        saldo_total=saldo_total,
        avisos=tuple(avisos),
        resumo=tuple(resumos.values()),
    )


def mesclar_metadados_tributarios(
    existentes: Mapping[str, object],
    importados: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    """Mescla sem sobrescrever silenciosamente lotes digitados no JSON."""
    resultado = {str(chave): valor for chave, valor in existentes.items()}
    for categoria, dados_importados in importados.items():
        atual = resultado.setdefault(categoria, {})
        if not isinstance(atual, Mapping):
            raise TypeError(f"Metadados de {categoria} devem ser um objeto.")
        combinado = dict(atual)
        conflitos = sorted(set(combinado) & set(dados_importados))
        if conflitos:
            raise ValueError(
                f"Categoria {categoria}: não informe os mesmos lotes no JSON "
                "e no arquivo (conflito em " + ", ".join(conflitos) + ")."
            )
        combinado.update(dados_importados)
        resultado[categoria] = combinado
    return resultado
