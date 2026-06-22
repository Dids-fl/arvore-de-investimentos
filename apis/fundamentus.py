"""
Fundamentus.com.br – scraping de indicadores fundamentalistas.
Não oficial, use com moderação.
"""

import requests
from bs4 import BeautifulSoup
import re
from typing import List, Dict, Optional
from utils.logging_config import get_logger

logger = get_logger(__name__)

BASE_URL = "https://www.fundamentus.com.br/"

def get_stock_data(ticker: str) -> Optional[Dict]:
    """
    Retorna indicadores fundamentalistas de uma ação do Fundamentus.
    Exemplo: get_stock_data("PETR4")
    """
    try:
        url = f"{BASE_URL}resultado.php?papel={ticker.upper()}"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')
        table = soup.find('table', {'class': 'data'})
        if not table:
            logger.warning(f"Tabela não encontrada para {ticker}")
            return None
        rows = table.find_all('tr')
        data = {}
        for row in rows:
            cols = row.find_all('td')
            if len(cols) >= 2:
                key = cols[0].text.strip()
                value = cols[1].text.strip()
                # Limpa e converte
                if '%' in value:
                    value = value.replace('%', '').replace(',', '.').strip()
                    data[key] = float(value)
                elif '.' in value and ',' in value:
                    # Números com milhares e decimais (ex: 1.234,56)
                    value = value.replace('.', '').replace(',', '.')
                    data[key] = float(value)
                else:
                    data[key] = value
        # Mapear para campos padronizados
        result = {
            "ticker": ticker.upper(),
            "nome": data.get("Empresa", ""),
            "cotacao": float(data.get("Preço", "0").replace(',', '.')),
            "pl": float(data.get("P/L", "0")),
            "pvp": float(data.get("P/VP", "0")),
            "dy": float(data.get("Div.Yield", "0")),
            "roe": float(data.get("ROE", "0")),
            "margem_liquida": float(data.get("Marg. Líquida", "0")),
            "receita_cagr_5a": float(data.get("Cresc. Rec. 5a", "0")),
            "setor": data.get("Setor", ""),
        }
        return result
    except Exception as e:
        logger.error(f"Erro ao buscar {ticker} no Fundamentus: {e}")
        return None

def search_stocks(limit: int = 100) -> List[Dict]:
    """
    Busca lista de ações do Fundamentus (página de resultados).
    """
    try:
        url = f"{BASE_URL}resultado.php"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')
        table = soup.find('table', {'id': 'resultado'})
        if not table:
            return []
        rows = table.find_all('tr')[1:]  # pular cabeçalho
        stocks = []
        for row in rows:
            cols = row.find_all('td')
            if len(cols) >= 10:
                ticker = cols[0].text.strip()
                if ticker.endswith('F') or ticker.endswith('11'):  # FIIs, não ações
                    continue
                try:
                    dy = float(cols[5].text.replace(',', '.').replace('%', ''))
                    pl = float(cols[2].text.replace(',', '.'))
                    pvp = float(cols[3].text.replace(',', '.'))
                    roe = float(cols[7].text.replace(',', '.').replace('%', ''))
                    liq = float(cols[9].text.replace(',', '.').replace('.', ''))
                    stocks.append({
                        "ticker": ticker,
                        "nome": cols[1].text.strip(),
                        "cotacao": float(cols[0].text.replace(',', '.')),
                        "dy": dy,
                        "pl": pl,
                        "pvp": pvp,
                        "roe": roe,
                        "liquidez": liq,
                    })
                except:
                    continue
                if len(stocks) >= limit:
                    break
        return stocks
    except Exception as e:
        logger.error(f"Erro ao buscar lista do Fundamentus: {e}")
        return []