# fundos/utils.py
"""
Funções utilitárias compartilhadas entre os módulos de fundos.
"""

import math
import pandas as pd

DIAS_ANO = 252


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
    return cotas.pct_change().dropna()


def retorno(cotas):
    if len(cotas) < 2:
        return 0.0
    inicial = to_float(cotas.iloc[0])
    final = to_float(cotas.iloc[-1])
    if inicial <= 0:
        return 0.0
    return (final / inicial) - 1


def retorno_periodo(cotas, dias):
    if len(cotas) < dias + 1:
        return None
    serie = cotas.iloc[-(dias + 1):]
    return retorno(serie)


def cagr(cotas, datas):
    if len(cotas) < 2 or len(datas) < 2:
        return None
    if not isinstance(datas.iloc[0], pd.Timestamp):
        datas = pd.to_datetime(datas)
    dias_totais = (datas.iloc[-1] - datas.iloc[0]).days
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
    retornos = serie_retorno(cotas)
    if retornos.empty:
        return None
    return retornos.std() * math.sqrt(DIAS_ANO)


def drawdown(cotas):
    if len(cotas) < 2:
        return None
    maximos = cotas.cummax()
    drawdowns = (cotas / maximos) - 1
    return float(drawdowns.min())


def downside_volatilidade(cotas):
    """Calcula o downside deviation (volatilidade negativa)."""
    retornos = serie_retorno(cotas)
    if retornos.empty:
        return None
    negativos = retornos[retornos < 0]
    if negativos.empty:
        return None
    return negativos.std() * math.sqrt(DIAS_ANO)