"""Propriedades do backtest e proteção contra look-ahead."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backtest.benchmarks import benchmark_cdi, retorno_carteira_fixa
from backtest.data_loader import (
    calcular_retornos,
    carregar_csv,
    janela_disponivel,
    validar_precos,
)
from backtest.metrics import max_drawdown, resumo_metricas
from backtest.portfolio_simulator import (
    calcular_turnover,
    simular_pesos_constantes,
)
from backtest.walk_forward import executar_walk_forward


@pytest.fixture
def precos_sinteticos() -> pd.DataFrame:
    datas = pd.bdate_range("2020-01-01", periods=320)
    return pd.DataFrame(
        {
            "AAA": 100 * np.cumprod(np.full(len(datas), 1.0010)),
            "BBB": 100 * np.cumprod(np.full(len(datas), 1.0005)),
            "CCC": 100 * np.cumprod(np.full(len(datas), 0.9998)),
        },
        index=datas,
    )


def test_validar_precos_rejeita_historico_vazio() -> None:
    with pytest.raises(ValueError):
        validar_precos(pd.DataFrame())


def test_csv_e_janela_respeitam_data_corte(
    tmp_path,
    precos_sinteticos,
) -> None:
    caminho = tmp_path / "precos.csv"
    precos_sinteticos.rename_axis("date").to_csv(caminho)
    carregados = carregar_csv(caminho)
    corte = carregados.index[99]
    janela = janela_disponivel(carregados, corte, observacoes=60)
    assert len(janela) == 60
    assert janela.index.max() == corte


def test_turnover_total_entre_carteiras_opostas() -> None:
    assert calcular_turnover({"AAA": 1}, {"BBB": 1}) == pytest.approx(1)


def test_simulacao_constante_cresce(precos_sinteticos) -> None:
    retornos = calcular_retornos(precos_sinteticos)
    simulacao = simular_pesos_constantes(retornos, {"AAA": 1})
    assert simulacao["patrimonio"].iloc[-1] > 1
    assert simulacao["turnover"].sum() == pytest.approx(1)


def test_walk_forward_nao_entrega_futuro_ao_ranker(
    precos_sinteticos,
) -> None:
    chamadas = []

    def ranker(historico, data_sinal):
        assert historico.index.max() <= data_sinal
        chamadas.append((historico.index.max(), data_sinal))
        retorno = historico.iloc[-1] / historico.iloc[0] - 1
        return retorno.to_dict()

    resultado = executar_walk_forward(
        precos_sinteticos,
        ranker,
        lookback_observacoes=60,
        rebalancear_a_cada=40,
        top_n=2,
        custos_bps=5,
    )
    assert chamadas
    assert resultado.sinais
    assert resultado.metricas["observacoes"] > 0
    assert resultado.simulacao.index.min() > min(resultado.sinais)


def test_metricas_para_serie_sem_quedas() -> None:
    retornos = pd.Series([0.001] * 252)
    metricas = resumo_metricas(retornos)
    assert metricas["retorno_anualizado"] > 0
    assert max_drawdown(retornos) == pytest.approx(0)


def test_benchmarks_tem_mesmo_indice(precos_sinteticos) -> None:
    retornos = calcular_retornos(precos_sinteticos)
    cdi = benchmark_cdi(retornos.index, 0.10)
    carteira = retorno_carteira_fixa(
        retornos,
        {"AAA": 0.5, "BBB": 0.5},
    )
    assert cdi.index.equals(retornos.index)
    assert carteira.index.equals(retornos.index)
