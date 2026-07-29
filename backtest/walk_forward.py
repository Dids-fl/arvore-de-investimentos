"""Orquestração walk-forward para rankings de ativos."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import pandas as pd

from backtest.data_loader import calcular_retornos, validar_precos
from backtest.metrics import comparar_series, resumo_metricas
from backtest.portfolio_simulator import simular_carteira


Ranker = Callable[[pd.DataFrame, pd.Timestamp], Mapping[str, float] | Sequence[str]]


@dataclass(frozen=True)
class ResultadoWalkForward:
    simulacao: pd.DataFrame
    sinais: dict[pd.Timestamp, dict[str, float]]
    metricas: dict[str, float]
    comparacao: pd.DataFrame | None


def _selecionar(
    ranking: Mapping[str, float] | Sequence[str],
    *,
    top_n: int,
    universo: set[str],
) -> list[str]:
    if isinstance(ranking, Mapping):
        ordenados = [
            str(ticker).upper()
            for ticker, _ in sorted(
                ranking.items(),
                key=lambda item: float(item[1]),
                reverse=True,
            )
        ]
    elif isinstance(ranking, Sequence) and not isinstance(ranking, str):
        ordenados = [str(ticker).upper() for ticker in ranking]
    else:
        raise TypeError("O ranker deve retornar scores ou uma sequência.")

    selecionados = []
    for ticker in ordenados:
        if ticker in universo and ticker not in selecionados:
            selecionados.append(ticker)
        if len(selecionados) == top_n:
            break
    if not selecionados:
        raise ValueError("O ranking não selecionou nenhum ativo do universo.")
    return selecionados


def executar_walk_forward(
    precos: pd.DataFrame,
    ranker: Ranker,
    *,
    lookback_observacoes: int = 252,
    rebalancear_a_cada: int = 63,
    top_n: int = 5,
    custos_bps: float = 10.0,
    capital_inicial: float = 1.0,
    aporte_mensal: float = 0.0,
    benchmarks: pd.DataFrame | None = None,
    taxa_livre_anual: float = 0.0,
) -> ResultadoWalkForward:
    """Executa ranking usando somente preços conhecidos em cada decisão."""
    if not callable(ranker):
        raise TypeError("ranker deve ser chamável.")
    if lookback_observacoes < 2:
        raise ValueError("lookback_observacoes deve ser pelo menos 2.")
    if rebalancear_a_cada < 1 or top_n < 1:
        raise ValueError("Frequência e top_n devem ser positivos.")

    dados = validar_precos(
        precos,
        minimo_observacoes=lookback_observacoes + 1,
    )
    universo = set(dados.columns)
    sinais: dict[pd.Timestamp, dict[str, float]] = {}

    indices_sinal = range(
        lookback_observacoes - 1,
        len(dados) - 1,
        rebalancear_a_cada,
    )
    for indice in indices_sinal:
        data_sinal = pd.Timestamp(dados.index[indice])
        historico = dados.iloc[
            indice - lookback_observacoes + 1 : indice + 1
        ].copy()
        ranking = ranker(historico, data_sinal)
        selecionados = _selecionar(
            ranking,
            top_n=top_n,
            universo=universo,
        )
        peso = 1.0 / len(selecionados)
        sinais[data_sinal] = {ticker: peso for ticker in selecionados}

    retornos = calcular_retornos(dados)
    inicio = min(sinais)
    retornos_teste = retornos.loc[retornos.index > inicio]
    simulacao = simular_carteira(
        retornos_teste,
        sinais,
        custos_bps=custos_bps,
        capital_inicial=capital_inicial,
        aporte_mensal=aporte_mensal,
    )
    metricas = resumo_metricas(
        simulacao["retorno_liquido"],
        taxa_livre_anual=taxa_livre_anual,
    )
    metricas["turnover_total"] = float(simulacao["turnover"].sum())
    metricas["custo_total_retorno"] = float(simulacao["custo"].sum())

    comparacao = None
    if benchmarks is not None:
        comparaveis = benchmarks.reindex(simulacao.index).copy()
        comparaveis.insert(
            0,
            "ESTRATEGIA",
            simulacao["retorno_liquido"],
        )
        comparacao = comparar_series(
            comparaveis.dropna(how="all"),
            taxa_livre_anual=taxa_livre_anual,
        )

    return ResultadoWalkForward(
        simulacao=simulacao,
        sinais=sinais,
        metricas=metricas,
        comparacao=comparacao,
    )


def momentum_ranker(
    historico: pd.DataFrame,
    data_sinal: pd.Timestamp,
) -> dict[str, float]:
    """Ranker demonstrativo: retorno da janela, sem dados posteriores."""
    del data_sinal
    janela = validar_precos(historico)
    primeiro = janela.ffill().iloc[0]
    ultimo = janela.ffill().iloc[-1]
    scores = ultimo / primeiro - 1.0
    return {
        str(ticker): float(score)
        for ticker, score in scores.dropna().items()
    }
