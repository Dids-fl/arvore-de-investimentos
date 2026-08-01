"""Testes parametrizados dos casos tributários mantidos em JSON."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from tributacao import ContextoTributario, calcular_tributacao

FIXTURES_DIR = (
    Path(__file__).resolve().parents[1] / "fixtures" / "tributacao"
)
ARQUIVOS_ESPERADOS = {
    "cripto.json",
    "estruturados.json",
    "fundos.json",
    "previdencia.json",
    "renda_fixa.json",
    "renda_variavel.json",
}
TOTAL_CASOS_ESPERADO = 61


def _carregar_documentos() -> list[tuple[Path, dict[str, Any]]]:
    """Carrega os documentos e rejeita uma coleção incompleta."""
    caminhos = sorted(FIXTURES_DIR.glob("*.json"))
    nomes = {caminho.name for caminho in caminhos}
    if nomes != ARQUIVOS_ESPERADOS:
        faltantes = sorted(ARQUIVOS_ESPERADOS - nomes)
        extras = sorted(nomes - ARQUIVOS_ESPERADOS)
        raise AssertionError(
            "Coleção tributária incorreta. "
            f"Faltantes: {faltantes}; extras: {extras}."
        )

    documentos = []
    for caminho in caminhos:
        with caminho.open(encoding="utf-8") as arquivo:
            documento = json.load(arquivo)
        documentos.append((caminho, documento))
    return documentos


DOCUMENTOS = _carregar_documentos()


def _parametros_casos() -> list[Any]:
    """Converte os casos JSON em parâmetros identificáveis do Pytest."""
    parametros = []
    ids_encontrados: set[str] = set()

    for caminho, documento in DOCUMENTOS:
        tolerancias = documento["tolerancias"]
        for caso in documento["casos"]:
            caso_id = f"{caminho.stem}::{caso['id']}"
            if caso_id in ids_encontrados:
                raise AssertionError(f"Caso tributário duplicado: {caso_id}.")
            ids_encontrados.add(caso_id)
            parametros.append(
                pytest.param(
                    caso,
                    tolerancias,
                    id=caso_id,
                )
            )

    if len(parametros) != TOTAL_CASOS_ESPERADO:
        raise AssertionError(
            "Quantidade inesperada de casos tributários: "
            f"{len(parametros)}; esperado: {TOTAL_CASOS_ESPERADO}."
        )
    return parametros


CASOS = _parametros_casos()


def _criar_contexto(entrada: dict[str, Any]) -> ContextoTributario:
    """Converte datas ISO do JSON para o contrato do motor."""
    dados = dict(entrada)
    dados["data_aplicacao"] = date.fromisoformat(
        dados["data_aplicacao"]
    )
    dados["data_resgate"] = date.fromisoformat(dados["data_resgate"])
    return ContextoTributario(**dados)


def _comparar_numero(
    obtido: float | None,
    esperado: float | None,
    *,
    tolerancia: float,
) -> None:
    """Compara número aproximado, preservando o significado de None."""
    if esperado is None:
        assert obtido is None
        return
    assert obtido is not None
    assert obtido == pytest.approx(esperado, abs=tolerancia)


def test_colecao_possui_metadados_e_fontes_consistentes() -> None:
    """Impede fixtures sem versão, fontes declaradas ou IDs válidos."""
    for caminho, documento in DOCUMENTOS:
        assert documento["_schema_version"] == 1, caminho.name
        assert documento["categoria"] == caminho.stem, caminho.name
        assert documento["validacao_externa"]["status"], caminho.name
        assert documento["fontes"], caminho.name

        fonte_ids = set(documento["fontes"])
        for caso in documento["casos"]:
            assert caso["id"], caminho.name
            assert caso["natureza"], caso["id"]
            assert set(caso["fonte_ids"]) <= fonte_ids, caso["id"]


@pytest.mark.parametrize(("caso", "tolerancias"), CASOS)
def test_caso_tributario_dourado(
    caso: dict[str, Any],
    tolerancias: dict[str, float],
) -> None:
    """Compara o motor atual com o resultado esperado da fixture."""
    contexto = _criar_contexto(caso["entrada"])
    resultado = calcular_tributacao(contexto)
    esperado = caso["esperado"]

    _comparar_numero(
        resultado.imposto_estimado,
        esperado["imposto_estimado"],
        tolerancia=tolerancias["monetaria"],
    )
    _comparar_numero(
        resultado.valor_liquido,
        esperado["valor_liquido"],
        tolerancia=tolerancias["monetaria"],
    )
    _comparar_numero(
        resultado.aliquota_efetiva,
        esperado["aliquota_efetiva"],
        tolerancia=tolerancias["aliquota"],
    )
    assert resultado.precisao.value == esperado["precisao"]
    assert resultado.regra_id == esperado["regra_id"]