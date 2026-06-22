"""
Cálculo de CAGR de receita e lucro usando dados de DRE (BRAPI ou FMP).
"""

from typing import Optional, List, Dict
from datetime import datetime
import math

def calcular_cagr(valores: List[float]) -> Optional[float]:
    """
    Calcula CAGR a partir de uma lista de valores anuais.
    Exemplo: [100, 120, 150] -> ~22.47%
    """
    if len(valores) < 2:
        return None
    primeiro = valores[0]
    ultimo = valores[-1]
    anos = len(valores) - 1
    if primeiro <= 0:
        return None
    return (ultimo / primeiro) ** (1.0 / anos) - 1

def extrair_receitas_fmp(fmp_client, symbol: str, years: int = 5) -> List[float]:
    """
    Extrai receita anual do FMP.
    """
    try:
        income = fmp_client.get_income_statement(symbol, years=years)
        receitas = []
        for item in income:
            rec = float(item.get("revenue", 0))
            if rec > 0:
                receitas.append(rec)
        return receitas
    except:
        return []

def get_cagr_receita(ticker: str, fmp_client=None, brapi_client=None) -> Optional[float]:
    """
    Obtém CAGR de receita para um ticker.
    Tenta FMP, depois BRAPI (se disponível).
    """
    if fmp_client:
        receitas = extrair_receitas_fmp(fmp_client, ticker, years=5)
        if len(receitas) >= 2:
            return calcular_cagr(receitas)
    # Se não tiver FMP, tenta BRAPI (mas BRAPI free não tem DRE)
    return None