"""Contrato do orquestrador de rankers sem consultar fontes externas."""

from __future__ import annotations

import pytest

recomendador_ativos = pytest.importorskip("recomendador_ativos")
categorias = pytest.importorskip("core.categorias")
RK = categorias.RK


def test_portfolio_consulta_somente_classes_relevantes(
    monkeypatch,
    carregar_fixture,
) -> None:
    fixture = carregar_fixture("ativos.json")
    chamadas = []

    def executar(classe, perfil, limite):
        chamadas.append((classe, perfil, limite))
        return fixture[classe][:limite]

    monkeypatch.setattr(recomendador_ativos, "_executar_classe", executar)
    resultado = recomendador_ativos.recomendar_por_portfolio(
        {RK.RF: 60, RK.RV: 40},
        perfil_risco=2,
        n=2,
    )
    assert {classe for classe, _, _ in chamadas} == {"rf", "acoes"}
    assert len(resultado["rf"]) == 2
    assert resultado["_indisponiveis"] == {}


def test_falha_de_uma_classe_nao_apaga_as_demais(monkeypatch) -> None:
    def executar(classe, perfil, limite):
        del perfil, limite
        if classe == "acoes":
            raise RuntimeError("fonte fora do ar")
        return [{"ticker": "TESOURO"}]

    monkeypatch.setattr(recomendador_ativos, "_executar_classe", executar)
    resultado, falhas = recomendador_ativos._buscar_classes(
        {"rf", "acoes"},
        perfil_risco=2,
        n=2,
    )
    assert resultado["rf"]
    assert "acoes" in falhas
