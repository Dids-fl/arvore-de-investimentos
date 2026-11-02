"""Gera ``decisao/dados/indices_mensais.csv``: retorno mensal de cada classe.

Reaproveita os coletores da validação histórica (Banco Central, Tesouro
Transparente, CVM e Yahoo Finance, todos gratuitos). Demora alguns minutos
na primeira vez porque baixa o histórico de preços do Tesouro e dos FIIs;
depois usa o cache em ``~/.cache/arvore_investimentos/historico``.

Uso:
    python scripts/atualizar_indices_historicos.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backtest import validacao_historica as vh  # noqa: E402
from decisao.historico import ARQUIVO_BASE, SERIES, btc_mercado_bitcoin  # noqa: E402

INICIO = "2000-01-01"


def gerar() -> pd.DataFrame:
    niveis = {
        "cdi": vh._mensal((1 + vh.serie_cdi() / 100).cumprod()),
        "ipca_mais": vh._mensal(vh.indice_ipca_mais()),
        "ibov": vh._mensal(vh.serie_yahoo("^BVSP")),
        "fii": vh._mensal(vh.indice_fii()),
    }
    for nome, ticker in (("usd", "USDBRL=X"), ("btc", "BTC-BRL")):
        try:
            niveis[nome] = vh._mensal(vh.serie_yahoo(ticker))
        except Exception as exc:  # noqa: BLE001 — série opcional
            print(f"{ticker} indisponível no Yahoo: {exc}")
    if "btc" not in niveis:
        try:
            niveis["btc"] = vh._mensal(btc_mercado_bitcoin())
        except Exception as exc:  # noqa: BLE001 — série opcional
            print(f"Bitcoin indisponível no Mercado Bitcoin: {exc}")
    tabela = pd.DataFrame(niveis).pct_change(fill_method=None).loc[INICIO:]
    # Só meses já encerrados: o último mês pode estar pela metade.
    hoje = pd.Timestamp.today().normalize()
    tabela = tabela.loc[tabela.index < hoje - pd.offsets.MonthBegin(1)]
    return tabela.reindex(columns=list(SERIES)).rename_axis("mes")


def main() -> int:
    tabela = gerar()
    ARQUIVO_BASE.parent.mkdir(parents=True, exist_ok=True)
    tabela.round(6).to_csv(ARQUIVO_BASE, date_format="%Y-%m-%d")
    inicio = {c: (tabela[c].first_valid_index() or "—") for c in tabela}
    print(f"{len(tabela)} meses até {tabela.index.max():%m/%Y} em {ARQUIVO_BASE}")
    print({c: (str(v)[:7]) for c, v in inicio.items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
