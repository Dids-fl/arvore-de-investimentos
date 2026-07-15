# fundos/sharpe_sortino.py
"""
Cálculo de Sharpe e Sortino usando a taxa CDI do período.
"""
import pandas as pd
from macroeconomia.cdi import obter_cdi_periodo
from .utils import cagr, volatilidade, downside_volatilidade


def _obter_cdi_para_periodo(datas):
    if len(datas) < 2:
        return None
    # datas pode ser pd.DatetimeIndex ou pd.Series
    if isinstance(datas, pd.DatetimeIndex):
        data_inicio = datas[0].strftime("%Y-%m-%d")
        data_fim = datas[-1].strftime("%Y-%m-%d")
    else:
        if not isinstance(datas.iloc[0], pd.Timestamp):
            datas = pd.to_datetime(datas)
        data_inicio = datas.iloc[0].strftime("%Y-%m-%d")
        data_fim = datas.iloc[-1].strftime("%Y-%m-%d")
    return obter_cdi_periodo(data_inicio, data_fim)


def calcular_sharpe(cotas, datas, taxa_livre_risco=None):
    ret = cagr(cotas, datas)
    vol = volatilidade(cotas)
    if ret is None or vol is None or vol == 0:
        return None
    if taxa_livre_risco is None:
        taxa_livre_risco = _obter_cdi_para_periodo(datas)
    if taxa_livre_risco is None:
        return None
    return (ret - taxa_livre_risco) / vol


def calcular_sortino(cotas, datas, taxa_livre_risco=None):
    ret = cagr(cotas, datas)
    downside = downside_volatilidade(cotas)
    if ret is None or downside is None or downside == 0:
        return None
    if taxa_livre_risco is None:
        taxa_livre_risco = _obter_cdi_para_periodo(datas)
    if taxa_livre_risco is None:
        return None
    return (ret - taxa_livre_risco) / downside


def calcular_indicadores_risco(cotas, datas, taxa_livre_risco=None):
    return {
        "sharpe": calcular_sharpe(cotas, datas, taxa_livre_risco),
        "sortino": calcular_sortino(cotas, datas, taxa_livre_risco),
    }