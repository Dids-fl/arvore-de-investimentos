"""CLI mínima para executar um backtest de momentum sobre um CSV."""

from __future__ import annotations

import argparse
import json

from backtest.data_loader import carregar_csv
from backtest.walk_forward import executar_walk_forward, momentum_ranker


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Executa walk-forward sobre CSV no formato "
            "date,TICKER1,TICKER2,..."
        )
    )
    parser.add_argument("csv", help="Caminho do CSV de preços.")
    parser.add_argument("--lookback", type=int, default=252)
    parser.add_argument("--rebalanceamento", type=int, default=63)
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--custos-bps", type=float, default=10.0)
    parser.add_argument("--capital", type=float, default=1.0)
    parser.add_argument("--aporte-mensal", type=float, default=0.0)
    return parser


def main() -> None:
    argumentos = construir_parser().parse_args()
    precos = carregar_csv(
        argumentos.csv,
        minimo_observacoes=argumentos.lookback + 1,
    )
    resultado = executar_walk_forward(
        precos,
        momentum_ranker,
        lookback_observacoes=argumentos.lookback,
        rebalancear_a_cada=argumentos.rebalanceamento,
        top_n=argumentos.top,
        custos_bps=argumentos.custos_bps,
        capital_inicial=argumentos.capital,
        aporte_mensal=argumentos.aporte_mensal,
    )
    print(json.dumps(resultado.metricas, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
