# renda_fixa/fallback.py
"""
Dados fixos de emergência para Renda Fixa.
Usado quando as fontes oficiais (BCB, Tesouro) falham.
"""
from datetime import datetime, timedelta

FALLBACK_RF = [
    {
        "ticker": "TD-SELIC",
        "nome": "Tesouro Selic 2029",
        "tipo": "Tesouro",
        "taxa_bruta": 0.105,  # 10.5% aa (aproximado)
        "vencimento": "2029-03-01",
        "garantia": "Governo Federal",
        "liquidez": "D+0",
        "ir": "15% (>720d)",
        "isento_ir": False,
        "prazo_dias": 1095,
        "score_bruto": 0.0
    },
    {
        "ticker": "TD-IPCA",
        "nome": "Tesouro IPCA+ 2045",
        "tipo": "Tesouro",
        "taxa_bruta": 0.06,  # 6% + IPCA
        "vencimento": "2045-05-15",
        "garantia": "Governo Federal",
        "liquidez": "D+1",
        "ir": "15% (>720d)",
        "isento_ir": False,
        "prazo_dias": 7300,
        "score_bruto": 0.0
    },
    {
        "ticker": "CDB-100",
        "nome": "CDB 100% CDI",
        "tipo": "CDB",
        "taxa_bruta": 0.105,  # baseado em CDI 10.5%
        "vencimento": (datetime.now() + timedelta(days=365)).strftime("%Y-%m-%d"),
        "garantia": "FGC",
        "liquidez": "Diária",
        "ir": "15% (>720d)",
        "isento_ir": False,
        "prazo_dias": 365,
        "score_bruto": 0.0
    },
    {
        "ticker": "CDB-115",
        "nome": "CDB 115% CDI",
        "tipo": "CDB",
        "taxa_bruta": 0.12075,  # 10.5 * 1.15
        "vencimento": (datetime.now() + timedelta(days=720)).strftime("%Y-%m-%d"),
        "garantia": "FGC",
        "liquidez": "Diária",
        "ir": "15% (>720d)",
        "isento_ir": False,
        "prazo_dias": 720,
        "score_bruto": 0.0
    },
    {
        "ticker": "LCI-90",
        "nome": "LCI 90% CDI",
        "tipo": "LCI",
        "taxa_bruta": 0.0945,  # 10.5 * 0.90
        "vencimento": (datetime.now() + timedelta(days=540)).strftime("%Y-%m-%d"),
        "garantia": "FGC",
        "liquidez": "Carência 6 meses",
        "ir": "ISENTO",
        "isento_ir": True,
        "prazo_dias": 540,
        "score_bruto": 0.0
    },
    {
        "ticker": "LCA-92",
        "nome": "LCA 92% CDI",
        "tipo": "LCA",
        "taxa_bruta": 0.0966,  # 10.5 * 0.92
        "vencimento": (datetime.now() + timedelta(days=540)).strftime("%Y-%m-%d"),
        "garantia": "FGC",
        "liquidez": "Carência 6 meses",
        "ir": "ISENTO",
        "isento_ir": True,
        "prazo_dias": 540,
        "score_bruto": 0.0
    }
]

def get_fallback():
    """Retorna o fallback com uma cópia para evitar mutação externa"""
    import copy
    return copy.deepcopy(FALLBACK_RF)