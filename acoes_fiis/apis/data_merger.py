"""
Data Merger – consolida dados do Fundamentus (scraping) + Yahoo Finance (complementos).
Remove a dependência da BRAPI para dados complementares.
"""

import yfinance as yf
from typing import Dict
from .fundamentus_scraper import get_all_bulk, get_fundamentus_data
from utils.logging_config import get_logger

logger = get_logger(__name__)

def _get_dividend_consistency_yf(ticker: str) -> bool:
    """
    Verifica se o ticker pagou dividendos nos últimos 5 anos (4 anos distintos).
    Usa Yahoo Finance.
    """
    try:
        ticker_yf = ticker if ticker.endswith(".SA") else ticker + ".SA"
        tk = yf.Ticker(ticker_yf)
        divs = tk.dividends
        if divs.empty:
            return False
        # Pega os últimos 5 anos a partir de hoje
        from datetime import datetime
        ano_atual = datetime.now().year
        anos = set(divs.index.year)
        anos_5 = set(range(ano_atual - 5, ano_atual + 1))
        anos_com_div = len(anos.intersection(anos_5))
        return anos_com_div >= 4
    except Exception as e:
        logger.debug(f"Erro ao verificar dividendos de {ticker} via yfinance: {e}")
        return False

def _get_yfinance_complement(ticker: str) -> Dict:
    """
    Busca dados complementares (preço, market cap, P/L, P/VP) via Yahoo Finance.
    """
    try:
        ticker_yf = ticker if ticker.endswith(".SA") else ticker + ".SA"
        tk = yf.Ticker(ticker_yf)
        info = tk.info
        return {
            "market_cap": info.get("marketCap"),
            "preco": info.get("regularMarketPrice"),
            "pl": info.get("priceEarnings"),
            "pvp": info.get("priceToBook"),
            "dividendos_consistentes": _get_dividend_consistency_yf(ticker),
        }
    except Exception as e:
        logger.debug(f"YFinance falhou para {ticker}: {e}")
        return {}

def merge_ticker_data(ticker: str) -> Dict:
    """
    Retorna dados consolidados de um ticker:
      - Fundamentus (primário)
      - Yahoo Finance (complementos: market cap, preço, P/L, P/VP, dividendos)
    """
    ticker = ticker.upper()
    resultado = {}

    # 1. Fundamentus (bulk) – fonte primária
    bulk = get_all_bulk()
    if ticker in bulk:
        dados = bulk[ticker]
        resultado.update({
            'roe': dados.get('roe', 0),
            'dy': dados.get('dy', 0),
            'pvp': dados.get('pvp', 0),
            'pl': dados.get('pl', 0),
            'cotacao': dados.get('cotacao', 0),
            'liquidez': dados.get('liquidez', 0),
            'divida_patrimonio': dados.get('divida_patrimônio', 0),
            'receita_cagr_5a': dados.get('receita_cagr_5a', 0),
            'patrimonio': dados.get('patrimônio', 0),
        })
    else:
        # Fallback: busca detalhes individuais (detalhes.php)
        detalhes = get_fundamentus_data(ticker)
        if detalhes:
            try:
                resultado['roe'] = float(str(detalhes.get('ROE', '0')).replace('%', '').replace(',', '.'))
                resultado['dy'] = float(str(detalhes.get('Div. Yield', '0')).replace('%', '').replace(',', '.'))
                resultado['pvp'] = float(str(detalhes.get('P/VP', '0')).replace(',', '.'))
                resultado['pl'] = float(str(detalhes.get('P/L', '0')).replace(',', '.'))
                resultado['cotacao'] = float(str(detalhes.get('Cotação', '0')).replace(',', '.'))
                resultado['divida_patrimonio'] = float(str(detalhes.get('Dív Líq / Patrim', '0')).replace(',', '.'))
                resultado['receita_cagr_5a'] = float(str(detalhes.get('Cres. Rec (5a)', '0')).replace('%', '').replace(',', '.'))
                resultado['patrimonio'] = float(str(detalhes.get('Patrim. Líq', '0')).replace(',', '.'))
            except Exception:
                pass

    # 2. Yahoo Finance – complementos (substitui BRAPI)
    yf_data = _get_yfinance_complement(ticker)
    if yf_data:
        # Atualiza apenas se o campo não existir ou for zero
        if yf_data.get('market_cap') and not resultado.get('market_cap'):
            resultado['market_cap'] = yf_data['market_cap']
        if yf_data.get('preco') and (not resultado.get('cotacao') or resultado.get('cotacao') == 0):
            resultado['cotacao'] = yf_data['preco']
        if yf_data.get('pl') and (not resultado.get('pl') or resultado.get('pl') == 0):
            resultado['pl'] = yf_data['pl']
        if yf_data.get('pvp') and (not resultado.get('pvp') or resultado.get('pvp') == 0):
            resultado['pvp'] = yf_data['pvp']
        # Dividendos consistentes
        resultado['dividendos_consistentes'] = yf_data.get('dividendos_consistentes', False)

    return resultado