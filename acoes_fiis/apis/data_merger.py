"""
Data Merger – consolida dados do Fundamentus (scraping) + BRAPI (complementos).
Fundamentus é a fonte primária; BRAPI complementa com market cap, preço, etc.
"""

from .fundamentus_scraper import get_all_bulk, get_fundamentus_data
from .brapi import BrapiClient
from typing import Dict

brapi = BrapiClient()

# Cache do bulk para evitar N scrapings (1 por ticker chamado)
# get_all_bulk() faz UMA requisição HTTP — cachear é essencial
_bulk_cache: Dict | None = None

def _get_bulk_cached() -> Dict:
    """Retorna o bulk do Fundamentus, fazendo scraping apenas uma vez por processo."""
    global _bulk_cache
    if _bulk_cache is None:
        _bulk_cache = get_all_bulk()
    return _bulk_cache

def merge_ticker_data(ticker: str) -> Dict:
    """
    Retorna dados consolidados: Fundamentus (primário) + BRAPI (complementos).
    Usa cache do bulk para evitar 1 scraping por ticker.
    """
    ticker = ticker.upper()
    resultado = {}

    # ── 1. Fundamentus (bulk) – fonte primária ──────────────────────────────
    bulk = _get_bulk_cached()
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

    # ── 2. BRAPI – complementos ──────────────────────────────────────────────
    try:
        quote = brapi.get_quote(ticker)
        if quote:
            # Market cap
            mcap = quote.get('marketCap', 0)
            if mcap > 0:
                resultado['market_cap'] = mcap
            # Preço (se Fundamentus não tiver ou for zero)
            preco = quote.get('regularMarketPrice', 0)
            if preco > 0 and (not resultado.get('cotacao') or resultado.get('cotacao') == 0):
                resultado['cotacao'] = preco
            # P/L (se Fundamentus não tiver)
            pl_brapi = quote.get('priceEarnings', 0)
            if pl_brapi > 0 and (not resultado.get('pl') or resultado.get('pl') == 0):
                resultado['pl'] = pl_brapi
            # P/VP (se Fundamentus não tiver)
            pvp_brapi = quote.get('priceToBook', 0)
            if pvp_brapi > 0 and (not resultado.get('pvp') or resultado.get('pvp') == 0):
                resultado['pvp'] = pvp_brapi

        # Consistência de dividendos (BRAPI)
        div_summary = brapi.get_dividend_summary(ticker)
        resultado['dividendos_consistentes'] = div_summary.get('consistente', False)

    except Exception:
        pass

    return resultado