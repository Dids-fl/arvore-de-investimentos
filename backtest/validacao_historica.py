"""Validação histórica: o que o código previa no passado x o que aconteceu.

Para cada data-base no passado, monta os dados de mercado exatamente como
estavam disponíveis naquele dia (Selic, IPCA 12 meses já publicado, medianas
do Focus daquela data e CAGR do Ibovespa até ali), pede ao ``engine`` as
mesmas hipóteses de retorno usadas no app e compara com o que de fato
aconteceu depois (CDI, Ibovespa e IPCA realizados).

Também testa os rankers que têm dados históricos gratuitos e "point-in-time"
(Tesouro Direto, fundos e previdência da CVM e ETFs), comparando o retorno
futuro dos ativos mais bem pontuados com o do universo elegível.

Uso:
    python -m backtest.validacao_historica            # todas as partes
    python -m backtest.validacao_historica --partes projecoes tesouro

Todas as fontes são públicas e gratuitas. Os downloads ficam em cache em
``~/.cache/arvore_investimentos/historico``.
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections.abc import Callable, Iterable
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

CACHE_DIR = Path.home() / ".cache" / "arvore_investimentos" / "historico"
SAIDA_JSON = Path(__file__).resolve().parent / "resultados" / "validacao_historica.json"
SAIDA_MD = Path(__file__).resolve().parents[1] / "docs" / "validacao-historica.md"

HORIZONTES_ANOS = (1, 3, 5)


# ── Cache simples em disco ────────────────────────────────────────────────────

def _em_cache(nome: str, gerar: Callable[[], pd.DataFrame | pd.Series]):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    arquivo = CACHE_DIR / f"{nome}.pkl"
    if arquivo.exists() and (datetime.now().timestamp() - arquivo.stat().st_mtime) < 7 * 86400:
        return pd.read_pickle(arquivo)
    dados = gerar()
    pd.to_pickle(dados, arquivo)
    return dados


# ── Séries históricas (BCB, Focus, Yahoo) ─────────────────────────────────────

def _sgs(codigo: int, inicio: str, fim: str | None = None) -> pd.Series:
    """Série do SGS em blocos de 5 anos (séries diárias limitam a 10 anos)."""
    from bcb import sgs

    fim_dt = pd.Timestamp(fim) if fim else pd.Timestamp(date.today())
    blocos = []
    atual = pd.Timestamp(inicio)
    while atual <= fim_dt:
        proximo = min(atual + pd.DateOffset(years=5) - pd.Timedelta(days=1), fim_dt)
        df = sgs.get({"v": codigo}, start=atual.strftime("%Y-%m-%d"), end=proximo.strftime("%Y-%m-%d"))
        if not df.empty:
            blocos.append(df["v"])
        atual = proximo + pd.Timedelta(days=1)
    serie = pd.concat(blocos).sort_index()
    return serie[~serie.index.duplicated(keep="last")].astype(float)


def serie_cdi() -> pd.Series:
    """CDI diário (% ao dia), SGS 12, desde 1995 (pós-Plano Real)."""
    return _em_cache("cdi_diario_1995", lambda: _sgs(12, "1995-01-01"))


def serie_selic_meta() -> pd.Series:
    """Meta Selic (% a.a.), SGS 432."""
    return _em_cache("selic_meta", lambda: _sgs(432, "2003-01-01"))


def serie_ipca_mensal() -> pd.Series:
    """IPCA mensal (% no mês), SGS 433."""
    return _em_cache("ipca_mensal", lambda: _sgs(433, "2000-01-01"))


def serie_ipca_12m() -> pd.Series:
    """IPCA acumulado em 12 meses (%), SGS 13522."""
    return _em_cache("ipca_12m", lambda: _sgs(13522, "2000-01-01"))


def focus_anual(indicador: str) -> pd.DataFrame:
    """Medianas anuais do Focus (Data, DataReferencia, Mediana) desde 2002."""
    def baixar() -> pd.DataFrame:
        from bcb import Expectativas

        endpoint = Expectativas().get_endpoint("ExpectativasMercadoAnuais")
        partes = []
        for ano in range(2002, date.today().year + 1):
            df = (
                endpoint.query()
                .filter(
                    endpoint.Indicador == indicador,
                    endpoint.baseCalculo == 0,
                    endpoint.Data >= f"{ano}-01-01",
                    endpoint.Data <= f"{ano}-12-31",
                )
                .select(endpoint.Data, endpoint.DataReferencia, endpoint.Mediana)
                .collect()
            )
            partes.append(df)
        dados = pd.concat(partes, ignore_index=True)
        dados["Data"] = pd.to_datetime(dados["Data"])
        dados["DataReferencia"] = dados["DataReferencia"].astype(int)
        return dados

    return _em_cache(f"focus_{indicador.lower()}_2002", baixar)


def serie_yahoo(ticker: str) -> pd.Series:
    """Fechamento diário do Yahoo Finance."""
    def baixar() -> pd.Series:
        import yfinance as yf

        hist = yf.Ticker(ticker).history(period="max", auto_adjust=False, actions=False)
        serie = hist["Close"].dropna()
        serie.index = serie.index.tz_localize(None)
        return serie

    return _em_cache(f"yahoo_{ticker.replace('^', '_')}", baixar)


# ── Utilidades de séries ──────────────────────────────────────────────────────

def _valor_ate(serie: pd.Series, dia: pd.Timestamp) -> float | None:
    anteriores = serie.loc[:dia]
    return None if anteriores.empty else float(anteriores.iloc[-1])


def _anualizar(fator: float, anos: float) -> float:
    return fator ** (1.0 / anos) - 1.0


def cdi_realizado(inicio: pd.Timestamp, fim: pd.Timestamp) -> float | None:
    """Fator acumulado do CDI entre duas datas (exclui o dia inicial)."""
    cdi = serie_cdi()
    janela = cdi.loc[(cdi.index > inicio) & (cdi.index <= fim)]
    if janela.empty or cdi.index.max() < fim - pd.Timedelta(days=7):
        return None
    return float((1 + janela / 100).prod())


def ipca_realizado(inicio: pd.Timestamp, fim: pd.Timestamp) -> float | None:
    """Fator acumulado do IPCA dos meses entre as duas datas."""
    ipca = serie_ipca_mensal()
    meses = ipca.loc[(ipca.index >= inicio.to_period("M").to_timestamp()) & (ipca.index < fim.to_period("M").to_timestamp())]
    esperado = (fim.to_period("M") - inicio.to_period("M")).n
    if len(meses) < esperado:
        return None
    return float((1 + meses / 100).prod())


def _spearman(a: list[float], b: list[float]) -> float | None:
    if len(a) < 5:
        return None
    return float(pd.Series(a).rank().corr(pd.Series(b).rank()))


# ── Mercado "como era" numa data passada ──────────────────────────────────────

def mercado_em(dia: pd.Timestamp, incluir_ibov: bool = True) -> dict[str, Any] | None:
    """Monta o payload de ``mercado.load_market_data`` com dados até ``dia``.

    O IPCA 12 meses usa apenas meses já divulgados (o IBGE publica cerca de
    10 dias após o fim do mês), e o Focus usa a última mediana publicada até
    a data, para não usar informação do futuro.
    """
    selic = _valor_ate(serie_selic_meta(), dia)
    ipca12 = _valor_ate(serie_ipca_12m(), dia - pd.Timedelta(days=40))
    if selic is None or ipca12 is None:
        return None
    ibov_cagr = None
    ibov_vol = None
    if incluir_ibov:
        ibov = serie_yahoo("^BVSP")
        inicio_10a = dia - pd.DateOffset(years=10)
        ibov_ini = _valor_ate(ibov, inicio_10a)
        ibov_fim = _valor_ate(ibov, dia)
        if not ibov_ini or not ibov_fim or ibov.index.min() > inicio_10a + pd.Timedelta(days=10):
            return None
        ibov_cagr = _anualizar(ibov_fim / ibov_ini, 10)
        from macroeconomia.premio_acoes import volatilidade_anual

        ibov_vol = volatilidade_anual(ibov, dia)

    def focus_por_ano(indicador: str) -> dict[int, float]:
        focus = focus_anual(indicador)
        ate = focus.loc[(focus["Data"] <= dia) & (focus["Data"] > dia - pd.Timedelta(days=45))]
        resultado = {}
        for ano in range(dia.year, dia.year + 4):
            linhas = ate.loc[ate["DataReferencia"] == ano].sort_values("Data")
            if not linhas.empty:
                resultado[ano] = float(linhas["Mediana"].iloc[-1]) / 100
        return resultado

    return {
        "_schema_version": 4,
        "selic": selic / 100,
        "focus_selic_por_ano": focus_por_ano("Selic"),
        "focus_selic": None,
        "focus_ipca_por_ano": focus_por_ano("IPCA"),
        "ipca": ipca12 / 100,
        "ibov_cagr": ibov_cagr,
        "ibov_volatilidade": ibov_vol,
        "data_ref": dia.strftime("%d/%m/%Y"),
        "fontes": [],
        "avisos": [],
        "fetched_at": dia.isoformat(),
        "cache_status": "historico",
    }


def datas_base(inicio: str, fim: str, meses: int = 6) -> list[pd.Timestamp]:
    """Primeiro dia útil de cada período, de ``inicio`` a ``fim``."""
    datas = pd.date_range(inicio, fim, freq=f"{meses}MS")
    return [pd.bdate_range(d, d + pd.Timedelta(days=7))[0] for d in datas]


# ── Parte 1: projeções do engine x realizado ──────────────────────────────────

def validar_projecoes() -> dict[str, Any]:
    import engine

    ibov = serie_yahoo("^BVSP")
    hoje = pd.Timestamp(date.today())
    registros = []
    for dia in datas_base("2013-01-01", (hoje - pd.DateOffset(years=1)).strftime("%Y-%m-%d")):
        mercado = mercado_em(dia)
        if mercado is None:
            continue
        for anos in HORIZONTES_ANOS:
            fim = dia + pd.DateOffset(years=anos)
            if fim > hoje - pd.Timedelta(days=10):
                continue
            taxas = engine.taxas_por_risco(
                mercado, prazo_meses=12 * anos, data_referencia=dia.date()
            )
            cdi = cdi_realizado(dia, fim)
            ibov_ini, ibov_fim = _valor_ate(ibov, dia), _valor_ate(ibov, fim)
            ipca = ipca_realizado(dia, fim)
            if cdi is None or not ibov_ini or not ibov_fim or ipca is None:
                continue
            fator_ibov = ibov_fim / ibov_ini
            realizado = {
                1: _anualizar(cdi, anos),
                3: _anualizar(fator_ibov, anos),
                # 50/50 comprado e mantido, como no nível 2 (média das taxas)
                2: _anualizar((cdi + fator_ibov) / 2, anos),
            }
            carteiras = {1: {"rf": 100}, 2: {"rf": 50, "rv": 50}, 3: {"rv": 100}}
            ipca_h = engine.ipca_esperado_mercado(
                mercado, prazo_meses=12 * anos, data_referencia=dia.date()
            )
            for nivel in (1, 2, 3):
                previsto = taxas[nivel]
                registros.append(
                    {
                        "data_base": dia.date().isoformat(),
                        "anos": anos,
                        "nivel": nivel,
                        "previsto": previsto,
                        "pessimista": engine._taxa_pessimista_carteira(
                            previsto, ipca_h, carteiras[nivel], anos, mercado
                        ),
                        "realizado": realizado[nivel],
                        "ingenuo": mercado["selic"] if nivel == 1 else None,
                    }
                )
            registros.append(
                {
                    "data_base": dia.date().isoformat(),
                    "anos": anos,
                    "nivel": "ipca",
                    # IPCA que o engine usa hoje (Focus mês a mês no horizonte)
                    "previsto": engine.ipca_esperado_mercado(
                        mercado, prazo_meses=12 * anos, data_referencia=dia.date()
                    ),
                    # método antigo: IPCA dos últimos 12 meses repetido
                    "ipca_12m": mercado["ipca"],
                    "realizado": _anualizar(ipca, anos),
                }
            )

    resumo = {}
    for chave in ("1", "2", "3", "ipca"):
        for anos in HORIZONTES_ANOS:
            grupo = [r for r in registros if str(r["nivel"]) == chave and r["anos"] == anos]
            if not grupo:
                continue
            erros = [r["previsto"] - r["realizado"] for r in grupo]
            item = {
                "amostras": len(grupo),
                "periodo": f"{grupo[0]['data_base']} a {grupo[-1]['data_base']}",
                "vies_medio": statistics.fmean(erros),
                "erro_absoluto_medio": statistics.fmean(abs(e) for e in erros),
                "previsto_medio": statistics.fmean(r["previsto"] for r in grupo),
                "realizado_medio": statistics.fmean(r["realizado"] for r in grupo),
            }
            if chave in ("1", "2", "3"):
                item["realizado_acima_do_pessimista"] = sum(
                    r["realizado"] >= r["pessimista"] for r in grupo
                ) / len(grupo)
                item["realizado_acima_do_central"] = sum(
                    r["realizado"] >= r["previsto"] for r in grupo
                ) / len(grupo)
            if chave == "1":
                item["erro_absoluto_medio_selic_constante"] = statistics.fmean(
                    abs(r["ingenuo"] - r["realizado"]) for r in grupo
                )
            if chave == "ipca":
                item["erro_absoluto_medio_ipca_12m"] = statistics.fmean(
                    abs(r["ipca_12m"] - r["realizado"]) for r in grupo
                )
            resumo[f"{chave}_{anos}a"] = item
    return {"resumo": resumo, "registros": registros}


# ── Pesquisa: regra de retorno esperado para ações ────────────────────────────

INICIO_TESTE = pd.Timestamp("2013-01-01")


def pesquisar_regra_acoes() -> dict[str, Any]:
    """Compara regras de retorno esperado de ações com treino e teste separados.

    Treino: datas-base de 2004 a 2012. Teste: 2013 em diante. Qualquer
    parâmetro (o prêmio fixo) é calibrado só no treino; o prêmio histórico é
    recalculado em cada data só com o passado.
    """
    import engine
    from macroeconomia.premio_acoes import desconto_pessimista, premio_historico, volatilidade_anual

    ibov = serie_yahoo("^BVSP")
    cdi = serie_cdi()
    hoje = pd.Timestamp(date.today())
    linhas = []
    for dia in datas_base("2004-01-01", (hoje - pd.DateOffset(years=1)).strftime("%Y-%m-%d")):
        mercado = mercado_em(dia)
        if mercado is None:
            continue
        premio = premio_historico(ibov, cdi, dia)
        vol = volatilidade_anual(ibov, dia)
        for anos in HORIZONTES_ANOS:
            fim = dia + pd.DateOffset(years=anos)
            if fim > hoje - pd.Timedelta(days=10):
                continue
            fator_cdi = cdi_realizado(dia, fim)
            ini, fin = _valor_ate(ibov, dia), _valor_ate(ibov, fim)
            if fator_cdi is None or not ini or not fin:
                continue
            rf = engine.taxas_por_risco(mercado, prazo_meses=12 * anos, data_referencia=dia.date())[1]
            linhas.append(
                {
                    "data_base": dia.date().isoformat(),
                    "teste": dia >= INICIO_TESTE,
                    "anos": anos,
                    "rf_previsto": rf,
                    "ibov_cagr_10a": mercado["ibov_cagr"],
                    "premio_historico": premio,
                    "volatilidade": vol,
                    "ipca": mercado["ipca"],
                    "ibov_realizado": _anualizar(fin / ini, anos),
                    "misto_realizado": _anualizar((fator_cdi + fin / ini) / 2, anos),
                }
            )

    treino = [r for r in linhas if not r["teste"] and r["anos"] == 5]
    premio_fixo = statistics.fmean(r["ibov_realizado"] - r["rf_previsto"] for r in treino)

    regras: dict[str, Callable[[dict], float | None]] = {
        "atual_cagr_10a": lambda r: r["ibov_cagr_10a"],
        "curva_sem_premio": lambda r: r["rf_previsto"],
        "curva_premio_fixo_treino": lambda r: r["rf_previsto"] + premio_fixo,
        "curva_premio_historico": lambda r: (
            None if r["premio_historico"] is None else r["rf_previsto"] + r["premio_historico"]
        ),
    }
    resultado: dict[str, Any] = {"premio_fixo_calibrado_no_treino": premio_fixo, "regras": {}}
    for nome, regra in regras.items():
        por_amostra = {}
        for amostra, filtro in (("treino", False), ("teste", True)):
            for anos in HORIZONTES_ANOS:
                grupo = [r for r in linhas if r["teste"] is filtro and r["anos"] == anos]
                pares = [(regra(r), r) for r in grupo if regra(r) is not None]
                if not pares:
                    continue
                erros = [prev - r["ibov_realizado"] for prev, r in pares]
                erros_misto = [
                    (prev + r["rf_previsto"]) / 2 - r["misto_realizado"] for prev, r in pares
                ]
                cobertura_nova = [
                    r["ibov_realizado"] >= prev - desconto_pessimista(r["volatilidade"], anos)
                    for prev, r in pares
                    if r["volatilidade"]
                ]
                cobertura_antiga = [
                    r["ibov_realizado"] >= engine._taxa_pessimista(prev, r["ipca"]) for prev, r in pares
                ]
                por_amostra[f"{amostra}_{anos}a"] = {
                    "amostras": len(pares),
                    "vies": statistics.fmean(erros),
                    "erro_absoluto_medio": statistics.fmean(abs(e) for e in erros),
                    "erro_absoluto_medio_misto": statistics.fmean(abs(e) for e in erros_misto),
                    "acima_pessimista_volatilidade": (
                        sum(cobertura_nova) / len(cobertura_nova) if cobertura_nova else None
                    ),
                    "acima_pessimista_antigo": sum(cobertura_antiga) / len(cobertura_antiga),
                }
        resultado["regras"][nome] = por_amostra
    resultado["linhas"] = linhas
    return resultado


# ── Parte 2: ranking do Tesouro Direto ─────────────────────────────────────────

URL_TESOURO_PACOTE = (
    "https://www.tesourotransparente.gov.br/ckan/api/3/action/"
    "package_show?id=taxas-dos-titulos-ofertados-pelo-tesouro-direto"
)


def historico_tesouro() -> pd.DataFrame:
    """Preços e taxas diários de todos os títulos desde 2004 (Tesouro Transparente)."""
    def baixar() -> pd.DataFrame:
        import io

        import requests

        pacote = requests.get(URL_TESOURO_PACOTE, timeout=60).json()
        recurso = next(
            r for r in pacote["result"]["resources"]
            if r.get("format", "").upper() == "CSV" and "precotaxatesourodireto" in r["url"].lower()
        )
        texto = requests.get(recurso["url"], timeout=300, headers={"User-Agent": "Mozilla/5.0"}).text
        df = pd.read_csv(io.StringIO(texto), sep=";", decimal=",")
        df["Data Base"] = pd.to_datetime(df["Data Base"], format="%d/%m/%Y")
        df["Data Vencimento"] = pd.to_datetime(df["Data Vencimento"], format="%d/%m/%Y")
        return df

    return _em_cache("tesouro_historico", baixar)


def _indexador_tesouro(tipo: str) -> str:
    if "IPCA" in tipo or "Renda+" in tipo or "Educa+" in tipo:
        return "IPCA"
    if "Selic" in tipo:
        return "SELIC"
    if "Prefixado" in tipo:
        return "Prefixado"
    return "Outro"


def validar_tesouro() -> dict[str, Any]:
    """Pontua os títulos à venda em datas passadas e mede o retorno realizado.

    Compra ao preço de compra (PU Compra) e vende ao preço de recompra do
    Tesouro (PU Venda) ao fim do horizonte. Títulos com fluxos intermediários
    (juros semestrais, Renda+, Educa+, IGP-M) ficam de fora porque o PU cai a
    cada pagamento e o retorno exigiria reinvestir os cupons.
    """
    from renda_fixa import ranker

    precos = historico_tesouro()
    sem_fluxos = ~precos["Tipo Titulo"].str.contains("Juros Semestrais|Renda\\+|Educa\\+|IGPM", regex=True)
    precos = precos.loc[sem_fluxos]
    hoje = pd.Timestamp(date.today())
    registros = []
    universos = []
    for dia in datas_base("2013-01-01", (hoje - pd.DateOffset(years=1)).strftime("%Y-%m-%d")):
        datas_disp = precos.loc[precos["Data Base"] >= dia, "Data Base"]
        if datas_disp.empty:
            continue
        dia_real = datas_disp.min()
        mercado = mercado_em(dia_real, incluir_ibov=False)
        if mercado is None:
            continue
        referencias = {
            "selic_atual": mercado["selic"],
            "ipca_atual": mercado["ipca"],
            "selic_por_ano": mercado["focus_selic_por_ano"],
            "ipca_por_ano": mercado["focus_ipca_por_ano"],
        }
        # Só o preço de compra indica oferta: o Tesouro Selic negocia com
        # taxa 0,00% ou negativa (ágio), e não pode ser descartado por isso.
        ofertados = precos.loc[
            (precos["Data Base"] == dia_real)
            & (precos["PU Compra Manha"] > 0)
            & precos["Taxa Compra Manha"].notna()
        ]
        for anos in (1, 3):
            fim = dia_real + pd.DateOffset(years=anos)
            if fim > hoje - pd.Timedelta(days=10):
                continue
            datas_fim = precos.loc[precos["Data Base"] >= fim, "Data Base"]
            if datas_fim.empty:
                continue
            dia_fim = datas_fim.min()
            cdi = cdi_realizado(dia_real, dia_fim)
            candidatos = []
            for _, linha in ofertados.iterrows():
                if linha["Data Vencimento"] <= dia_fim:
                    continue
                saida = precos.loc[
                    (precos["Data Base"] == dia_fim)
                    & (precos["Tipo Titulo"] == linha["Tipo Titulo"])
                    & (precos["Data Vencimento"] == linha["Data Vencimento"]),
                    "PU Venda Manha",
                ]
                if saida.empty or saida.iloc[0] <= 0:
                    continue
                titulo = {
                    "nome": linha["Tipo Titulo"],
                    "taxa": float(linha["Taxa Compra Manha"]) / 100,
                    "vencimento": linha["Data Vencimento"].strftime("%d/%m/%Y"),
                    "tipo": _indexador_tesouro(linha["Tipo Titulo"]),
                }
                produto = ranker._processar_tesouro([titulo], dia_real.strftime("%Y-%m-%d"))[0]
                produto["taxa_nominal_estimada"] = ranker.taxa_nominal_equivalente(
                    produto, referencias, dia_real.strftime("%Y-%m-%d")
                )
                if produto["taxa_nominal_estimada"] is None:
                    continue
                produto["retorno_realizado"] = _anualizar(
                    float(saida.iloc[0]) / float(linha["PU Compra Manha"]), anos
                )
                candidatos.append(produto)
            if len(candidatos) < 3:
                continue
            universos.append(
                {
                    "data_base": dia_real.date().isoformat(),
                    "anos": anos,
                    "cdi": _anualizar(cdi, anos) if cdi else None,
                    "titulos": [
                        {
                            "ticker": p["ticker"],
                            "tipo": p["tipo"],
                            "prazo_dias": p["prazo_dias"],
                            "taxa_bruta": p["taxa_bruta"],
                            "taxa_nominal_estimada": p["taxa_nominal_estimada"],
                            "retorno_realizado": p["retorno_realizado"],
                        }
                        for p in candidatos
                    ],
                }
            )
            for perfil in (1, 2, 3):
                ordem = ranker.pontuar_titulos([dict(p) for p in candidatos], perfil, anos)
                registros.append(
                    {
                        "data_base": dia_real.date().isoformat(),
                        "anos": anos,
                        "perfil": perfil,
                        "titulos": len(candidatos),
                        "escolhido": ordem[0]["ticker"],
                        "retorno_escolhido": ordem[0]["retorno_realizado"],
                        "retorno_top3": statistics.fmean(p["retorno_realizado"] for p in ordem[:3]),
                        "retorno_medio": statistics.fmean(p["retorno_realizado"] for p in candidatos),
                        "retorno_mediano": statistics.median(p["retorno_realizado"] for p in candidatos),
                        "melhor_possivel": max(p["retorno_realizado"] for p in candidatos),
                        "cdi": _anualizar(cdi, anos) if cdi else None,
                        "spearman": _spearman(
                            [p["score"] for p in ordem],
                            [p["retorno_realizado"] for p in ordem],
                        ),
                    }
                )
    return {"resumo": _resumir_ranking(registros), "registros": registros, "universos": universos}


def _resumir_ranking(registros: list[dict]) -> dict[str, Any]:
    resumo = {}
    chaves = sorted({(r["perfil"], r["anos"]) for r in registros})
    for perfil, anos in chaves:
        grupo = [r for r in registros if r["perfil"] == perfil and r["anos"] == anos]
        correlacoes = [r["spearman"] for r in grupo if r["spearman"] is not None]
        com_cdi = [r for r in grupo if r.get("cdi") is not None]
        resumo[f"perfil{perfil}_{anos}a"] = {
            "amostras": len(grupo),
            "periodo": f"{grupo[0]['data_base']} a {grupo[-1]['data_base']}",
            "retorno_escolhido_medio": statistics.fmean(r["retorno_escolhido"] for r in grupo),
            "retorno_top_medio": statistics.fmean(r["retorno_top3"] for r in grupo),
            "retorno_universo_medio": statistics.fmean(r["retorno_medio"] for r in grupo),
            "retorno_universo_mediano": statistics.fmean(r["retorno_mediano"] for r in grupo),
            "cdi_medio": statistics.fmean(r["cdi"] for r in com_cdi) if com_cdi else None,
            "escolhido_bateu_mediana": sum(
                r["retorno_escolhido"] >= r["retorno_mediano"] for r in grupo
            ) / len(grupo),
            "escolhido_bateu_cdi": (
                sum(r["retorno_escolhido"] >= r["cdi"] for r in com_cdi) / len(com_cdi)
                if com_cdi
                else None
            ),
            "spearman_medio": statistics.fmean(correlacoes) if correlacoes else None,
        }
    return resumo


# ── Parte 3: rankers de fundos e previdência (CVM) ─────────────────────────────

def _cotas_em(cnpjs: list[str], dia: str) -> dict[str, float]:
    """Última cota de cada fundo até ``dia`` no banco local da CVM."""
    from fundos.informe_diario_coletor import get_informe_coletor

    conexao = get_informe_coletor().conn
    cotas: dict[str, float] = {}
    for i in range(0, len(cnpjs), 500):
        bloco = cnpjs[i:i + 500]
        marcadores = ",".join("?" for _ in bloco)
        consulta = f"""
            SELECT CNPJ_Classe, Valor_Cota FROM (
                SELECT CNPJ_Classe, Valor_Cota, ROW_NUMBER() OVER (
                    PARTITION BY CNPJ_Classe ORDER BY Data_Competencia DESC) AS rn
                FROM informe_diario
                WHERE CNPJ_Classe IN ({marcadores}) AND Data_Competencia <= ?
                  AND Data_Competencia >= date(?, '-10 days')
            ) WHERE rn = 1
        """
        for cnpj, cota in conexao.execute(consulta, [*bloco, dia, dia]):
            if cota and cota > 0:
                cotas[cnpj] = float(cota)
    return cotas


def validar_fundos(previdencia: bool = False) -> dict[str, Any]:
    """Ranqueia fundos com dados até cada data de corte e mede os 12 meses seguintes.

    Usa o banco local da CVM (janela de 3 anos do app). Limitações: o
    cadastro é o atual, então fundos encerrados depois do corte não entram
    (viés de sobrevivência, que afeta igualmente escolhidos e universo).
    """
    import fundos.ranker_fundos as ranker_fundos
    import fundos.ranker_previdenciarios as ranker_prev
    from fundos import informe_diario_coletor as informe

    modulo = ranker_prev if previdencia else ranker_fundos
    originais = (modulo.listar_historicos, modulo.listar_metricas_agregadas)
    registros = []
    try:
        for corte in ("2025-01-31", "2025-05-30", "2025-09-30"):
            fim = (pd.Timestamp(corte) + pd.DateOffset(years=1)).strftime("%Y-%m-%d")
            modulo.listar_historicos = (
                lambda cnpjs, limite=252, _d=corte: informe.listar_historicos(cnpjs, limite, _d)
            )
            modulo.listar_metricas_agregadas = (
                lambda cnpjs, _d=corte: informe.listar_metricas_agregadas(cnpjs, _d)
            )
            cdi = cdi_realizado(pd.Timestamp(corte), pd.Timestamp(fim))
            for perfil in (1, 2, 3):
                if previdencia:
                    ranking = ranker_prev.RankerPrevidenciarios(perfil).gerar_ranking()
                else:
                    ranking = ranker_fundos.RankerFundos(
                        perfil, data_referencia=corte
                    ).gerar_ranking()
                cnpjs = [f["cnpj"] for f in ranking]
                inicio, final = _cotas_em(cnpjs, corte), _cotas_em(cnpjs, fim)
                validos = [
                    {**f, "retorno": final[f["cnpj"]] / inicio[f["cnpj"]] - 1}
                    for f in ranking
                    if f["cnpj"] in inicio and f["cnpj"] in final
                ]
                if len(validos) < 20:
                    continue
                validos.sort(key=lambda f: -f["score"])
                retornos = [f["retorno"] for f in validos]
                registros.append(
                    {
                        "data_base": corte,
                        "anos": 1,
                        "perfil": perfil,
                        "fundos": len(validos),
                        "escolhido": validos[0].get("nome"),
                        "retorno_escolhido": validos[0]["retorno"],
                        "retorno_top3": statistics.fmean(f["retorno"] for f in validos[:3]),
                        "retorno_top10": statistics.fmean(f["retorno"] for f in validos[:10]),
                        "retorno_medio": statistics.fmean(retornos),
                        "retorno_mediano": statistics.median(retornos),
                        "melhor_possivel": max(retornos),
                        "cdi": cdi - 1 if cdi else None,
                        "spearman": _spearman([f["score"] for f in validos], retornos),
                    }
                )
                print(f"   {('prev' if previdencia else 'fundos')} {corte} perfil {perfil}: {len(validos)} fundos", flush=True)
    finally:
        modulo.listar_historicos, modulo.listar_metricas_agregadas = originais
    resumo = _resumir_ranking(registros)
    for chave, item in resumo.items():
        perfil, anos = chave.split("_")
        grupo = [r for r in registros if f"perfil{r['perfil']}" == perfil]
        item["retorno_top10_medio"] = statistics.fmean(r["retorno_top10"] for r in grupo)
    return {"resumo": resumo, "registros": registros}


# ── Parte 4: ranking de ETFs de ações (Yahoo) ──────────────────────────────────

def historico_etfs() -> tuple[pd.DataFrame, pd.DataFrame, dict[str, str]]:
    """Fechamento ajustado e volume diários dos ETFs listados (BRAPI + Yahoo)."""
    from acoes_fiis.apis.brapi_tickers import listar_tickers

    ativos = listar_tickers()
    etfs = {s: str(i.get("name") or i.get("longName") or "") for s, i in ativos.items()
            if str(i.get("subType", "")).lower() == "etf"}

    def baixar() -> pd.DataFrame:
        import time

        import yfinance as yf

        partes = []
        simbolos = sorted(etfs)
        for i in range(0, len(simbolos), 40):
            bloco = [f"{s}.SA" for s in simbolos[i:i + 40]]
            dados = yf.download(bloco, period="7y", auto_adjust=True, progress=False, threads=False)
            partes.append(dados)
            time.sleep(5)
        return pd.concat(partes, axis=1)

    dados = _em_cache("etfs_historico", baixar)
    fechamento = dados["Close"].copy()
    volume = dados["Volume"].copy()
    for tabela in (fechamento, volume):
        tabela.columns = [c.replace(".SA", "") for c in tabela.columns]
        tabela.index = pd.to_datetime(tabela.index).tz_localize(None)
    return fechamento, volume, etfs


def _metricas_etf(precos: pd.Series, volumes: pd.Series) -> dict[str, float] | None:
    """Mesmas métricas de ``etfs.screener_etf.get_etf_data``, numa janela dada."""
    import numpy as np

    precos = precos.dropna()
    if len(precos) < 200:
        return None
    diarios = precos.pct_change().dropna()
    vol_anual = float(diarios.std()) * float(np.sqrt(252)) * 100
    medio_anual = (1 + float(diarios.mean())) ** 252 - 1
    return {
        "retorno_12m": (float(precos.iloc[-1]) / float(precos.iloc[0]) - 1) * 100,
        "volatilidade": vol_anual,
        "sharpe": (medio_anual - 0.05) / (vol_anual / 100) if vol_anual > 0 else 0.0,
        "volume": float((volumes.reindex(precos.index).fillna(0) * precos).mean()),
        "taxa": None,
        "preco": float(precos.iloc[-1]),
    }


def validar_etfs() -> dict[str, Any]:
    """Pontua ETFs de ações com os 12 meses anteriores e mede os 12 seguintes."""
    from etfs import screener_etf

    fechamento, volume, nomes = historico_etfs()
    hoje = pd.Timestamp(date.today())
    registros = []
    universos = []
    for dia in datas_base("2020-01-01", (hoje - pd.DateOffset(years=1)).strftime("%Y-%m-%d"), meses=3):
        fim = dia + pd.DateOffset(years=1)
        cdi = cdi_realizado(dia, fim)
        candidatos = []
        for ticker in fechamento.columns:
            janela = fechamento[ticker].loc[dia - pd.DateOffset(years=1):dia]
            metricas = _metricas_etf(janela, volume[ticker])
            if metricas is None or metricas["volume"] <= 0:
                continue
            if screener_etf.classe_etf(nomes.get(ticker), metricas["volatilidade"], ticker) != "acoes":
                continue
            saida = _valor_ate(fechamento[ticker].dropna(), fim)
            entrada = _valor_ate(fechamento[ticker].dropna(), dia)
            if not saida or not entrada:
                continue
            metricas["ticker"] = ticker
            metricas["retorno_realizado"] = saida / entrada - 1
            candidatos.append(metricas)
        if len(candidatos) < 8:
            continue
        universos.append(
            {
                "data_base": dia.date().isoformat(),
                "cdi": cdi - 1 if cdi else None,
                "etfs": [
                    {k: c[k] for k in ("ticker", "retorno_12m", "volatilidade", "sharpe", "volume", "retorno_realizado")}
                    for c in candidatos
                ],
            }
        )
        for perfil in (1, 2, 3):
            for c in candidatos:
                c["score"], _ = screener_etf._score_etf(c, perfil)
            ordem = sorted(candidatos, key=lambda c: -c["score"])
            retornos = [c["retorno_realizado"] for c in candidatos]
            registros.append(
                {
                    "data_base": dia.date().isoformat(),
                    "anos": 1,
                    "perfil": perfil,
                    "etfs": len(candidatos),
                    "escolhido": ordem[0]["ticker"],
                    "retorno_escolhido": ordem[0]["retorno_realizado"],
                    "retorno_top3": statistics.fmean(c["retorno_realizado"] for c in ordem[:3]),
                    "retorno_medio": statistics.fmean(retornos),
                    "retorno_mediano": statistics.median(retornos),
                    "melhor_possivel": max(retornos),
                    "cdi": cdi - 1 if cdi else None,
                    "spearman": _spearman([c["score"] for c in candidatos], retornos),
                }
            )
    return {"resumo": _resumir_ranking(registros), "registros": registros, "universos": universos}


# ── CLI ───────────────────────────────────────────────────────────────────────

PARTES: dict[str, Callable[[], dict[str, Any]]] = {
    "projecoes": validar_projecoes,
    "tesouro": validar_tesouro,
    "fundos": validar_fundos,
    "previdencia": lambda: validar_fundos(previdencia=True),
    "etfs": validar_etfs,
    "pesquisa_acoes": pesquisar_regra_acoes,
}


def main(argumentos: Iterable[str] | None = None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--partes", nargs="+", choices=sorted(PARTES), default=sorted(PARTES))
    args = parser.parse_args(list(argumentos) if argumentos is not None else None)

    resultados: dict[str, Any] = {
        "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if SAIDA_JSON.exists():
        anterior = json.loads(SAIDA_JSON.read_text(encoding="utf-8"))
        resultados = {**anterior, **resultados}
    for parte in args.partes:
        print(f"→ {parte}...", flush=True)
        resultados[parte] = PARTES[parte]()
    SAIDA_JSON.parent.mkdir(parents=True, exist_ok=True)
    SAIDA_JSON.write_text(
        json.dumps(resultados, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(f"Resultados em {SAIDA_JSON}")
    return resultados


if __name__ == "__main__":
    main()
