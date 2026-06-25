"""
Teste para o módulo de criptomoedas (CoinGecko).
Verifica se a API está respondendo e se os dados são coerentes.
"""

import sys
from pathlib import Path

# Adiciona a raiz ao path para importar os módulos
sys.path.insert(0, str(Path(__file__).parent.parent))

from cripto.screener_cripto import top_cripto, _score_cripto
from cripto.apis.coingecko import CoinGeckoClient


def test_coingecko_conexao():
    """Testa se a CoinGecko está respondendo."""
    print("\n🔍 Testando conexão com CoinGecko...")
    try:
        client = CoinGeckoClient()
        # Tenta buscar o top 5 para ver se a API responde
        markets = client.get_markets_top(top_n=5)
        assert len(markets) > 0, "Nenhum dado retornado da CoinGecko."
        print(f"✅ Conexão OK. {len(markets)} criptos retornadas.")
        print("   Primeiras 3:")
        for c in markets[:3]:
            print(f"   - {c['name']} ({c['symbol'].upper()}): R$ {c['current_price']:.2f}")
        return True
    except Exception as e:
        print(f"❌ Falha na conexão: {e}")
        return False


def test_retorno_volatilidade():
    """Testa o cálculo de retorno e volatilidade para uma cripto conhecida."""
    print("\n📊 Testando retorno e volatilidade para Bitcoin...")
    try:
        client = CoinGeckoClient()
        rv = client.get_retorno_e_volatilidade("bitcoin")
        assert "retorno_12m_pct" in rv
        assert "volatilidade_anual" in rv
        print(f"✅ Retorno 12m BTC: {rv['retorno_12m_pct']:.2f}%")
        print(f"✅ Volatilidade anual BTC: {rv['volatilidade_anual']:.2f}%")
        return True
    except Exception as e:
        print(f"❌ Falha: {e}")
        return False


def test_score_cripto():
    """Testa o score para uma cripto com dados mockados."""
    print("\n🎯 Testando função de score...")
    # Dados simulados (baseados em Bitcoin)
    ind = {
        "market_cap": 1_500_000_000_000,
        "volume": 30_000_000_000,
        "retorno_12m": 120.0,
        "volatilidade_anual": 65.0,
    }
    perfil = 2  # moderado
    score, motivos = _score_cripto(ind, perfil)
    print(f"Score moderado (BTC mock): {score}")
    print("Motivos:")
    for m in motivos:
        print(f"  - {m}")
    assert score > 0, "Score deveria ser positivo."
    return True


def test_top_cripto():
    """Testa o ranking de criptos para um perfil."""
    print("\n🏆 Testando ranking de criptos (perfil moderado, top 3)...")
    try:
        resultado = top_cripto(perfil=2, n=3)
        assert len(resultado) == 3, f"Esperado 3 criptos, obtido {len(resultado)}"
        print("Top 3 criptos para perfil moderado:")
        for i, item in enumerate(resultado, 1):
            print(f"  {i}. {item['ticker']} - {item['nome']} (Score: {item['score']:.1f})")
            for motivo in item['motivos'][:2]:
                print(f"     {motivo}")
        return True
    except Exception as e:
        print(f"❌ Falha: {e}")
        return False


def main():
    print("=" * 60)
    print("🧪 TESTE DO MÓDULO DE CRIPTOMOEDAS (CoinGecko)")
    print("=" * 60)

    resultados = []
    resultados.append(("Conexão", test_coingecko_conexao()))
    resultados.append(("Retorno/Volatilidade", test_retorno_volatilidade()))
    resultados.append(("Score", test_score_cripto()))
    resultados.append(("Ranking", test_top_cripto()))

    print("\n" + "=" * 60)
    print("📊 RESUMO DOS TESTES")
    print("=" * 60)
    for nome, status in resultados:
        print(f"{'✅' if status else '❌'} {nome}: {'OK' if status else 'FALHA'}")
    print("=" * 60)


if __name__ == "__main__":
    main()