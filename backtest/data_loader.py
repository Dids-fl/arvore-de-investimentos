"""Carregamento e validação de preços históricos."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pandas as pd


def _tickers_validos(tickers: Iterable[str]) -> list[str]:
    resultado = []
    for ticker in tickers:
        if not isinstance(ticker, str) or not ticker.strip():
            raise ValueError("Cada ticker deve ser um texto não vazio.")
        normalizado = ticker.strip().upper()
        if normalizado not in resultado:
            resultado.append(normalizado)
    if not resultado:
        raise ValueError("Informe pelo menos um ticker.")
    return resultado


def validar_precos(
    precos: pd.DataFrame,
    *,
    minimo_observacoes: int = 2,
) -> pd.DataFrame:
    """Normaliza uma tabela de preços e rejeita valores impossíveis."""
    if not isinstance(precos, pd.DataFrame):
        raise TypeError("precos deve ser um pandas.DataFrame.")
    if minimo_observacoes < 2:
        raise ValueError("minimo_observacoes deve ser pelo menos 2.")
    if precos.empty or not len(precos.columns):
        raise ValueError("A tabela de preços está vazia.")

    resultado = precos.copy()
    resultado.index = pd.to_datetime(resultado.index, errors="coerce")
    resultado = resultado.loc[~resultado.index.isna()]
    if resultado.index.tz is not None:
        resultado.index = resultado.index.tz_convert(None)
    resultado = resultado.sort_index()
    resultado = resultado.loc[~resultado.index.duplicated(keep="last")]
    resultado.columns = [str(coluna).strip().upper() for coluna in resultado]
    resultado = resultado.apply(pd.to_numeric, errors="coerce")
    resultado = resultado.where(resultado > 0)
    resultado = resultado.dropna(axis=1, how="all").dropna(how="all")

    if len(resultado) < minimo_observacoes:
        raise ValueError(
            "Histórico insuficiente: "
            f"{len(resultado)} observação(ões), mínimo {minimo_observacoes}."
        )
    if not len(resultado.columns):
        raise ValueError("Nenhuma coluna contém preços positivos válidos.")
    return resultado.astype(float)


def carregar_csv(
    caminho: str | Path,
    *,
    coluna_data: str = "date",
    minimo_observacoes: int = 2,
) -> pd.DataFrame:
    """Carrega CSV no formato ``date,TICKER1,TICKER2,...``."""
    arquivo = Path(caminho)
    if not arquivo.is_file():
        raise FileNotFoundError(f"Arquivo histórico não encontrado: {arquivo}")

    tabela = pd.read_csv(arquivo)
    if coluna_data not in tabela:
        raise ValueError(f"O CSV não contém a coluna {coluna_data!r}.")
    tabela = tabela.set_index(coluna_data)
    return validar_precos(
        tabela,
        minimo_observacoes=minimo_observacoes,
    )


def carregar_yfinance(
    tickers: Iterable[str],
    inicio: str,
    fim: str,
    *,
    auto_adjust: bool = True,
) -> pd.DataFrame:
    """Baixa preços ajustados; a importação é tardia para facilitar testes."""
    nomes = _tickers_validos(tickers)
    try:
        import yfinance as yf
    except ImportError as exc:
        raise RuntimeError(
            "yfinance não está instalado; use um CSV ou instale a dependência."
        ) from exc

    bruto = yf.download(
        nomes,
        start=inicio,
        end=fim,
        auto_adjust=auto_adjust,
        progress=False,
        actions=False,
        group_by="column",
    )
    if bruto is None or bruto.empty:
        raise RuntimeError("Yahoo Finance não devolveu preços para o período.")

    if isinstance(bruto.columns, pd.MultiIndex):
        campo = "Close"
        if campo not in bruto.columns.get_level_values(0):
            raise RuntimeError("Resposta do Yahoo Finance não contém Close.")
        precos = bruto[campo]
    elif "Close" in bruto:
        precos = bruto[["Close"]].rename(columns={"Close": nomes[0]})
    else:
        raise RuntimeError("Resposta do Yahoo Finance não contém Close.")

    if isinstance(precos, pd.Series):
        precos = precos.to_frame(name=nomes[0])
    return validar_precos(precos)


def calcular_retornos(
    precos: pd.DataFrame,
    *,
    preencher_ate_dias: int = 3,
) -> pd.DataFrame:
    """Calcula retornos simples sem preencher lacunas longas."""
    if preencher_ate_dias < 0:
        raise ValueError("preencher_ate_dias não pode ser negativo.")
    dados = validar_precos(precos)
    if preencher_ate_dias:
        dados = dados.ffill(limit=preencher_ate_dias)
    retornos = dados.pct_change(fill_method=None)
    retornos = retornos.replace([float("inf"), float("-inf")], pd.NA)
    return retornos.dropna(how="all").astype(float)


def janela_disponivel(
    precos: pd.DataFrame,
    data_corte: object,
    *,
    observacoes: int,
) -> pd.DataFrame:
    """Retorna somente dados conhecidos até a data de decisão."""
    if observacoes < 2:
        raise ValueError("observacoes deve ser pelo menos 2.")
    dados = validar_precos(precos)
    corte = pd.Timestamp(data_corte)
    if corte.tzinfo is not None:
        corte = corte.tz_convert(None)
    janela = dados.loc[:corte].tail(observacoes)
    if len(janela) < observacoes:
        raise ValueError(
            f"São necessárias {observacoes} observações até {corte.date()}."
        )
    return janela
