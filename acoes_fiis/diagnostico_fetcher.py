"""
Script de diagnóstico para testar a coleta híbrida (Fundamentus + BRAPI).
Mostra: dados brutos do Fundamentus, complementos da BRAPI e a fusão final.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from acoes_fiis.apis.fundamentus_scraper import get_all_bulk, get_fundamentus_data
from acoes_fiis.apis.brapi import BrapiClient
from acoes_fiis.apis.data_merger import merge_ticker_data


def testar_fundamentus(ticker: str):
    print(f"\n📡 Fundamentus (bulk) para {ticker}:")
    bulk = get_all_bulk()
    if ticker in bulk:
        dados = bulk[ticker]
        print("✅ Encontrado no bulk:")
        for k, v in dados.items():
            print(f"   {k}: {v}")
    else:
        detalhes = get_fundamentus_data(ticker)
        if detalhes:
            print("✅ Detalhes encontrados:")
            for k, v in detalhes.items():
                print(f"   {k}: {v}")
        else:
            print("❌ Nenhum dado do Fundamentus.")


def testar_brapi(ticker: str):
    print(f"\n📡 BRAPI para {ticker}:")
    try:
        client = BrapiClient()
        quote = client.get_quote(ticker)
        if quote:
            print("✅ Quote obtido:")
            print(f"   Preço: {quote.get('regularMarketPrice')}")
            print(f"   Market Cap: {quote.get('marketCap')}")
            print(f"   P/L: {quote.get('priceEarnings')}")
            print(f"   P/VP: {quote.get('priceToBook')}")
            print(f"   EPS: {quote.get('earningsPerShare')}")
        else:
            print("❌ Quote não obtido")
        # Dividendos
        div_summary = client.get_dividend_summary(ticker)
        print(f"   Dividendos consistentes (5 anos): {div_summary.get('consistente', False)}")
    except Exception as e:
        print(f"❌ Erro: {e}")


def testar_merger(ticker: str):
    print(f"\n📡 Fusão (Fundamentus + BRAPI) para {ticker}:")
    dados = merge_ticker_data(ticker)
    if dados:
        print("✅ Dados consolidados:")
        for k, v in dados.items():
            print(f"   {k}: {v}")
    else:
        print("❌ Nenhum dado retornado.")


def main():
    ticker = sys.argv[1].upper() if len(sys.argv) > 1 else "VALE3"
    print("=" * 60)
    print(f"🔍 DIAGNÓSTICO COMPLETO PARA {ticker}")
    print("=" * 60)

    testar_fundamentus(ticker)
    testar_brapi(ticker)
    testar_merger(ticker)

    print("\n✅ Diagnóstico concluído.")


if __name__ == "__main__":
    main()

# python -m acoes_fiis.diagnostico_fetcher VALE3