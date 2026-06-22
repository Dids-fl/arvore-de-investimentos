"""
Backtester para avaliar performance do ranking de ações.
Simula compra das top N ações em uma data passada e compara com Ibovespa.
"""

import yfinance as yf
import pandas as pd
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from screener import top_acoes
from utils.logging_config import get_logger

logger = get_logger(__name__)

def backtest_ranking(perfil: int, n: int = 5, anos: int = 1) -> Dict:
    """
    Simula compra das top N ações para um perfil em uma data passada (ex: 1 ano atrás)
    e calcula retorno acumulado vs Ibovespa.
    """
    data_fim = datetime.now()
    data_ini = data_fim - timedelta(days=anos*365)
    
    # Buscar ranking baseado em dados atuais (não temos histórico de indicadores)
    # Para simular, usamos dados atuais e assumimos que o ranking seria similar.
    # Melhor: usar dados históricos de indicadores (não disponível).
    logger.warning("Backtester usa dados atuais como proxy; não é histórico real.")
    
    tickers = [ativo['ticker'] for ativo in top_acoes(perfil, n=n)]
    if not tickers:
        return {"erro": "Nenhum ativo encontrado"}
    
    # Baixar dados históricos
    try:
        df = yf.download(tickers, start=data_ini, end=data_fim, group_by='ticker')
        # Calcular retorno acumulado igualmente ponderado
        retornos = []
        for t in tickers:
            if t in df.columns:
                preco_ini = df[t]['Close'].iloc[0]
                preco_fim = df[t]['Close'].iloc[-1]
                ret = (preco_fim / preco_ini) - 1
                retornos.append(ret)
        ret_medio = sum(retornos) / len(retornos) if retornos else 0
        # Ibovespa
        ibov = yf.download('^BVSP', start=data_ini, end=data_fim)
        ret_ibov = (ibov['Close'].iloc[-1] / ibov['Close'].iloc[0]) - 1
        return {
            "perfil": perfil,
            "n": n,
            "periodo": f"{data_ini.date()} a {data_fim.date()}",
            "retorno_carteira": ret_medio,
            "retorno_ibov": ret_ibov,
            "alpha": ret_medio - ret_ibov,
            "tickers": tickers,
        }
    except Exception as e:
        return {"erro": str(e)}