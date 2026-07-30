"""
Testes do módulo de criptomoedas baseado na CoinGecko.

Os testes que acessam a API real são marcados como ``slow`` e ficam fora da
suíte determinística executada pelo CI.
"""

import sys
from collections.abc import Callable
from pathlib import Path

import pytest

# Permite executar este arquivo diretamente com:
# python tests/test_coingecko.py
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cripto.apis.coingecko import CoinGeckoClient
from cripto.screener_cripto import _score_cripto, top_cripto


@pytest.mark.slow
def test_coingecko_conexao() -> None:
    """Verifica se a CoinGecko devolve uma lista de mercados."""
    print("\n🔍 Testando conexão com CoinGecko...")

    client = CoinGeckoClient()
    markets = client.get_markets_top(top_n=5)

    assert markets, "Nenhum dado retornado da CoinGecko."

    print(f"✅ Conexão OK. {len(markets)} criptos retornadas.")
    print("   Primeiras 3:")
    for cripto in markets[:3]:
        print(
            f"   - {cripto['name']} ({cripto['symbol'].upper()}): "
            f"R$ {cripto['current_price']:.2f}"
        )


@pytest.mark.slow
def test_retorno_volatilidade() -> None:
    """Verifica retorno e volatilidade calculados para o Bitcoin."""
    print("\n📊 Testando retorno e volatilidade para Bitcoin...")

    client = CoinGeckoClient()
    retorno_volatilidade = client.get_retorno_e_volatilidade("bitcoin")

    assert "retorno_12m_pct" in retorno_volatilidade
    assert "volatilidade_anual" in retorno_volatilidade
    assert retorno_volatilidade["retorno_12m_pct"] is not None
    assert retorno_volatilidade["volatilidade_anual"] is not None

    print(
        "✅ Retorno 12m BTC: "
        f"{retorno_volatilidade['retorno_12m_pct']:.2f}%"
    )
    print(
        "✅ Volatilidade anual BTC: "
        f"{retorno_volatilidade['volatilidade_anual']:.2f}%"
    )


def test_score_cripto() -> None:
    """Verifica o score usando dados determinísticos."""
    print("\n🎯 Testando função de score...")

    indicadores = {
        "market_cap": 1_500_000_000_000,
        "volume": 30_000_000_000,
        "retorno_12m": 120.0,
        "volatilidade_anual": 65.0,
    }

    score, motivos = _score_cripto(indicadores, perfil=2)

    assert score > 0, "Score deveria ser positivo."
    assert motivos, "O cálculo deve explicar os motivos do score."

    print(f"Score moderado (BTC mock): {score}")
    print("Motivos:")
    for motivo in motivos:
        print(f"  - {motivo}")


@pytest.mark.slow
def test_top_cripto() -> None:
    """Verifica o ranking real para um perfil moderado."""
    print("\n🏆 Testando ranking de criptos (perfil moderado, top 3)...")

    resultado = top_cripto(perfil=2, n=3)

    assert len(resultado) == 3, (
        f"Esperado 3 criptos, obtido {len(resultado)}"
    )

    print("Top 3 criptos para perfil moderado:")
    for indice, item in enumerate(resultado, 1):
        print(
            f"  {indice}. {item['ticker']} - {item['nome']} "
            f"(Score: {item['score']:.1f})"
        )
        for motivo in item["motivos"][:2]:
            print(f"     {motivo}")


def _executar_teste_manual(
    nome: str,
    teste: Callable[[], None],
) -> tuple[str, bool]:
    """Executa um teste na interface manual e converte exceção em status."""
    try:
        teste()
    except Exception as exc:  # noqa: BLE001
        print(f"❌ {nome}: {exc}")
        return nome, False
    return nome, True


def main() -> None:
    """Executa todos os testes manualmente e imprime um resumo."""
    print("=" * 60)
    print("🧪 TESTE DO MÓDULO DE CRIPTOMOEDAS (CoinGecko)")
    print("=" * 60)

    resultados = [
        _executar_teste_manual("Conexão", test_coingecko_conexao),
        _executar_teste_manual(
            "Retorno/Volatilidade",
            test_retorno_volatilidade,
        ),
        _executar_teste_manual("Score", test_score_cripto),
        _executar_teste_manual("Ranking", test_top_cripto),
    ]

    print("\n" + "=" * 60)
    print("📊 RESUMO DOS TESTES")
    print("=" * 60)
    for nome, status in resultados:
        indicador = "✅" if status else "❌"
        resultado = "OK" if status else "FALHA"
        print(f"{indicador} {nome}: {resultado}")
    print("=" * 60)


if __name__ == "__main__":
    main()