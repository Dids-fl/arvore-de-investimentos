"""Prêmio de risco das ações sobre o CDI e volatilidade do Ibovespa.

O app projeta ações como "juros esperados (curva Selic/Focus) + prêmio". O
prêmio não é um número fixo: é a média do que o Ibovespa rendeu acima do CDI
em todas as janelas de ``janela_anos`` já encerradas até a data, usando todo
o histórico desde o Plano Real. Assim ele se atualiza sozinho e só usa
informação disponível no passado.

As mesmas funções são usadas pelo app (``mercado.py``) e pela validação
histórica (``backtest/validacao_historica.py``).
"""

from __future__ import annotations

import math

import pandas as pd

JANELA_PREMIO_ANOS = 5
# Percentil 20 da distribuição normal: o cenário pessimista é aquele que o
# resultado real supera em cerca de 80% das vezes.
Z_PESSIMISTA = 0.8416


def _indice_cdi(cdi_diario_pct: pd.Series) -> pd.Series:
    """Índice acumulado do CDI a partir da taxa diária em %."""
    return (1 + cdi_diario_pct.sort_index().astype(float) / 100).cumprod()


def _valor_ate(serie: pd.Series, dia: pd.Timestamp) -> float | None:
    anteriores = serie.loc[:dia]
    return None if anteriores.empty else float(anteriores.iloc[-1])


def premio_historico(
    ibov: pd.Series,
    cdi_diario_pct: pd.Series,
    ate: pd.Timestamp | str,
    *,
    janela_anos: int = JANELA_PREMIO_ANOS,
    minimo_janelas: int = 24,
) -> float | None:
    """Média do excesso anual do Ibovespa sobre o CDI em janelas encerradas.

    As janelas começam a cada mês e terminam até ``ate``. Devolve ``None``
    se houver menos de ``minimo_janelas`` janelas (histórico insuficiente).
    """
    ate = pd.Timestamp(ate)
    ibov = ibov.sort_index().loc[:ate].dropna()
    indice_cdi = _indice_cdi(cdi_diario_pct.loc[:ate])
    if ibov.empty or indice_cdi.empty:
        return None
    inicio = max(ibov.index.min(), indice_cdi.index.min())
    excessos = []
    for comeco in pd.date_range(inicio, ate - pd.DateOffset(years=janela_anos), freq="MS"):
        fim = comeco + pd.DateOffset(years=janela_anos)
        valores = (
            _valor_ate(ibov, comeco),
            _valor_ate(ibov, fim),
            _valor_ate(indice_cdi, comeco),
            _valor_ate(indice_cdi, fim),
        )
        if any(v is None or v <= 0 for v in valores):
            continue
        ibov_ini, ibov_fim, cdi_ini, cdi_fim = valores
        acao = (ibov_fim / ibov_ini) ** (1 / janela_anos) - 1
        juros = (cdi_fim / cdi_ini) ** (1 / janela_anos) - 1
        excessos.append(acao - juros)
    if len(excessos) < minimo_janelas:
        return None
    return sum(excessos) / len(excessos)


def volatilidade_anual(
    ibov: pd.Series,
    ate: pd.Timestamp | str,
    *,
    anos: int = 10,
) -> float | None:
    """Desvio-padrão anualizado dos retornos diários do Ibovespa."""
    ate = pd.Timestamp(ate)
    janela = ibov.sort_index().loc[ate - pd.DateOffset(years=anos):ate].dropna()
    if len(janela) < 250:
        return None
    retornos = janela.pct_change().dropna()
    return float(retornos.std() * math.sqrt(252))


def desconto_pessimista(volatilidade: float, anos: float) -> float:
    """Quanto o cenário pessimista fica abaixo do central, em taxa anual.

    A incerteza da taxa média anual cai com a raiz do prazo, então o desconto
    é maior em prazos curtos.
    """
    return Z_PESSIMISTA * volatilidade / math.sqrt(max(float(anos), 1.0))
