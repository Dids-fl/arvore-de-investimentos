"""Ferramentas de backtest sem vazamento temporal para o recomendador."""

from backtest.benchmarks import benchmark_cdi, montar_benchmarks
from backtest.data_loader import (
    calcular_retornos,
    carregar_csv,
    carregar_yfinance,
    janela_disponivel,
    validar_precos,
)
from backtest.metrics import comparar_series, resumo_metricas
from backtest.portfolio_simulator import (
    calcular_turnover,
    simular_carteira,
    simular_pesos_constantes,
)
from backtest.walk_forward import (
    ResultadoWalkForward,
    executar_walk_forward,
    momentum_ranker,
)

__all__ = [
    "ResultadoWalkForward",
    "benchmark_cdi",
    "calcular_retornos",
    "calcular_turnover",
    "carregar_csv",
    "carregar_yfinance",
    "comparar_series",
    "executar_walk_forward",
    "janela_disponivel",
    "momentum_ranker",
    "montar_benchmarks",
    "resumo_metricas",
    "simular_carteira",
    "simular_pesos_constantes",
    "validar_precos",
]
