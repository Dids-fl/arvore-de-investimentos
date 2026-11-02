"""A regra de ranking de ações usada pelo app e pela validação histórica."""

from __future__ import annotations

from acoes_fiis import screener


def _acao(ticker, dy=5.0, pl=8.0, roe=15.0, pvp=1.2, liquidez=50e6, mktcap=20e9):
    return {
        "ticker": ticker, "dy": dy, "pl": pl, "roe": roe, "pvp": pvp,
        "liquidez": liquidez, "mktcap_proxy": mktcap, "setor": "",
    }


def test_deduplica_classes_da_mesma_empresa() -> None:
    universo = [_acao("ABCD3"), _acao("ABCD4", dy=6.0), _acao("EFGH3"), _acao("IJKL3")]
    tickers = [a["ticker"] for a in screener.ranquear_acoes(universo, perfil=2, n=10)]
    assert sum(t.startswith("ABCD") for t in tickers) == 1


def test_respeita_n_e_ordem_por_score() -> None:
    universo = [_acao(f"AA{chr(65 + i)}A3", dy=3 + i, pl=10 - i * 0.5) for i in range(8)]
    ranking = screener.ranquear_acoes(universo, perfil=1, n=3)
    assert len(ranking) == 3
    assert [a["score"] for a in ranking] == sorted((a["score"] for a in ranking), reverse=True)


def test_ignora_acao_sem_nenhum_indicador() -> None:
    universo = [_acao("ZERO3", dy=0, pl=0, roe=0), _acao("BOAS3"), _acao("OUTR3")]
    tickers = [a["ticker"] for a in screener.ranquear_acoes(universo, perfil=2, n=10)]
    assert "ZERO3" not in tickers
