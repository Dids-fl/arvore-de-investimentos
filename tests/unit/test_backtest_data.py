"""Casos de borda dos carregadores e benchmarks do backtest."""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pandas as pd
import pytest

from backtest.benchmarks import (
    benchmark_cdi,
    montar_benchmarks,
    retorno_carteira_fixa,
)
from backtest.data_loader import (
    _tickers_validos,
    calcular_retornos,
    carregar_csv,
    carregar_yfinance,
    janela_disponivel,
    validar_precos,
)


@pytest.fixture
def precos_basicos() -> pd.DataFrame:
    datas = pd.bdate_range("2024-01-02", periods=4)
    return pd.DataFrame(
        {
            "AAA": [100.0, 101.0, 102.0, 103.0],
            "BBB": [50.0, 49.0, 50.0, 51.0],
        },
        index=datas,
    )


def test_tickers_validos_normaliza_e_remove_duplicados() -> None:
    assert _tickers_validos([" petr4 ", "PETR4", "vale3"]) == [
        "PETR4",
        "VALE3",
    ]


@pytest.mark.parametrize(
    "tickers",
    [
        [],
        [""],
        ["   "],
        [None],
    ],
)
def test_tickers_validos_rejeita_entradas_invalidas(tickers) -> None:
    with pytest.raises(ValueError):
        _tickers_validos(tickers)


def test_validar_precos_normaliza_datas_colunas_e_valores() -> None:
    precos = pd.DataFrame(
        {
            " aaa ": [110, 999, 100, 120],
            "SEM_PRECO": [0, 0, 0, 0],
        },
        index=[
            "2024-01-02",
            "data-invalida",
            "2024-01-01",
            "2024-01-02",
        ],
    )

    resultado = validar_precos(precos)

    assert list(resultado.columns) == ["AAA"]
    assert resultado.index.tolist() == [
        pd.Timestamp("2024-01-01"),
        pd.Timestamp("2024-01-02"),
    ]
    assert resultado.loc["2024-01-02", "AAA"] == pytest.approx(120.0)


def test_validar_precos_remove_timezone() -> None:
    indice = pd.date_range("2024-01-01", periods=2, tz="UTC")
    resultado = validar_precos(pd.DataFrame({"AAA": [1, 2]}, index=indice))
    assert resultado.index.tz is None


@pytest.mark.parametrize(
    ("precos", "minimo", "erro"),
    [
        ([], 2, TypeError),
        (pd.DataFrame({"AAA": [1, 2]}), 1, ValueError),
        (pd.DataFrame(), 2, ValueError),
        (
            pd.DataFrame(
                {"AAA": [1]},
                index=[pd.Timestamp("2024-01-01")],
            ),
            2,
            ValueError,
        ),
        (
            pd.DataFrame(
                {"AAA": [0, -1]},
                index=pd.date_range("2024-01-01", periods=2),
            ),
            2,
            ValueError,
        ),
    ],
)
def test_validar_precos_rejeita_entradas_invalidas(
    precos,
    minimo,
    erro,
) -> None:
    with pytest.raises(erro):
        validar_precos(precos, minimo_observacoes=minimo)


def test_carregar_csv_valida_arquivo_e_coluna_data(
    tmp_path,
    precos_basicos,
) -> None:
    inexistente = tmp_path / "inexistente.csv"
    with pytest.raises(FileNotFoundError):
        carregar_csv(inexistente)

    sem_data = tmp_path / "sem_data.csv"
    precos_basicos.to_csv(sem_data, index=False)
    with pytest.raises(ValueError, match="date"):
        carregar_csv(sem_data)


def test_carregar_yfinance_rejeita_dependencia_ausente(
    monkeypatch,
) -> None:
    monkeypatch.setitem(sys.modules, "yfinance", None)
    with pytest.raises(RuntimeError, match="não está instalado"):
        carregar_yfinance(["AAA"], "2024-01-01", "2024-02-01")


def test_carregar_yfinance_rejeita_resposta_vazia(monkeypatch) -> None:
    modulo = SimpleNamespace(download=lambda *args, **kwargs: pd.DataFrame())
    monkeypatch.setitem(sys.modules, "yfinance", modulo)

    with pytest.raises(RuntimeError, match="não devolveu preços"):
        carregar_yfinance(["AAA"], "2024-01-01", "2024-02-01")


def test_carregar_yfinance_extrai_close_multiindex(monkeypatch) -> None:
    datas = pd.date_range("2024-01-01", periods=2)
    colunas = pd.MultiIndex.from_product(
        [["Close", "Open"], ["AAA", "BBB"]]
    )
    bruto = pd.DataFrame(
        [
            [10, 20, 9, 19],
            [11, 21, 10, 20],
        ],
        index=datas,
        columns=colunas,
    )
    modulo = SimpleNamespace(download=lambda *args, **kwargs: bruto)
    monkeypatch.setitem(sys.modules, "yfinance", modulo)

    resultado = carregar_yfinance(
        ["aaa", "bbb"],
        "2024-01-01",
        "2024-02-01",
    )

    assert list(resultado.columns) == ["AAA", "BBB"]
    assert resultado.iloc[-1].tolist() == [11.0, 21.0]


def test_carregar_yfinance_extrai_close_de_um_ticker(monkeypatch) -> None:
    bruto = pd.DataFrame(
        {"Close": [10, 11]},
        index=pd.date_range("2024-01-01", periods=2),
    )
    modulo = SimpleNamespace(download=lambda *args, **kwargs: bruto)
    monkeypatch.setitem(sys.modules, "yfinance", modulo)

    resultado = carregar_yfinance(
        ["aaa"],
        "2024-01-01",
        "2024-02-01",
    )

    assert list(resultado.columns) == ["AAA"]
    assert resultado["AAA"].tolist() == [10.0, 11.0]


@pytest.mark.parametrize(
    "bruto",
    [
        pd.DataFrame(
            {"Open": [10, 11]},
            index=pd.date_range("2024-01-01", periods=2),
        ),
        pd.DataFrame(
            [[10], [11]],
            index=pd.date_range("2024-01-01", periods=2),
            columns=pd.MultiIndex.from_tuples([("Open", "AAA")]),
        ),
    ],
)
def test_carregar_yfinance_exige_close(monkeypatch, bruto) -> None:
    modulo = SimpleNamespace(download=lambda *args, **kwargs: bruto)
    monkeypatch.setitem(sys.modules, "yfinance", modulo)

    with pytest.raises(RuntimeError, match="não contém Close"):
        carregar_yfinance(["AAA"], "2024-01-01", "2024-02-01")


def test_calcular_retornos_valida_limite_e_lacunas() -> None:
    datas = pd.date_range("2024-01-01", periods=4)
    precos = pd.DataFrame(
        {
            "AAA": [100.0, None, None, 110.0],
            "BBB": [50.0, 51.0, 52.0, 53.0],
        },
        index=datas,
    )

    with pytest.raises(ValueError):
        calcular_retornos(precos, preencher_ate_dias=-1)

    resultado = calcular_retornos(precos, preencher_ate_dias=1)

    assert resultado.loc["2024-01-02", "AAA"] == pytest.approx(0.0)
    assert pd.isna(resultado.loc["2024-01-03", "AAA"])
    assert pd.isna(resultado.loc["2024-01-04", "AAA"])


def test_janela_disponivel_valida_tamanho_e_timezone(
    precos_basicos,
) -> None:
    with pytest.raises(ValueError, match="pelo menos 2"):
        janela_disponivel(
            precos_basicos,
            precos_basicos.index[-1],
            observacoes=1,
        )

    with pytest.raises(ValueError, match="São necessárias"):
        janela_disponivel(
            precos_basicos,
            precos_basicos.index[0],
            observacoes=3,
        )

    corte = pd.Timestamp(precos_basicos.index[-1]).tz_localize("UTC")
    janela = janela_disponivel(
        precos_basicos,
        corte,
        observacoes=2,
    )
    assert janela.index.equals(precos_basicos.index[-2:])


def test_benchmark_cdi_aceita_escalar_e_serie(
    precos_basicos,
) -> None:
    escalar = benchmark_cdi(precos_basicos.index, 0.10)
    esperado = (1.10 ** (1 / 252)) - 1
    assert escalar.tolist() == pytest.approx(
        [esperado] * len(escalar)
    )

    taxas = pd.Series(
        [0.10, 0.12],
        index=precos_basicos.index[[0, 2]],
    )
    serie = benchmark_cdi(precos_basicos.index, taxas)
    assert serie.notna().all()
    assert serie.iloc[0] != serie.iloc[-1]


@pytest.mark.parametrize(
    ("taxa", "periodos"),
    [
        (0.10, 0),
        (
            pd.Series(
                [float("nan")],
                index=[pd.Timestamp("2024-01-01")],
            ),
            252,
        ),
        (-1.0, 252),
    ],
)
def test_benchmark_cdi_rejeita_taxas_invalidas(taxa, periodos) -> None:
    indice = pd.date_range("2024-01-01", periods=2)
    with pytest.raises(ValueError):
        benchmark_cdi(indice, taxa, periodos_ano=periodos)


def test_retorno_carteira_fixa_normaliza_pesos_e_colunas(
    precos_basicos,
) -> None:
    retornos = precos_basicos.pct_change(fill_method=None).dropna()
    resultado = retorno_carteira_fixa(
        retornos.rename(columns=str.lower),
        {"aaa": 3, "bbb": 1},
    )
    esperado = retornos["AAA"] * 0.75 + retornos["BBB"] * 0.25
    pd.testing.assert_series_equal(
        resultado,
        esperado.rename("Carteira fixa"),
    )


@pytest.mark.parametrize(
    ("retornos", "pesos"),
    [
        (pd.DataFrame(), {"AAA": 1}),
        (pd.DataFrame({"AAA": [0.1]}), {"BBB": 1}),
        (pd.DataFrame({"AAA": [0.1]}), {"AAA": -1}),
        (pd.DataFrame({"AAA": [0.1]}), {"AAA": 0}),
    ],
)
def test_retorno_carteira_fixa_rejeita_entradas_invalidas(
    retornos,
    pesos,
) -> None:
    with pytest.raises(ValueError):
        retorno_carteira_fixa(retornos, pesos)


def test_montar_benchmarks_reune_referencias(
    precos_basicos,
) -> None:
    retornos = precos_basicos.pct_change(fill_method=None).dropna()
    resultado = montar_benchmarks(
        retornos,
        cdi_anual=0.10,
        coluna_ibov="AAA",
    )
    assert list(resultado.columns) == [
        "EQUIPONDERADO",
        "CDI",
        "IBOVESPA",
    ]
    assert resultado.index.equals(retornos.index)


def test_montar_benchmarks_rejeita_entrada_e_ibov_ausente() -> None:
    with pytest.raises(ValueError):
        montar_benchmarks(pd.DataFrame())

    retornos = pd.DataFrame(
        {"AAA": [0.01]},
        index=[pd.Timestamp("2024-01-01")],
    )
    with pytest.raises(ValueError, match="IBOV"):
        montar_benchmarks(retornos, coluna_ibov="IBOV")
