"""O backtest histórico não pode usar informação posterior à data-base."""

from __future__ import annotations

import pandas as pd
import pytest

vh = pytest.importorskip("backtest.validacao_historica")


@pytest.fixture
def series_falsas(monkeypatch):
    dias = pd.date_range("2000-01-01", "2026-12-31", freq="D")
    monkeypatch.setattr(vh, "serie_selic_meta", lambda: pd.Series(10.0, index=dias))
    meses = pd.date_range("2000-01-01", "2026-12-01", freq="MS")
    ipca12 = pd.Series(range(len(meses)), index=meses, dtype=float)
    monkeypatch.setattr(vh, "serie_ipca_12m", lambda: ipca12)
    monkeypatch.setattr(vh, "serie_yahoo", lambda t: pd.Series(1.0, index=dias).cumsum())
    focus = pd.DataFrame(
        {
            "Data": pd.to_datetime(["2020-01-02", "2020-03-10", "2020-03-20"]),
            "DataReferencia": [2020, 2020, 2020],
            "Mediana": [4.0, 5.0, 9.0],
        }
    )
    monkeypatch.setattr(vh, "focus_anual", lambda indicador: focus)
    return ipca12


def test_mercado_em_nao_olha_o_futuro(series_falsas) -> None:
    dia = pd.Timestamp("2020-03-15")
    mercado = vh.mercado_em(dia)

    # Focus: última mediana publicada até o dia (5%), não a de 20/03 (9%)
    assert mercado["focus_selic_por_ano"] == {2020: 0.05}
    assert mercado["selic"] == 0.10
    # IPCA 12m: o IBGE divulga cada mês por volta do dia 10 do mês seguinte.
    # Em 15/03 fevereiro já saiu; em 05/03 ainda não, então vale janeiro.
    assert mercado["ipca"] == series_falsas.loc["2020-02-01"] / 100
    antes = vh.mercado_em(pd.Timestamp("2020-03-05"))
    assert antes["ipca"] == series_falsas.loc["2020-01-01"] / 100


def test_anualizar() -> None:
    assert vh._anualizar(1.21, 2) == pytest.approx(0.10)


def test_serie_com_desdobramento_nao_ajustado_e_descartada() -> None:
    dias = pd.bdate_range("2024-01-01", "2024-12-31")
    normal = pd.Series(100.0, index=dias) * (1.001 ** pd.Series(range(len(dias)), index=dias))
    com_salto = normal.copy()
    com_salto.loc["2024-06-03":] *= 10  # desdobramento 1:10 não ajustado
    inicio, fim = pd.Timestamp("2024-02-01"), pd.Timestamp("2024-11-29")

    assert vh._serie_confiavel(normal, inicio, fim)
    assert not vh._serie_confiavel(com_salto, inicio, fim)


def test_balanco_so_conta_depois_de_publicado() -> None:
    # A DFP do ano anterior sai até o fim de março.
    assert vh._ano_balanco_disponivel(pd.Timestamp("2020-03-31")) == 2018
    assert vh._ano_balanco_disponivel(pd.Timestamp("2020-04-01")) == 2019
    assert vh._ano_balanco_disponivel(pd.Timestamp("2020-12-31")) == 2019


def _proxies(meses: int = 36) -> pd.DataFrame:
    datas = pd.date_range("2010-01-31", periods=meses, freq="ME")
    passos = pd.Series(range(meses), index=datas, dtype=float)
    return pd.DataFrame(
        {
            "cdi": 1.01**passos,
            "ipca_mais": 1.01**passos,
            # bolsa: sobe 5% e cai 5% alternadamente
            "ibov": (passos.map(lambda i: 1.05 if i % 2 else 1 / 1.05)).cumprod(),
            "fii": pd.Series(float("nan"), index=datas),
        }
    )


def test_carteira_so_cdi_nunca_perde_dinheiro() -> None:
    r = vh.simular_carteira({"rf": 100}, _proxies())
    assert r["retorno_anual"] == pytest.approx(1.01**12 - 1)
    assert r["pior_queda"] == pytest.approx(0)
    assert r["perdeu_dinheiro_12m"] == 0


def test_carteira_com_bolsa_tem_queda_e_serie_ausente_usa_substituto() -> None:
    so_cdi = vh.simular_carteira({"rf": 100}, _proxies())
    bolsa = vh.simular_carteira({"rf": 50, "rv": 50}, _proxies())
    assert bolsa["pior_queda"] < so_cdi["pior_queda"]
    # FII sem dados no período: usa 50% IPCA+ e 50% Ibovespa, sem quebrar
    fii = vh.simular_carteira({"fiis": 100}, _proxies())
    assert fii["pior_queda"] < 0
    assert fii["retorno_anual"] == fii["retorno_anual"]  # não é NaN
