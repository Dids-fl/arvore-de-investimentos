"""Simulação de carteira com rebalanceamento, aportes e custos."""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd


def normalizar_pesos(pesos: Mapping[str, float]) -> dict[str, float]:
    if not isinstance(pesos, Mapping):
        raise TypeError("pesos deve ser um mapeamento.")
    resultado = {str(k).upper(): float(v) for k, v in pesos.items()}
    if not resultado:
        raise ValueError("A carteira não possui pesos.")
    if any(valor < 0 for valor in resultado.values()):
        raise ValueError("Pesos negativos não são suportados.")
    total = sum(resultado.values())
    if total <= 0:
        raise ValueError("A soma dos pesos deve ser positiva.")
    return {
        chave: valor / total
        for chave, valor in resultado.items()
        if valor > 0
    }


def calcular_turnover(
    pesos_anteriores: Mapping[str, float],
    pesos_novos: Mapping[str, float],
) -> float:
    novos = normalizar_pesos(pesos_novos)
    if not pesos_anteriores:
        # A primeira compra transforma 100% de caixa em ativos.
        return 1.0
    anteriores = normalizar_pesos(pesos_anteriores)
    chaves = set(anteriores) | set(novos)
    return 0.5 * sum(
        abs(novos.get(chave, 0.0) - anteriores.get(chave, 0.0))
        for chave in chaves
    )


def simular_carteira(
    retornos: pd.DataFrame,
    pesos_por_data: Mapping[object, Mapping[str, float]],
    *,
    custos_bps: float = 0.0,
    capital_inicial: float = 1.0,
    aporte_mensal: float = 0.0,
) -> pd.DataFrame:
    """
    Aplica cada sinal no pregão seguinte, evitando negociação retrospectiva.
    """
    if not isinstance(retornos, pd.DataFrame) or retornos.empty:
        raise ValueError("retornos deve ser um DataFrame não vazio.")
    if custos_bps < 0:
        raise ValueError("custos_bps não pode ser negativo.")
    if capital_inicial < 0 or aporte_mensal < 0:
        raise ValueError("Capital e aporte não podem ser negativos.")
    if not pesos_por_data:
        raise ValueError("Informe pelo menos um sinal de pesos.")

    dados = retornos.copy()
    dados.index = pd.to_datetime(dados.index)
    dados = dados.sort_index().apply(pd.to_numeric, errors="coerce")
    dados.columns = [str(coluna).upper() for coluna in dados]

    sinais = sorted(
        (
            pd.Timestamp(data),
            normalizar_pesos(pesos),
        )
        for data, pesos in pesos_por_data.items()
    )
    for _, pesos in sinais:
        ausentes = set(pesos) - set(dados.columns)
        if ausentes:
            raise ValueError(
                "Ativos sem retornos: " + ", ".join(sorted(ausentes))
            )

    patrimonio = float(capital_inicial)
    pesos_ativos: dict[str, float] = {}
    proximo_sinal = 0
    ultimo_mes: tuple[int, int] | None = None
    linhas = []

    for data, linha in dados.iterrows():
        turnover_dia = 0.0
        while proximo_sinal < len(sinais) and sinais[proximo_sinal][0] < data:
            novos = sinais[proximo_sinal][1]
            turnover_dia += calcular_turnover(pesos_ativos, novos)
            pesos_ativos = novos
            proximo_sinal += 1

        mes_atual = (data.year, data.month)
        aporte = 0.0
        if ultimo_mes is not None and mes_atual != ultimo_mes:
            aporte = float(aporte_mensal)
            patrimonio += aporte
        ultimo_mes = mes_atual

        retorno_bruto = 0.0
        for ticker, peso in pesos_ativos.items():
            valor = linha.get(ticker, 0.0)
            retorno_bruto += peso * (
                0.0
                if pd.isna(valor)
                else float(valor)
            )
        custo = turnover_dia * custos_bps / 10_000.0
        retorno_liquido = retorno_bruto - custo
        patrimonio *= 1.0 + retorno_liquido

        linhas.append(
            {
                "data": data,
                "retorno_bruto": retorno_bruto,
                "custo": custo,
                "retorno_liquido": retorno_liquido,
                "turnover": turnover_dia,
                "aporte": aporte,
                "patrimonio": patrimonio,
            }
        )

    return pd.DataFrame(linhas).set_index("data")


def simular_pesos_constantes(
    retornos: pd.DataFrame,
    pesos: Mapping[str, float],
    **kwargs,
) -> pd.DataFrame:
    """Ativa uma carteira antes da primeira observação de retorno."""
    primeira_data = pd.Timestamp(retornos.index.min())
    sinal = primeira_data - pd.Timedelta(1, unit="ns")
    return simular_carteira(retornos, {sinal: pesos}, **kwargs)