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
