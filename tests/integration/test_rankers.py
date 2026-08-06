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


def test_prazo_e_data_chegam_ao_ranker_de_fundos(monkeypatch) -> None:
    recebidos = {}

    def executar(
        classe,
        perfil,
        limite,
        *,
        prazo_anos=None,
        data_referencia=None,
        retorno_esperado_fundos=None,
    ):
        recebidos.update(
            {
                "classe": classe,
                "perfil": perfil,
                "limite": limite,
                "prazo_anos": prazo_anos,
                "data_referencia": data_referencia,
                "retorno_esperado_fundos": retorno_esperado_fundos,
            }
        )
        return []

    monkeypatch.setattr(recomendador_ativos, "_executar_classe", executar)
    recomendador_ativos.recomendar_por_portfolio(
        {RK.FUNDOS: 100},
        perfil_risco=2,
        n=3,
        prazo_anos=10,
        data_referencia="2026-07-29",
        retorno_esperado_fundos=0.11,
    )

    assert recebidos == {
        "classe": "fundos",
        "perfil": 2,
        "limite": 3,
        "prazo_anos": 10,
        "data_referencia": "2026-07-29",
        "retorno_esperado_fundos": 0.11,
    }


@pytest.mark.parametrize(
    ("classe", "score_origem", "esperado"),
    [
        ("rf", 8.5, 85.0),
        ("fundos", 7.2, 72.0),
        ("estruturados", 6.0, 60.0),
        ("fiis", 55.5, 55.5),
        ("acoes", 81.0, 81.0),
        ("etf", 74.0, 74.0),
        ("cripto", 63.0, 63.0),
    ],
)
def test_scores_publicos_sao_padronizados_em_cem(
    classe,
    score_origem,
    esperado,
) -> None:
    resultado = recomendador_ativos._padronizar_scores(
        classe,
        [{"ticker": "TESTE", "score": score_origem}],
    )

    assert resultado[0]["score"] == pytest.approx(esperado)
    assert resultado[0]["score_escala"] == 100
