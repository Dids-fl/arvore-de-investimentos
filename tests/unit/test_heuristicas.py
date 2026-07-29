"""Cenários de adequação; não medem desempenho histórico dos ativos."""

from __future__ import annotations

import pytest

engine = pytest.importorskip("engine")
categorias = pytest.importorskip("core.categorias")


def _verificar_restricoes(analise: dict, restricoes: dict) -> None:
    resultado = analise["resultado"]
    if "nivel_risco_maximo" in restricoes:
        assert (
            resultado["nivel_risco_perfil"]
            <= restricoes["nivel_risco_maximo"]
        )
    if "risco_recomendacao_maximo" in restricoes:
        assert (
            categorias._risco(resultado["recomendacao_principal"])
            <= restricoes["risco_recomendacao_maximo"]
        )
    for categoria in restricoes.get("categorias_proibidas", []):
        assert resultado["portfolio"].get(categoria, 0) == 0
    if "aporte_mensal_esperado" in restricoes:
        assert (
            analise["respostas"]["aporte_mensal"]
            == restricoes["aporte_mensal_esperado"]
        )
    if "liquidez_pct_esperada" in restricoes:
        assert (
            analise["respostas"]["liquidez_pct"]
            == restricoes["liquidez_pct_esperada"]
        )
    if restricoes.get("portfolio_soma_cem"):
        assert sum(resultado["portfolio"].values()) == 100


def test_cenarios_de_adequacao(
    carregar_fixture,
    respostas_padrao,
    mercado_valido,
) -> None:
    cenarios = carregar_fixture("perfis_validacao.json")
    for cenario in cenarios:
        respostas = {
            **respostas_padrao,
            **cenario["respostas"],
        }
        restricoes = cenario["restricoes"]
        if restricoes.get("bloqueia"):
            with pytest.raises(engine.RecomendacaoBloqueadaError):
                engine.criar_analise(respostas, mercado_valido)
            continue

        analise = engine.criar_analise(respostas, mercado_valido)
        _verificar_restricoes(analise, restricoes)
