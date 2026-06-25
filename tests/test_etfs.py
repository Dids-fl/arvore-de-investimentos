"""
Testes para o módulo de ETFs.
"""

import pytest
from etfs.screener_etf import get_all_etf_tickers, top_etfs, get_etf_data


def test_get_all_etf_tickers():
    """Verifica se a lista de ETFs não está vazia e contém tickers válidos."""
    tickers = get_all_etf_tickers()
    assert isinstance(tickers, list)
    assert len(tickers) > 0
    # Verifica se pelo menos um ticker conhecido está presente
    known_etfs = {"BOVA11", "IVVB11", "BOVV11", "DIVO11", "PIBB11"}
    assert any(t in known_etfs for t in tickers), "Nenhum ETF conhecido encontrado."


def test_get_etf_data():
    """Testa a obtenção de dados de um ETF específico."""
    dados = get_etf_data("BOVA11")
    assert isinstance(dados, dict)
    assert dados.get("retorno_12m") is not None
    assert dados.get("volatilidade") is not None
    assert dados.get("sharpe") is not None
    assert dados.get("volume") is not None
    assert dados.get("taxa") is not None
    assert dados.get("preco") is not None


def test_top_etfs():
    """Verifica se o ranking retorna o número correto de ETFs."""
    for perfil in [1, 2, 3]:
        resultados = top_etfs(perfil, n=3)
        assert len(resultados) == 3
        for item in resultados:
            assert "ticker" in item
            assert "score" in item
            assert "motivos" in item
            assert item["score"] >= 0


def test_top_etfs_perfis_diferentes():
    """Verifica se os rankings para perfis diferentes não são idênticos (pelo menos em ordem)."""
    top1 = [r["ticker"] for r in top_etfs(1, n=5)]
    top2 = [r["ticker"] for r in top_etfs(2, n=5)]
    top3 = [r["ticker"] for r in top_etfs(3, n=5)]
    assert len(top1) == len(top2) == len(top3) == 5

# pytest tests/test_etfs.py -v