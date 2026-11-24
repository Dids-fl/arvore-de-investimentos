"""Retornos mensais históricos de cada classe da carteira.

A base fica em ``decisao/dados/indices_mensais.csv`` (retorno de cada mês,
desde 2000), gerada por ``python scripts/atualizar_indices_historicos.py``
com dados gratuitos:

- ``cdi``: CDI diário do Banco Central (SGS 12);
- ``ipca_mais``: Tesouro IPCA+ sem cupom de ~5 anos, com marcação a mercado
  (preços do Tesouro Transparente, desde 2005);
- ``ibov``: Ibovespa (Yahoo Finance);
- ``fii``: média igual dos FIIs líquidos (CVM + Yahoo, desde 2020);
- ``usd``: dólar (Yahoo, desde 2004);
- ``btc``: bitcoin em reais (Yahoo ou, se ele falhar, a API pública do
  Mercado Bitcoin).

Ao rodar o app, os meses que faltam no fim da base são completados com CDI,
Ibovespa e dólar baixados na hora (cache de um dia). Meses sem dado de uma
classe usam um substituto de risco parecido (``SUBSTITUTO``).
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

ARQUIVO_BASE = Path(__file__).with_name("dados") / "indices_mensais.csv"
CACHE_RECENTES = Path.home() / ".cache" / "arvore_investimentos" / "indices_recentes.csv"
TTL_RECENTES = 24 * 60 * 60
SERIES = ("cdi", "ipca_mais", "ibov", "fii", "usd", "btc")

# Cada categoria do app vira uma mistura das séries. Multimercado e
# previdência sem renda fixa pura não têm índice gratuito: usam uma mistura
# documentada (70% CDI, 15% IPCA+, 15% Ibovespa).
_MULTI = {"cdi": 0.70, "ipca_mais": 0.15, "ibov": 0.15}
PROXY_CATEGORIA: dict[str, dict[str, float]] = {
    "rf": {"cdi": 1}, "rf_liq": {"cdi": 1}, "rf_reserva": {"cdi": 1}, "rf_selic_cdb": {"cdi": 1},
    "rf_reavalie": {"cdi": 1}, "fundos_rf": {"cdi": 1}, "fundos_rf_liq": {"cdi": 1},
    "prev_pgbl_rf": {"cdi": 1}, "prev_vgbl_rf": {"cdi": 1}, "coe": {"cdi": 1},
    "estruturados": {"cdi": 1}, "ofertas": {"cdi": 1},
    "rf_ipca": {"ipca_mais": 1},
    "rf_equilibrio": {"cdi": 0.5, "ipca_mais": 0.5},
    "fundos": _MULTI, "fundos_div": _MULTI, "fundos_multi": _MULTI,
    "prev_pgbl": _MULTI, "prev_vgbl": _MULTI,
    "fiis": {"fii": 1}, "fiis_del": {"fii": 1},
    "rv": {"ibov": 1}, "rv_dca": {"ibov": 1}, "rv_compl": {"ibov": 1},
    "fundos_acoes": {"ibov": 1}, "fundos_etf": {"ibov": 1}, "fundos_dca": {"ibov": 1},
    "rv_cripto": {"btc": 1}, "fundos_cripto": {"btc": 1},
    "cambio": {"usd": 1},
}
# Quando uma série não existe num mês (FIIs antes de 2020, IPCA+ antes de
# 2005, bitcoin), usa-se um substituto de risco parecido.
SUBSTITUTO: dict[str, dict[str, float]] = {
    "fii": {"ipca_mais": 0.5, "ibov": 0.5},
    "btc": {"ibov": 1},
    "usd": {"cdi": 1},
    "ipca_mais": {"cdi": 1},
}


MERCADO_BITCOIN_CANDLES = "https://api.mercadobitcoin.net/api/v4/candles"


def _fechamentos_candles(dados) -> pd.Series:
    """Converte a resposta de candles (colunas ``t``/``c`` ou lista de dicts)."""
    if isinstance(dados, dict) and "t" in dados and "c" in dados:
        datas, precos = dados["t"], dados["c"]
    elif isinstance(dados, list):
        datas = [item.get("timestamp", item.get("t")) for item in dados]
        precos = [item.get("close", item.get("c")) for item in dados]
    else:
        raise ValueError("formato de candles inesperado")
    serie = pd.Series(
        pd.to_numeric(pd.Series(precos), errors="coerce").to_numpy(),
        index=pd.to_datetime(pd.to_numeric(pd.Series(datas)), unit="s"),
    )
    return serie.dropna().sort_index()


def btc_mercado_bitcoin(inicio: str = "2014-01-01", sessao=None) -> pd.Series:
    """Preço diário do bitcoin em reais pela API pública do Mercado Bitcoin.

    Gratuita e sem chave. Usada quando o Yahoo não entrega ``BTC-BRL``.
    Busca em blocos de um ano para respeitar o limite de candles por consulta.
    """
    import requests

    sessao = sessao or requests.Session()
    partes = []
    atual = pd.Timestamp(inicio)
    fim = pd.Timestamp.today().normalize()
    while atual < fim:
        proximo = min(atual + pd.DateOffset(years=1), fim)
        resposta = sessao.get(
            MERCADO_BITCOIN_CANDLES,
            params={
                "symbol": "BTC-BRL",
                "resolution": "1d",
                "from": int(atual.timestamp()),
                "to": int(proximo.timestamp()),
            },
            timeout=30,
        )
        resposta.raise_for_status()
        partes.append(_fechamentos_candles(resposta.json()))
        atual = proximo
    serie = pd.concat(partes) if partes else pd.Series(dtype=float)
    return serie[~serie.index.duplicated()].sort_index()


def ler_base(arquivo: Path = ARQUIVO_BASE) -> pd.DataFrame:
    tabela = pd.read_csv(arquivo, index_col="mes", parse_dates=["mes"])
    return tabela.reindex(columns=list(SERIES)).astype(float)


def _baixar_recentes(desde: pd.Timestamp) -> pd.DataFrame:
    """CDI, Ibovespa e dólar mensais desde ``desde`` (fontes online)."""
    colunas: dict[str, pd.Series] = {}
    try:
        from bcb import sgs

        cdi = sgs.get({"cdi": 12}, start=(desde - pd.DateOffset(months=1)).date())["cdi"]
        fator = (1 + cdi / 100).cumprod().resample("ME").last()
        colunas["cdi"] = fator.pct_change(fill_method=None)
    except Exception as exc:  # noqa: BLE001 — sem internet: fica com a base
        logger.info("CDI recente indisponível: %s", exc)
    try:
        import yfinance as yf

        for nome, ticker in (("ibov", "^BVSP"), ("usd", "USDBRL=X")):
            dados = yf.Ticker(ticker).history(
                start=(desde - pd.DateOffset(months=1)).date(), interval="1d", auto_adjust=True
            )
            if not dados.empty:
                fechamento = dados["Close"]
                fechamento.index = fechamento.index.tz_localize(None)
                colunas[nome] = fechamento.resample("ME").last().pct_change(fill_method=None)
    except Exception as exc:  # noqa: BLE001
        logger.info("Ibovespa/dólar recentes indisponíveis: %s", exc)
    if not colunas:
        return pd.DataFrame(columns=list(SERIES))
    return pd.DataFrame(colunas).loc[desde:]


def carregar_indices(
    *,
    atualizar: bool = True,
    hoje: pd.Timestamp | None = None,
    arquivo: Path = ARQUIVO_BASE,
) -> pd.DataFrame:
    """Retornos mensais das classes; completa os meses recentes quando possível."""
    base = ler_base(arquivo)
    if not atualizar:
        return base
    hoje = pd.Timestamp(hoje or pd.Timestamp.today()).normalize()
    ultimo_mes_fechado = (hoje - pd.offsets.MonthBegin(1)) - pd.Timedelta(1, unit="D")
    if base.index.max() >= ultimo_mes_fechado:
        return base
    recentes = None
    try:
        if CACHE_RECENTES.is_file() and time.time() - CACHE_RECENTES.stat().st_mtime < TTL_RECENTES:
            recentes = pd.read_csv(CACHE_RECENTES, index_col="mes", parse_dates=["mes"])
    except (OSError, ValueError):
        recentes = None
    if recentes is None:
        recentes = _baixar_recentes(base.index.max() + pd.Timedelta(1, unit="D"))
        try:
            CACHE_RECENTES.parent.mkdir(parents=True, exist_ok=True)
            recentes.rename_axis("mes").to_csv(CACHE_RECENTES)
        except OSError:
            pass
    recentes = recentes.loc[(recentes.index > base.index.max()) & (recentes.index <= ultimo_mes_fechado)]
    if recentes.empty:
        return base
    return pd.concat([base, recentes.reindex(columns=list(SERIES))]).sort_index()


def retornos_carteira(carteira: dict[str, float], indices: pd.DataFrame) -> pd.Series:
    """Retorno mensal da carteira rebalanceada todo mês (pesos em %)."""
    total = pd.Series(0.0, index=indices.index)
    soma_pesos = sum(float(p) for p in carteira.values()) or 1.0
    for categoria, peso in carteira.items():
        mistura = PROXY_CATEGORIA.get(categoria, {"cdi": 1})
        for serie, fracao in mistura.items():
            r = indices[serie] if serie in indices else pd.Series(index=indices.index, dtype=float)
            if r.isna().any():
                substituto = sum(
                    indices[s] * f for s, f in SUBSTITUTO.get(serie, {"cdi": 1}).items()
                )
                r = r.fillna(substituto)
            total += float(peso) / soma_pesos * fracao * r.fillna(indices["cdi"]).fillna(0)
    return total.loc[indices["cdi"].notna()]


def series_usadas(carteira: dict[str, float], indices: pd.DataFrame) -> dict[str, str]:
    """Para cada série usada, desde quando há dado real (o resto é substituto)."""
    usadas: dict[str, str] = {}
    for categoria in carteira:
        for serie in PROXY_CATEGORIA.get(categoria, {"cdi": 1}):
            if serie in indices and indices[serie].notna().any():
                usadas[serie] = indices[serie].first_valid_index().strftime("%m/%Y")
            else:
                usadas[serie] = "sem dado (substituto)"
    return usadas
