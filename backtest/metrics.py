"""Métricas de retorno e risco usadas na validação quantitativa."""

from __future__ import annotations

import math

import pandas as pd


def _serie_valida(retornos: pd.Series) -> pd.Series:
    if not isinstance(retornos, pd.Series):
        raise TypeError("retornos deve ser uma pandas.Series.")
    serie = pd.to_numeric(retornos, errors="coerce").dropna().astype(float)
    serie = serie.replace([float("inf"), float("-inf")], pd.NA).dropna()
    if serie.empty:
        raise ValueError("A série de retornos está vazia.")
    if (serie <= -1).any():
        raise ValueError("Retornos iguais ou inferiores a -100% são inválidos.")
    return serie


def retorno_anualizado(
    retornos: pd.Series,
    *,
    periodos_ano: int = 252,
) -> float:
    serie = _serie_valida(retornos)
    crescimento = float((1.0 + serie).prod())
    return crescimento ** (periodos_ano / len(serie)) - 1.0


def volatilidade_anualizada(
    retornos: pd.Series,
    *,
    periodos_ano: int = 252,
) -> float:
    serie = _serie_valida(retornos)
    if len(serie) < 2:
        return 0.0
    return float(serie.std(ddof=1) * math.sqrt(periodos_ano))


def sharpe(
    retornos: pd.Series,
    *,
    taxa_livre_anual: float = 0.0,
    periodos_ano: int = 252,
) -> float:
    serie = _serie_valida(retornos)
    vol = volatilidade_anualizada(serie, periodos_ano=periodos_ano)
    if vol == 0:
        return float("nan")
    return (
        retorno_anualizado(serie, periodos_ano=periodos_ano)
        - taxa_livre_anual
    ) / vol


def sortino(
    retornos: pd.Series,
    *,
    taxa_livre_anual: float = 0.0,
    periodos_ano: int = 252,
) -> float:
    serie = _serie_valida(retornos)
    negativos = serie.clip(upper=0)
    downside = float((negativos.pow(2).mean() ** 0.5) * math.sqrt(periodos_ano))
    if downside == 0:
        return float("nan")
    excesso = (
        retorno_anualizado(serie, periodos_ano=periodos_ano)
        - taxa_livre_anual
    )
    return excesso / downside


def max_drawdown(retornos: pd.Series) -> float:
    serie = _serie_valida(retornos)
    patrimonio = (1.0 + serie).cumprod()
    picos = patrimonio.cummax()
    drawdown = patrimonio / picos - 1.0
    return float(drawdown.min())


def var_historico(retornos: pd.Series, *, nivel: float = 0.95) -> float:
    if not 0 < nivel < 1:
        raise ValueError("nivel deve estar entre 0 e 1.")
    serie = _serie_valida(retornos)
    return float(serie.quantile(1.0 - nivel))


def cvar_historico(retornos: pd.Series, *, nivel: float = 0.95) -> float:
    serie = _serie_valida(retornos)
    limite = var_historico(serie, nivel=nivel)
    cauda = serie[serie <= limite]
    return float(cauda.mean()) if not cauda.empty else limite


def resumo_metricas(
    retornos: pd.Series,
    *,
    taxa_livre_anual: float = 0.0,
    periodos_ano: int = 252,
) -> dict[str, float]:
    serie = _serie_valida(retornos)
    anual = retorno_anualizado(serie, periodos_ano=periodos_ano)
    drawdown = max_drawdown(serie)
    return {
        "retorno_anualizado": anual,
        "volatilidade_anualizada": volatilidade_anualizada(
            serie,
            periodos_ano=periodos_ano,
        ),
        "sharpe": sharpe(
            serie,
            taxa_livre_anual=taxa_livre_anual,
            periodos_ano=periodos_ano,
        ),
        "sortino": sortino(
            serie,
            taxa_livre_anual=taxa_livre_anual,
            periodos_ano=periodos_ano,
        ),
        "max_drawdown": drawdown,
        "calmar": anual / abs(drawdown) if drawdown < 0 else float("nan"),
        "var_95": var_historico(serie),
        "cvar_95": cvar_historico(serie),
        "percentual_positivo": float((serie > 0).mean()),
        "observacoes": float(len(serie)),
    }


def comparar_series(
    series: pd.DataFrame,
    *,
    taxa_livre_anual: float = 0.0,
    periodos_ano: int = 252,
) -> pd.DataFrame:
    """Calcula as mesmas métricas para estratégia e benchmarks."""
    if not isinstance(series, pd.DataFrame) or series.empty:
        raise ValueError("series deve ser um DataFrame não vazio.")
    resultado = {
        coluna: resumo_metricas(
            series[coluna],
            taxa_livre_anual=taxa_livre_anual,
            periodos_ano=periodos_ano,
        )
        for coluna in series
    }
    return pd.DataFrame(resultado).T
