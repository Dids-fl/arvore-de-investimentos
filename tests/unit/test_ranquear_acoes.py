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


def test_agressivo_prefere_acoes_baratas_a_roe_alto() -> None:
    # Regra validada: no agressivo, P/L e P/VP baixos pesam mais que ROE alto.
    universo = [
        _acao("CARA3", dy=1.0, pl=40.0, roe=45.0, pvp=6.0),
        _acao("BARA3", dy=1.0, pl=5.0, roe=12.0, pvp=0.7),
        _acao("MEIO3", dy=1.0, pl=15.0, roe=20.0, pvp=2.0),
    ]
    ranking = screener.ranquear_acoes(universo, perfil=3, n=3)
    assert ranking[0]["ticker"] == "BARA3"
    assert ranking[-1]["ticker"] == "CARA3"


def test_agressivo_mantem_filtro_de_roe_minimo() -> None:
    universo = [
        _acao("BAIX3", pl=3.0, roe=4.0, pvp=0.5),
        _acao("BOAA3", pl=8.0, roe=15.0, pvp=1.0),
        _acao("OUTA3", pl=9.0, roe=18.0, pvp=1.1),
    ]
    tickers = [a["ticker"] for a in screener.ranquear_acoes(universo, perfil=3, n=3)]
    assert "BAIX3" not in tickers
