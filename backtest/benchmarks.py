"""Benchmarks reproduzíveis para comparação do backtest."""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd


def benchmark_cdi(
    indice: pd.Index,
    taxa_anual: float | pd.Series,
    *,
    periodos_ano: int = 252,
) -> pd.Series:
    """Converte uma taxa CDI anual em retornos por pregão."""
    if periodos_ano <= 0:
        raise ValueError("periodos_ano deve ser positivo.")
    datas = pd.DatetimeIndex(pd.to_datetime(indice))

    if isinstance(taxa_anual, pd.Series):
        taxas = taxa_anual.copy()
        taxas.index = pd.to_datetime(taxas.index)
        taxas = taxas.reindex(datas).ffill()
    else:
        taxas = pd.Series(float(taxa_anual), index=datas)

    if taxas.isna().any() or (taxas <= -1).any():
        raise ValueError("A série CDI contém taxas ausentes ou inválidas.")
    diario = (1.0 + taxas.astype(float)) ** (1.0 / periodos_ano) - 1.0
    diario.name = "CDI"
    return diario


def retorno_carteira_fixa(
    retornos: pd.DataFrame,
    pesos: Mapping[str, float],
) -> pd.Series:
    """Benchmark com pesos constantes e rebalanceamento diário."""
    if not isinstance(retornos, pd.DataFrame) or retornos.empty:
        raise ValueError("retornos deve ser um DataFrame não vazio.")
    dados = retornos.copy()
    dados.columns = [str(coluna).upper() for coluna in dados]
    normalizados = {str(k).upper(): float(v) for k, v in pesos.items()}
    desconhecidos = set(normalizados) - set(dados.columns)
    if desconhecidos:
        raise ValueError(
            "Ativos ausentes nos retornos: " + ", ".join(sorted(desconhecidos))
        )
    if any(valor < 0 for valor in normalizados.values()):
        raise ValueError("Pesos negativos não são aceitos neste benchmark.")
    total = sum(normalizados.values())
    if total <= 0:
        raise ValueError("A soma dos pesos deve ser positiva.")
    normalizados = {chave: valor / total for chave, valor in normalizados.items()}
    serie = dados[list(normalizados)].fillna(0).mul(
        pd.Series(normalizados)
    ).sum(axis=1)
    serie.name = "Carteira fixa"
    return serie


def montar_benchmarks(
    retornos: pd.DataFrame,
    *,
    cdi_anual: float | pd.Series | None = None,
    coluna_ibov: str | None = None,
) -> pd.DataFrame:
    """Cria CDI, carteira equiponderada e Ibovespa quando disponíveis."""
    if not isinstance(retornos, pd.DataFrame) or retornos.empty:
        raise ValueError("retornos deve ser um DataFrame não vazio.")
    saida: dict[str, pd.Series] = {}

    pesos_iguais = {
        coluna: 1.0 / len(retornos.columns)
        for coluna in retornos.columns
    }
    equiponderado = retorno_carteira_fixa(retornos, pesos_iguais)
    saida["EQUIPONDERADO"] = equiponderado

    if cdi_anual is not None:
        saida["CDI"] = benchmark_cdi(retornos.index, cdi_anual)

    if coluna_ibov is not None:
        chave = coluna_ibov.upper()
        if chave not in retornos:
            raise ValueError(f"Benchmark {chave!r} não está nos retornos.")
        saida["IBOVESPA"] = retornos[chave].fillna(0)

    return pd.DataFrame(saida, index=retornos.index)
