"""Testes da interface de linha de comando do backtest."""

from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import pandas as pd
import pytest

from backtest import run_backtest


def test_construir_parser_aplica_valores_padrao() -> None:
    argumentos = run_backtest.construir_parser().parse_args(["precos.csv"])
    assert argumentos.csv == "precos.csv"
    assert argumentos.lookback == 252
    assert argumentos.rebalanceamento == 63
    assert argumentos.top == 5
    assert argumentos.custos_bps == pytest.approx(10.0)
    assert argumentos.capital == pytest.approx(1.0)
    assert argumentos.aporte_mensal == pytest.approx(0.0)


def test_main_encaminha_argumentos_e_imprime_json(
    monkeypatch,
    capsys,
) -> None:
    precos = pd.DataFrame(
        {"AAA": [100.0, 101.0, 102.0]},
        index=pd.date_range("2024-01-01", periods=3),
    )
    chamadas: dict = {}

    def carregar_csv_falso(caminho, *, minimo_observacoes):
        chamadas["csv"] = caminho
        chamadas["minimo_observacoes"] = minimo_observacoes
        return precos

    def executar_falso(dados, ranker, **kwargs):
        chamadas["dados"] = dados
        chamadas["ranker"] = ranker
        chamadas["kwargs"] = kwargs
        return SimpleNamespace(
            metricas={
                "retorno_anualizado": 0.123,
                "observacoes": 2,
            }
        )

    monkeypatch.setattr(run_backtest, "carregar_csv", carregar_csv_falso)
    monkeypatch.setattr(
        run_backtest,
        "executar_walk_forward",
        executar_falso,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_backtest",
            "dados.csv",
            "--lookback",
            "2",
            "--rebalanceamento",
            "5",
            "--top",
            "2",
            "--custos-bps",
            "15",
            "--capital",
            "1000",
            "--aporte-mensal",
            "100",
        ],
    )

    run_backtest.main()

    saida = json.loads(capsys.readouterr().out)
    assert saida == {
        "retorno_anualizado": 0.123,
        "observacoes": 2,
    }
    assert chamadas["csv"] == "dados.csv"
    assert chamadas["minimo_observacoes"] == 3
    assert chamadas["dados"] is precos
    assert chamadas["ranker"] is run_backtest.momentum_ranker
    assert chamadas["kwargs"] == {
        "lookback_observacoes": 2,
        "rebalancear_a_cada": 5,
        "top_n": 2,
        "custos_bps": 15.0,
        "capital_inicial": 1000.0,
        "aporte_mensal": 100.0,
    }
