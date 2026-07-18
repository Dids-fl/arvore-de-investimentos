# fundos/utils.py
"""
Funções utilitárias compartilhadas entre os módulos de fundos.
"""

import math
import pandas as pd
import numpy as np

DIAS_ANO = 252


def _para_series(dados):
    """Converte para pd.Series se for array-like."""
    if isinstance(dados, (np.ndarray, list)):
        return pd.Series(dados)
    return dados


def _para_datetime_index(datas):
    """Garante que datas seja um Index ou Series, e converte para datetime se necessário."""
    if isinstance(datas, pd.DatetimeIndex):
        return datas
    if isinstance(datas, pd.Series):
        return pd.to_datetime(datas)
    if isinstance(datas, (np.ndarray, list)):
        return pd.to_datetime(datas)
    return datas


def to_float(valor):
    try:
        if valor is None:
            return 0.0
        if pd.isna(valor):
            return 0.0
        return float(valor)
    except Exception:
        return 0.0


def serie_retorno(cotas):
    cotas = _para_series(cotas)
    retornos = cotas.pct_change()
    # Remove +inf/-inf (ex.: cota anterior igual a 0 ou dado corrompido) além
    # de NaN. inf não é removido por dropna() sozinho e, se sobrar na série,
    # corrompe std()/volatilidade com RuntimeWarning e resultado NaN silencioso.
    retornos = retornos.replace([np.inf, -np.inf], np.nan).dropna()
    return retornos


def retorno(cotas):
    cotas = _para_series(cotas)
    if len(cotas) < 2:
        return 0.0
    inicial = to_float(cotas.iloc[0])
    final = to_float(cotas.iloc[-1])
    if inicial <= 0:
        return 0.0
    return (final / inicial) - 1


def retorno_periodo(cotas, dias):
    cotas = _para_series(cotas)
    if len(cotas) < dias + 1:
        return None
    serie = cotas.iloc[-(dias + 1):]
    return retorno(serie)


def cagr(cotas, datas):
    cotas = _para_series(cotas)
    datas = _para_datetime_index(datas)
    if len(cotas) < 2 or len(datas) < 2:
        return None
    # datas pode ser um Index ou Series
    if isinstance(datas, pd.DatetimeIndex):
        data_inicio = datas[0]
        data_fim = datas[-1]
    else:
        data_inicio = datas.iloc[0]
        data_fim = datas.iloc[-1]
    if not isinstance(data_inicio, pd.Timestamp):
        data_inicio = pd.to_datetime(data_inicio)
        data_fim = pd.to_datetime(data_fim)
    dias_totais = (data_fim - data_inicio).days
    if dias_totais <= 0:
        return None
    anos = dias_totais / 365.25
    if anos <= 0:
        return None
    inicial = to_float(cotas.iloc[0])
    final = to_float(cotas.iloc[-1])
    if inicial <= 0:
        return None
    return (final / inicial) ** (1 / anos) - 1


def volatilidade(cotas):
    cotas = _para_series(cotas)
    retornos = serie_retorno(cotas)
    if retornos.empty:
        return None
    return retornos.std() * math.sqrt(DIAS_ANO)


def drawdown(cotas):
    cotas = _para_series(cotas)
    if len(cotas) < 2:
        return None
    maximos = cotas.cummax()
    drawdowns = (cotas / maximos) - 1
    return float(drawdowns.min())


def downside_volatilidade(cotas):
    """Calcula o downside deviation (volatilidade negativa)."""
    cotas = _para_series(cotas)
    retornos = serie_retorno(cotas)
    if retornos.empty:
        return None
    negativos = retornos[retornos < 0]
    if negativos.empty:
        return None
    return negativos.std() * math.sqrt(DIAS_ANO)