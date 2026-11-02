"""Testes determinísticos para o módulo de ETFs."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import etfs.screener_etf as screener


@pytest.fixture(autouse=True)
def limpar_caches():
    """Impede que um teste dependa do cache preenchido por outro."""
    screener._CACHE_ETFS = None
    screener._CACHE_TIMESTAMP = 0.0

    with screener._CACHE_DADOS_LOCK:
        screener._CACHE_DADOS_ETF.clear()

    yield

    screener._CACHE_ETFS = None
    screener._CACHE_TIMESTAMP = 0.0

    with screener._CACHE_DADOS_LOCK:
        screener._CACHE_DADOS_ETF.clear()


class FakeTicker:
    """Substituto local do objeto yfinance.Ticker."""

    def __init__(
        self,
        taxa=None,
        tamanho_historico: int = 60,
    ):
        self.taxa = taxa
        self.tamanho_historico = tamanho_historico
        self.history_calls = 0
        self.info_calls = 0

    def history(self, **kwargs):
        self.history_calls += 1
        indice = pd.bdate_range(
            "2026-01-02",
            periods=self.tamanho_historico,
        )

        return pd.DataFrame(
            {
                "Close": np.linspace(
                    100.0,
                    112.0,
                    self.tamanho_historico,
                ),
                "Volume": np.full(
                    self.tamanho_historico,
                    1_000_000,
                ),
            },
            index=indice,
        )

    def get_info(self):
        self.info_calls += 1
        info = {"longName": "ETF de teste"}

        if self.taxa is not None:
            info["annualReportExpenseRatio"] = self.taxa

        return info


def dados_etf_ficticios(
    retorno: float,
    volatilidade: float,
    sharpe: float,
    taxa,
    volume: float,
) -> dict:
    return {
        "retorno_12m": retorno,
        "volatilidade": volatilidade,
        "sharpe": sharpe,
        "taxa": taxa,
        "volume": volume,
        "preco": 100.0,
        "nome": "ETF de teste",
    }


def test_get_all_etf_tickers_usa_brapi_e_cache(monkeypatch):
    chamadas = {"quantidade": 0}

    def fake_brapi():
        chamadas["quantidade"] += 1
        return ["BOVA11", "IVVB11", "BOVA11"]

    monkeypatch.setattr(
        screener,
        "_get_etfs_from_brapi",
        fake_brapi,
    )

    primeira = screener.get_all_etf_tickers()
    segunda = screener.get_all_etf_tickers()

    assert primeira == ["BOVA11", "IVVB11", "BOVA11"]
    assert segunda == primeira
    assert chamadas["quantidade"] == 1


def test_get_all_etf_tickers_rejeita_lista_vazia(monkeypatch):
    monkeypatch.setattr(
        screener,
        "_get_etfs_from_brapi",
        list,
    )

    with pytest.raises(Exception) as erro:
        screener.get_all_etf_tickers()

    assert "Lista de ETFs" in str(erro.value)


def test_get_etf_data_nao_descarta_taxa_ausente(monkeypatch):
    fake_ticker = FakeTicker(taxa=None)
    monkeypatch.setattr(
        screener.yf,
        "Ticker",
        lambda ticker: fake_ticker,
    )

    dados = screener.get_etf_data("BOVA11")

    assert dados
    assert dados["retorno_12m"] == pytest.approx(12.0)
    assert dados["volatilidade"] >= 0
    assert dados["sharpe"] is not None
    assert dados["volume"] > 0
    assert dados["taxa"] is None
    assert dados["preco"] == pytest.approx(112.0)
    assert dados["nome"] == "ETF de teste"


def test_get_etf_data_converte_taxa_decimal_para_percentual(
    monkeypatch,
):
    fake_ticker = FakeTicker(taxa=0.0025)
    monkeypatch.setattr(
        screener.yf,
        "Ticker",
        lambda ticker: fake_ticker,
    )

    dados = screener.get_etf_data("BOVA11.SA")

    assert dados["taxa"] == pytest.approx(0.25)


def test_get_etf_data_usa_cache(monkeypatch):
    fake_ticker = FakeTicker(taxa=None)
    monkeypatch.setattr(
        screener.yf,
        "Ticker",
        lambda ticker: fake_ticker,
    )

    primeira = screener.get_etf_data("BOVA11")
    segunda = screener.get_etf_data("BOVA11")

    assert primeira == segunda
    assert primeira is not segunda
    assert fake_ticker.history_calls == 1
    assert fake_ticker.info_calls == 1


def test_get_etf_data_rejeita_historico_insuficiente(monkeypatch):
    fake_ticker = FakeTicker(
        taxa=0.0025,
        tamanho_historico=10,
    )
    monkeypatch.setattr(
        screener.yf,
        "Ticker",
        lambda ticker: fake_ticker,
    )

    assert screener.get_etf_data("BOVA11") == {}


def test_score_ignora_taxa_ausente_sem_inventar_valor():
    sem_taxa = dados_etf_ficticios(
        retorno=20.0,
        volatilidade=15.0,
        sharpe=1.0,
        taxa=None,
        volume=20_000_000,
    )

    score, motivos = screener._score_etf(
        sem_taxa,
        perfil=2,
    )

    assert 0 <= score <= 100
    assert any(
        "não usado no score" in motivo
        for motivo in motivos
    )


def test_menor_volatilidade_vence_em_todos_os_perfis():
    defensivo = dados_etf_ficticios(
        retorno=8.0,
        volatilidade=8.0,
        sharpe=0.8,
        taxa=0.15,
        volume=20_000_000,
    )
    agressivo = dados_etf_ficticios(
        retorno=35.0,
        volatilidade=35.0,
        sharpe=1.4,
        taxa=0.80,
        volume=60_000_000,
    )

    score_defensivo_p1, _ = screener._score_etf(
        defensivo,
        perfil=1,
    )
    score_agressivo_p1, _ = screener._score_etf(
        agressivo,
        perfil=1,
    )
    score_defensivo_p3, _ = screener._score_etf(
        defensivo,
        perfil=3,
    )
    score_agressivo_p3, _ = screener._score_etf(
        agressivo,
        perfil=3,
    )

    # Validação histórica: menor volatilidade venceu em todos os perfis.
    assert score_defensivo_p1 > score_agressivo_p1
    assert score_defensivo_p3 > score_agressivo_p3


def test_retorno_passado_nao_muda_o_score():
    """Momentum de 12 meses não previu retorno futuro; é só informativo."""
    base = dados_etf_ficticios(retorno=5.0, volatilidade=15.0, sharpe=0.2, taxa=0.3, volume=10_000_000)
    subiu = dict(base, retorno_12m=60.0, sharpe=2.5)
    assert screener._score_etf(base, perfil=2)[0] == screener._score_etf(subiu, perfil=2)[0]


@pytest.fixture
def ranking_mock(monkeypatch):
    tickers = [
        "ETF1",
        "ETF2",
        "ETF3",
        "ETF4",
        "ETF5",
        "ETF6",
    ]

    monkeypatch.setattr(
        screener,
        "get_all_etf_tickers",
        lambda: list(tickers),
    )

    def fake_get_etf_data(ticker):
        indice = int(ticker[-1])
        return dados_etf_ficticios(
            retorno=5.0 * indice,
            volatilidade=7.0 * indice,
            sharpe=0.2 * indice,
            taxa=None if indice % 2 else 0.1 * indice,
            volume=5_000_000 * indice,
        )

    monkeypatch.setattr(
        screener,
        "get_etf_data",
        fake_get_etf_data,
    )

    return tickers


@pytest.mark.parametrize("perfil", [1, 2, 3])
def test_top_etfs_retorna_quantidade_e_contrato(
    ranking_mock,
    perfil,
):
    resultados = screener.top_etfs(perfil, n=3)

    assert len(resultados) == 3

    for item in resultados:
        assert item["ticker"] in ranking_mock
        assert 0 <= item["score"] <= 100
        assert isinstance(item["motivos"], list)
        assert item["retorno_12m"] is not None
        assert item["volatilidade"] is not None
        assert "taxa" in item


def test_top_etfs_respeita_n_zero(ranking_mock):
    assert screener.top_etfs(2, n=0) == []

@pytest.mark.parametrize(
    ("nome", "classe"),
    [
        ("INVESTO TEVA TESOURO SELIC ETF CLASSE DE ÍNDICE", "renda_fixa"),
        ("INVESTO ETF MARKETVECTOR BRAZIL TREASURY 760 DAY", "renda_fixa"),
        ("IT NOW IMA-B5 P2 FUNDO DE ÍNDICE", "renda_fixa"),
        ("BB ETF ÍNDICE FUTURO DE BOI GORDO B3", "commodity"),
        ("HASHDEX NASDAQ BITCOIN REFERENCE PRICE FUNDO DE ÍNDICE", "cripto"),
        ("ISHARES BOVA FUNDO DE ÍNDICE", "acoes"),
        ("Fundo de Investimento Amazônia - FINAM", "outro"),
        ("PORTO SUDESTE V.M. S.A.", "outro"),
        ("FUNDES", "outro"),
        ("BTG PACTUAL TEVA AÇÕES COMMODITIES BRASIL FUNDO DE ÍNDICE", "acoes"),
        ("Btg Pactual Teva Itbr Ipca 95-5 Fundo De Indice", "renda_fixa"),
        ("BB ETF ÍNDICE DAP5 B3 FUNDO DE ÍNDICE", "renda_fixa"),
        (None, "acoes"),
    ],
)
def test_classe_etf(nome, classe):
    from etfs.screener_etf import classe_etf

    assert classe_etf(nome) == classe


@pytest.mark.parametrize(
    ("volatilidade", "classe"),
    [(0.6, "renda_fixa"), (5.5, "renda_fixa"), (16.0, "acoes"), (None, "acoes")],
)
def test_classe_etf_usa_volatilidade_quando_nome_e_generico(volatilidade, classe):
    from etfs.screener_etf import classe_etf

    assert classe_etf("BL03 FUNDO DE ÍNDICE", volatilidade) == classe


def test_top_etfs_de_acoes_ignora_renda_fixa_e_ativos_sem_preco(monkeypatch):
    universo = {
        "BOVA11": {"nome": "ISHARES IBOVESPA FUNDO DE ÍNDICE", "volatilidade": 18.0},
        "LFTS11": {"nome": "TESOURO SELIC ETF", "volatilidade": 0.5},
        "XXXX11": {"nome": "BL03 Fundo Invest Financeiro", "volatilidade": 2.0},
        "FNAM11": {"nome": "Fundo de Investimento Amazônia", "volatilidade": 30.0, "preco": 0.0},
    }
    monkeypatch.setattr(screener, "get_all_etf_tickers", lambda: list(universo))

    def fake_get_etf_data(ticker):
        dados = dados_etf_ficticios(10.0, 15.0, 0.5, None, 1_000_000)
        dados.update(universo[ticker])
        return dados

    monkeypatch.setattr(screener, "get_etf_data", fake_get_etf_data)

    resultado = screener.top_etfs(2, n=5)

    assert [item["ticker"] for item in resultado] == ["BOVA11"]
    assert resultado[0]["classe"] == "acoes"


def test_fundos_regionais_nao_sao_etf():
    from etfs.screener_etf import classe_etf

    assert classe_etf("FNOR11", 30.0, "FNOR11") == "outro"
    assert classe_etf("BOVA11", 20.0, "BOVA11") == "acoes"  # nome desconhecido
