# apis/data_merger.py (versão expandida)
from typing import Dict
from apis.brapi import BrapiClient
from apis.fundamentus_scraper import get_all_bulk, get_fundamentus_data

brapi = BrapiClient()

def merge_ticker_data(ticker: str) -> Dict:
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
            # ⬇️⬇️⬇️ NOVOS CAMPOS ⬇️⬇️⬇️
            'divida_patrimonio': dados.get('divida_patrimônio', 0),  # Dívida Líquida / PL
            'receita_cagr_5a': dados.get('receita_cagr_5a', 0),      # Crescimento da Receita (5a)
        })
    else:
        # Fallback: tenta detalhes
        detalhes = get_fundamentus_data(ticker)
        if detalhes:
            resultado['roe'] = float(detalhes.get('ROE', '0').replace('%', '').replace(',', '.'))
            resultado['dy'] = float(detalhes.get('Div. Yield', '0').replace('%', '').replace(',', '.'))
            resultado['pvp'] = float(detalhes.get('P/VP', '0').replace(',', '.'))
            resultado['pl'] = float(detalhes.get('P/L', '0').replace(',', '.'))
            resultado['cotacao'] = float(detalhes.get('Cotação', '0').replace(',', '.'))
            # Fallback para campos extras
            resultado['divida_patrimonio'] = float(detalhes.get('Dív Líq / Patrim', '0').replace(',', '.'))
            resultado['receita_cagr_5a'] = float(detalhes.get('Cres. Rec (5a)', '0').replace('%', '').replace(',', '.'))

    # 2. BRAPI – complementos
    try:
        quote = brapi.get_quote(ticker)
        resultado['market_cap'] = quote.get('marketCap', 0)
        resultado['preco'] = quote.get('regularMarketPrice', 0)
        if not resultado.get('pl'):
            resultado['pl'] = quote.get('priceEarnings', 0)
        div_summary = brapi.get_dividend_summary(ticker)
        resultado['dividendos_consistentes'] = div_summary.get('consistente', False)
    except:
        pass

    return resultado