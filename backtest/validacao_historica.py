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
        proximo = min(atual + pd.DateOffset(years=5) - pd.Timedelta(1, unit="D"), fim_dt)
        df = sgs.get({"v": codigo}, start=atual.strftime("%Y-%m-%d"), end=proximo.strftime("%Y-%m-%d"))
        if not df.empty:
            blocos.append(df["v"])
        atual = proximo + pd.Timedelta(1, unit="D")
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
    if janela.empty or cdi.index.max() < fim - pd.Timedelta(7, unit="D"):
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


SALTO_DIARIO_MAXIMO = 0.35


def _serie_confiavel(serie: pd.Series, inicio: pd.Timestamp, fim: pd.Timestamp) -> bool:
    """Falso se houver salto diário impossível (desdobramento não ajustado).

    O Yahoo às vezes não ajusta desdobramentos e grupamentos de FIIs e ETFs,
    o que cria "retornos" de centenas de por cento em um dia.
    """
    janela = serie.loc[inicio - pd.Timedelta(5, unit="D"):fim].dropna()
    if len(janela) < 2:
        return False
    return bool((janela.pct_change().abs().dropna() <= SALTO_DIARIO_MAXIMO).all())


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
    ipca12 = _valor_ate(serie_ipca_12m(), dia - pd.Timedelta(40, unit="D"))
    if selic is None or ipca12 is None:
        return None
    ibov_cagr = None
    ibov_vol = None
    if incluir_ibov:
        ibov = serie_yahoo("^BVSP")
        inicio_10a = dia - pd.DateOffset(years=10)
        ibov_ini = _valor_ate(ibov, inicio_10a)
        ibov_fim = _valor_ate(ibov, dia)
        if not ibov_ini or not ibov_fim or ibov.index.min() > inicio_10a + pd.Timedelta(10, unit="D"):
            return None
        ibov_cagr = _anualizar(ibov_fim / ibov_ini, 10)
        from macroeconomia.premio_acoes import volatilidade_anual

        ibov_vol = volatilidade_anual(ibov, dia)

    def focus_por_ano(indicador: str) -> dict[int, float]:
        focus = focus_anual(indicador)
        ate = focus.loc[(focus["Data"] <= dia) & (focus["Data"] > dia - pd.Timedelta(45, unit="D"))]
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
    return [pd.bdate_range(d, d + pd.Timedelta(7, unit="D"))[0] for d in datas]


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
            if fim > hoje - pd.Timedelta(10, unit="D"):
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
            if fim > hoje - pd.Timedelta(10, unit="D"):
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
            if fim > hoje - pd.Timedelta(10, unit="D"):
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

BANCO_INFORME_ANTIGO = CACHE_DIR / "informe_diario_antigo.db"
URL_INFORME_MENSAL = "https://dados.cvm.gov.br/dados/FI/DOC/INF_DIARIO/DADOS/inf_diario_fi_{ano}{mes:02d}.zip"
_COLETOR_COMBINADO: dict[str, Any] = {}


def coletor_informe_combinado():
    """Coletor do informe diário com o histórico do app mais meses antigos.

    O app guarda só 3 anos. Para ter mais datas de corte, os meses de 2021
    até o início da janela do app são baixados (arquivos mensais gratuitos da
    CVM) para um banco separado, usado só aqui. Uma visão temporária une os
    dois bancos, então as consultas do próprio coletor funcionam sem mudança.
    """
    if "coletor" in _COLETOR_COMBINADO:
        return _COLETOR_COMBINADO["coletor"]
    import io
    import zipfile

    import requests

    from fundos.informe_diario_coletor import DB_PATH, InformeDiarioColetorCVM

    atual = InformeDiarioColetorCVM(atualizar=False)
    primeiro = atual.conn.execute("SELECT MIN(Data_Competencia) FROM informe_diario").fetchone()[0]
    limite = pd.Timestamp(primeiro).to_period("M")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    antigo = InformeDiarioColetorCVM(db_path=BANCO_INFORME_ANTIGO, atualizar=False)
    for periodo in pd.period_range("2021-01", limite - 1, freq="M"):
        if antigo.mes_ja_carregado(periodo.year, periodo.month):
            continue
        url = URL_INFORME_MENSAL.format(ano=periodo.year, mes=periodo.month)
        resposta = requests.get(url, timeout=300)
        resposta.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(resposta.content)) as arquivo:
            nome = next(n for n in arquivo.namelist() if n.endswith(".csv"))
            with arquivo.open(nome) as csv:
                for pedaco in pd.read_csv(csv, sep=";", encoding="latin1", low_memory=False, chunksize=100_000):
                    antigo._processar_chunk(pedaco)
        print(f"   informe {periodo} carregado", flush=True)
    antigo.conn.execute(f"ATTACH DATABASE '{Path(DB_PATH).resolve()}' AS atual")
    antigo.conn.execute(
        "CREATE TEMP VIEW informe_diario AS "
        "SELECT * FROM main.informe_diario UNION ALL SELECT * FROM atual.informe_diario"
    )
    _COLETOR_COMBINADO["coletor"] = antigo
    return antigo


def _cotas_em(cnpjs: list[str], dia: str) -> dict[str, float]:
    """Última cota de cada fundo até ``dia`` (banco do app + meses antigos)."""
    conexao = coletor_informe_combinado().conn
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


# Nove cortes a cada 4 meses; cada um usa até 2 anos de histórico anterior.
CORTES_FUNDOS = (
    "2023-01-31", "2023-05-31", "2023-09-29",
    "2024-01-31", "2024-05-31", "2024-09-30",
    "2025-01-31", "2025-05-30", "2025-09-30",
)


def validar_fundos(previdencia: bool = False) -> dict[str, Any]:
    """Ranqueia fundos com dados até cada data de corte e mede os 12 meses seguintes.

    Usa o banco local da CVM mais os meses antigos de
    ``coletor_informe_combinado``. Limitações: o cadastro é o atual, então fundos encerrados depois do corte não entram
    (viés de sobrevivência, que afeta igualmente escolhidos e universo).
    """
    import fundos.ranker_fundos as ranker_fundos
    import fundos.ranker_previdenciarios as ranker_prev

    modulo = ranker_prev if previdencia else ranker_fundos
    informe = coletor_informe_combinado()
    originais = (modulo.listar_historicos, modulo.listar_metricas_agregadas)
    registros = []
    try:
        for corte in CORTES_FUNDOS:
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
            if not _serie_confiavel(fechamento[ticker], dia - pd.DateOffset(years=1), fim):
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


# ── Parte 5: ranking de FIIs (CVM + Yahoo) ─────────────────────────────────────

URL_FII_MENSAL = "https://dados.cvm.gov.br/dados/FII/DOC/INF_MENSAL/DADOS/inf_mensal_fii_{ano}.zip"


def informes_fii() -> pd.DataFrame:
    """Informe mensal de todos os FIIs (CVM): valor patrimonial e DY por cota."""
    def baixar() -> pd.DataFrame:
        import io
        import zipfile

        import requests

        partes = []
        for ano in range(2019, date.today().year + 1):
            resposta = requests.get(URL_FII_MENSAL.format(ano=ano), timeout=120)
            if resposta.status_code != 200:
                continue
            with zipfile.ZipFile(io.BytesIO(resposta.content)) as arquivo:
                nomes = arquivo.namelist()
                ler = lambda parte: pd.read_csv(  # noqa: E731
                    arquivo.open(next(n for n in nomes if parte in n)), sep=";", encoding="latin1"
                )
                complemento = ler("complemento")
                geral = ler("geral")
            # Até 2024 a coluna se chamava CNPJ_Fundo.
            for tabela in (complemento, geral):
                tabela.rename(columns={"CNPJ_Fundo": "CNPJ_Fundo_Classe"}, inplace=True)
            chaves = ["CNPJ_Fundo_Classe", "Data_Referencia"]
            dados = complemento[chaves + ["Valor_Patrimonial_Cotas", "Percentual_Dividend_Yield_Mes"]].merge(
                geral[chaves + ["Codigo_ISIN", "Mercado_Negociacao_Bolsa"]], on=chaves
            )
            partes.append(dados)
        tudo = pd.concat(partes, ignore_index=True)
        tudo = tudo.loc[tudo["Codigo_ISIN"].astype(str).str.match(r"^BR[A-Z]{4}CTF")]
        tudo["ticker"] = tudo["Codigo_ISIN"].str[2:6] + "11"
        tudo["Data_Referencia"] = pd.to_datetime(tudo["Data_Referencia"])
        return tudo.sort_values("Data_Referencia").drop_duplicates(["ticker", "Data_Referencia"], keep="last")

    return _em_cache("fii_informes", baixar)


def precos_fii(tickers: list[str]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Fechamento, fechamento ajustado (retorno total) e volume diários."""
    def baixar() -> pd.DataFrame:
        import time

        import yfinance as yf

        partes = []
        for i in range(0, len(tickers), 40):
            bloco = [f"{t}.SA" for t in tickers[i:i + 40]]
            partes.append(
                yf.download(bloco, period="7y", auto_adjust=False, progress=False, threads=False)
            )
            time.sleep(5)
        return pd.concat(partes, axis=1)

    dados = _em_cache("fii_precos", baixar)
    tabelas = []
    for campo in ("Close", "Adj Close", "Volume"):
        tabela = dados[campo].copy()
        tabela.columns = [c.replace(".SA", "") for c in tabela.columns]
        tabela.index = pd.to_datetime(tabela.index).tz_localize(None)
        tabelas.append(tabela)
    return tabelas[0], tabelas[1], tabelas[2]


def _indicadores_fii(ticker, dia, informes, fechamento, volume) -> dict | None:
    """DY 12 meses sobre o preço, P/VP e liquidez como estariam em ``dia``.

    O informe do mês M é entregue até o fim do mês M+1, então só entram os
    informes com referência pelo menos 45 dias antes de ``dia``.
    """
    preco = _valor_ate(fechamento[ticker].dropna(), dia)
    if not preco or preco <= 0:
        return None
    publicados = informes.loc[
        (informes["Data_Referencia"] <= dia - pd.Timedelta(45, unit="D"))
        & (informes["Data_Referencia"] > dia - pd.Timedelta(45 + 366, unit="D"))
    ]
    if len(publicados) < 10:
        return None
    vp = float(publicados["Valor_Patrimonial_Cotas"].iloc[-1])
    distribuido = float(
        (publicados["Percentual_Dividend_Yield_Mes"].fillna(0) * publicados["Valor_Patrimonial_Cotas"]).sum()
    )
    janela = fechamento[ticker].loc[dia - pd.Timedelta(62, unit="D"):dia].dropna()
    vol = volume[ticker].reindex(janela.index).fillna(0)
    if vp <= 0 or janela.empty:
        return None
    return {
        "ticker": ticker,
        "tipo_ativo": "fii",
        "dy": distribuido / preco * 100,
        "pvp": preco / vp,
        "liquidez": float((janela * vol).mean()),
        "vacancia": None,
    }


def validar_fiis() -> dict[str, Any]:
    """Pontua FIIs com os dados de cada data e mede o retorno total de 12 meses.

    A vacância (15% do score) não tem série mensal gratuita simples e fica
    fora; o peso dela é redistribuído entre DY, P/VP e liquidez.
    """
    from acoes_fiis import screener
    from acoes_fiis.ativos import MIN_LIQUIDEZ_FIIS

    informes = informes_fii()
    informes = informes.loc[informes["Mercado_Negociacao_Bolsa"].astype(str).str.upper() == "S"]
    tickers = sorted(informes["ticker"].unique())
    fechamento, ajustado, volume = precos_fii(tickers)
    por_ticker = {t: g for t, g in informes.groupby("ticker")}
    hoje = pd.Timestamp(date.today())
    registros, universos = [], []
    for dia in datas_base("2020-07-01", (hoje - pd.DateOffset(years=1)).strftime("%Y-%m-%d"), meses=3):
        fim = dia + pd.DateOffset(years=1)
        cdi = cdi_realizado(dia, fim)
        candidatos = []
        for ticker in fechamento.columns:
            if ticker not in por_ticker:
                continue
            ind = _indicadores_fii(ticker, dia, por_ticker[ticker], fechamento, volume)
            if ind is None or ind["liquidez"] < MIN_LIQUIDEZ_FIIS:
                continue
            if not _serie_confiavel(ajustado[ticker], dia - pd.DateOffset(years=1), fim):
                continue
            entrada = _valor_ate(ajustado[ticker].dropna(), dia)
            saida = _valor_ate(ajustado[ticker].dropna(), fim)
            if not entrada or not saida:
                continue
            ind["retorno_realizado"] = saida / entrada - 1
            candidatos.append(ind)
        candidatos = [c for c in screener._validar_fiis(candidatos) if c["dy"] <= 30]
        if len(candidatos) < 20:
            continue
        universos.append(
            {
                "data_base": dia.date().isoformat(),
                "cdi": cdi - 1 if cdi else None,
                "fiis": [
                    {k: c[k] for k in ("ticker", "dy", "pvp", "liquidez", "retorno_realizado")}
                    for c in candidatos
                ],
            }
        )
        dy_mediana = statistics.median(c["dy"] for c in candidatos)
        for perfil in (1, 2, 3):
            for c in candidatos:
                c["score"], _ = screener._score_fii(c, perfil, dy_mediana)
            ordem = sorted(candidatos, key=lambda c: -c["score"])
            retornos = [c["retorno_realizado"] for c in candidatos]
            registros.append(
                {
                    "data_base": dia.date().isoformat(),
                    "anos": 1,
                    "perfil": perfil,
                    "fiis": len(candidatos),
                    "escolhido": ordem[0]["ticker"],
                    "retorno_escolhido": ordem[0]["retorno_realizado"],
                    "retorno_top3": statistics.fmean(c["retorno_realizado"] for c in ordem[:3]),
                    "retorno_top10": statistics.fmean(c["retorno_realizado"] for c in ordem[:10]),
                    "retorno_medio": statistics.fmean(retornos),
                    "retorno_mediano": statistics.median(retornos),
                    "melhor_possivel": max(retornos),
                    "cdi": cdi - 1 if cdi else None,
                    "spearman": _spearman([c["score"] for c in candidatos], retornos),
                }
            )
    return {"resumo": _resumir_ranking(registros), "registros": registros, "universos": universos}


# ── Parte 7: ranking de ações (CVM + Yahoo) ────────────────────────────────────

URL_DFP = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/DADOS/dfp_cia_aberta_{ano}.zip"
URL_FCA = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/FCA/DADOS/fca_cia_aberta_{ano}.zip"
URL_FRE = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/FRE/DADOS/fre_cia_aberta_{ano}.zip"


def acoes_emitidas() -> pd.DataFrame:
    """Quantidade de ações integralizadas por empresa e ano (Formulário de Referência)."""
    def baixar() -> pd.DataFrame:
        import io
        import zipfile

        import requests

        partes = []
        for ano in range(2011, date.today().year + 1):
            resposta = requests.get(URL_FRE.format(ano=ano), timeout=300)
            if resposta.status_code != 200:
                continue
            with zipfile.ZipFile(io.BytesIO(resposta.content)) as arquivo:
                capital = pd.read_csv(
                    arquivo.open(f"fre_cia_aberta_capital_social_{ano}.csv"), sep=";", encoding="latin1"
                )
            capital = capital.loc[capital["Tipo_Capital"].astype(str) == "Capital Integralizado"]
            capital = capital.sort_values("Versao").groupby("CNPJ_Companhia")["Quantidade_Total_Acoes"].last()
            partes.append(pd.DataFrame({"CNPJ_CIA": capital.index, "acoes": capital.values, "ano_fre": ano}))
        return pd.concat(partes, ignore_index=True)

    return _em_cache("acoes_emitidas_fre", baixar)


def _conta(tabela: pd.DataFrame, prefixo: str, padrao: str) -> pd.Series:
    """Valor (em R$) da conta de 2º nível cujo nome casa com ``padrao``, por CNPJ."""
    linhas = tabela.loc[
        (tabela["ORDEM_EXERC"].astype(str).str.upper().str.startswith("ÚLTIMO"))
        & tabela["CD_CONTA"].astype(str).str.fullmatch(prefixo + r"\.\d{2}")
        & tabela["DS_CONTA"].astype(str).str.contains(padrao, case=False, regex=True)
    ].copy()
    escala = linhas["ESCALA_MOEDA"].astype(str).str.upper().map({"MIL": 1_000.0}).fillna(1.0)
    linhas["valor"] = linhas["VL_CONTA"].astype(float) * escala
    linhas = linhas.sort_values(["CNPJ_CIA", "VERSAO", "CD_CONTA"])
    return linhas.groupby("CNPJ_CIA")["valor"].last()


def fundamentos_acoes() -> pd.DataFrame:
    """Lucro líquido, patrimônio e número de ações por empresa e ano (DFP da CVM)."""
    def baixar() -> pd.DataFrame:
        import io
        import zipfile

        import requests

        partes = []
        for ano in range(2011, date.today().year):
            resposta = requests.get(URL_DFP.format(ano=ano), timeout=300)
            if resposta.status_code != 200:
                continue
            with zipfile.ZipFile(io.BytesIO(resposta.content)) as arquivo:
                ler = lambda parte: pd.read_csv(  # noqa: E731
                    arquivo.open(f"dfp_cia_aberta_{parte}_{ano}.csv"), sep=";", encoding="latin1"
                )
                dre, bpp = ler("DRE_con"), ler("BPP_con")
            lucro = _conta(dre, "3", r"lucro.*(?:l[ií]quido|preju[ií]zo)|preju[ií]zo.*l[ií]quido")
            patrimonio = _conta(bpp, "2", r"^patrim[oô]nio l[ií]quido")
            tabela = pd.DataFrame({"lucro": lucro, "patrimonio": patrimonio}).dropna()
            tabela["ano"] = ano
            partes.append(tabela.reset_index(names="CNPJ_CIA"))
            print(f"   DFP {ano}: {len(tabela)} empresas", flush=True)
        balancos = pd.concat(partes, ignore_index=True)
        # Ações do FRE do ano seguinte ao exercício (posição perto do fim do
        # exercício); se faltar, a do próprio ano.
        fre = acoes_emitidas()
        seguinte = fre.assign(ano=fre["ano_fre"] - 1)[["CNPJ_CIA", "ano", "acoes"]]
        mesmo = fre.assign(ano=fre["ano_fre"])[["CNPJ_CIA", "ano", "acoes"]]
        balancos = balancos.merge(seguinte, on=["CNPJ_CIA", "ano"], how="left")
        balancos = balancos.merge(mesmo, on=["CNPJ_CIA", "ano"], how="left", suffixes=("", "_mesmo"))
        balancos["acoes"] = balancos["acoes"].fillna(balancos["acoes_mesmo"])
        return balancos.drop(columns="acoes_mesmo").dropna(subset=["acoes"])

    return _em_cache("acoes_fundamentos_v2", baixar)


def tickers_acoes() -> pd.DataFrame:
    """Códigos de negociação (ON, PN, units) por CNPJ, de vários anos do FCA."""
    def baixar() -> pd.DataFrame:
        import io
        import zipfile

        import requests

        partes = []
        for ano in range(2016, date.today().year + 1):
            resposta = requests.get(URL_FCA.format(ano=ano), timeout=120)
            if resposta.status_code != 200:
                continue
            with zipfile.ZipFile(io.BytesIO(resposta.content)) as arquivo:
                vm = pd.read_csv(
                    arquivo.open(f"fca_cia_aberta_valor_mobiliario_{ano}.csv"), sep=";", encoding="latin1"
                )
            vm = vm.loc[
                (vm["Mercado"].astype(str) == "Bolsa")
                & vm["Valor_Mobiliario"].astype(str).str.contains("Ações|Units", regex=True)
            ]
            partes.append(vm[["CNPJ_Companhia", "Codigo_Negociacao"]])
        tudo = pd.concat(partes).dropna().drop_duplicates()
        tudo["Codigo_Negociacao"] = tudo["Codigo_Negociacao"].astype(str).str.strip().str.upper()
        return tudo.loc[tudo["Codigo_Negociacao"].str.fullmatch(r"[A-Z]{4}\d{1,2}")]

    return _em_cache("acoes_tickers", baixar)


def precos_acoes(tickers: list[str]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Fechamento, fechamento ajustado e volume diários (Yahoo), desde 2010."""
    def baixar() -> pd.DataFrame:
        import time

        import yfinance as yf

        partes = []
        for i in range(0, len(tickers), 40):
            bloco = [f"{t}.SA" for t in tickers[i:i + 40]]
            for tentativa in range(4):
                try:
                    dados = yf.download(
                        bloco, start="2010-01-01", auto_adjust=False, progress=False, threads=False
                    )
                    if not dados.empty:
                        partes.append(dados)
                        break
                except Exception as exc:  # noqa: BLE001
                    print(f"   Yahoo: {type(exc).__name__}, nova tentativa", flush=True)
                time.sleep(60 * (tentativa + 1))
            time.sleep(8)
            print(f"   preços {min(i + 40, len(tickers))}/{len(tickers)}", flush=True)
        return pd.concat(partes, axis=1)

    dados = _em_cache("acoes_precos", baixar)
    dados = _completar_precos(dados, tickers)
    tabelas = []
    for campo in ("Close", "Adj Close", "Volume"):
        tabela = dados[campo].copy()
        tabela.columns = [c.replace(".SA", "") for c in tabela.columns]
        tabela.index = pd.to_datetime(tabela.index).tz_localize(None)
        tabelas.append(tabela.loc[:, ~tabela.columns.duplicated()])
    return tabelas[0], tabelas[1], tabelas[2]


def _completar_precos(dados: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    """Baixa de novo, devagar, os tickers que falharam por limite do Yahoo."""
    import time

    import yfinance as yf

    arquivo = CACHE_DIR / "acoes_precos_complemento.pkl"
    complemento = pd.read_pickle(arquivo) if arquivo.exists() else pd.DataFrame()
    presentes = set()
    for tabela in (dados, complemento):
        if not tabela.empty:
            fechado = tabela["Close"]
            presentes |= {c.replace(".SA", "") for c in fechado.columns[fechado.notna().any()]}
    tentados_arquivo = CACHE_DIR / "acoes_precos_tentados.txt"
    tentados = set(tentados_arquivo.read_text().split()) if tentados_arquivo.exists() else set()
    faltando = [t for t in tickers if t not in presentes and t not in tentados]
    for i in range(0, len(faltando), 10):
        bloco = faltando[i:i + 10]
        try:
            novo = yf.download(
                [f"{t}.SA" for t in bloco], start="2010-01-01", auto_adjust=False, progress=False, threads=False
            )
        except Exception as exc:  # noqa: BLE001
            print(f"   Yahoo: {type(exc).__name__}; pausa", flush=True)
            time.sleep(120)
            continue
        if isinstance(novo.columns, pd.MultiIndex) and not novo.empty:
            complemento = novo if complemento.empty else pd.concat([complemento, novo], axis=1)
            pd.to_pickle(complemento, arquivo)
        tentados |= set(bloco)
        tentados_arquivo.write_text("\n".join(sorted(tentados)))
        time.sleep(15)
        print(f"   complemento {min(i + 10, len(faltando))}/{len(faltando)}", flush=True)
    if complemento.empty:
        return dados
    complemento = complemento.loc[:, ~complemento.columns.duplicated()]
    return pd.concat([dados, complemento], axis=1).loc[:, lambda d: ~d.columns.duplicated()]


def _ano_balanco_disponivel(dia: pd.Timestamp) -> int:
    """Último exercício cuja DFP já tinha sido entregue (prazo: 31 de março)."""
    return dia.year - 1 if dia.month >= 4 else dia.year - 2


def universo_acoes_em(dia, fundamentos, mapa, fechamento, ajustado, volume) -> list[dict]:
    """Indicadores de cada ação como estariam em ``dia`` (sem dado do futuro)."""
    ano = _ano_balanco_disponivel(dia)
    balanco = fundamentos.loc[fundamentos["ano"] == ano].set_index("CNPJ_CIA")
    universo = []
    for ticker, cnpj in mapa.items():
        if ticker not in fechamento.columns or cnpj not in balanco.index:
            continue
        linha = balanco.loc[cnpj]
        if isinstance(linha, pd.DataFrame):
            linha = linha.iloc[-1]
        preco = _valor_ate(fechamento[ticker].dropna(), dia)
        janela = fechamento[ticker].loc[dia - pd.Timedelta(62, unit="D"):dia].dropna()
        if not preco or preco <= 0 or janela.empty or linha["acoes"] <= 0 or linha["patrimonio"] <= 0:
            continue
        mcap = preco * float(linha["acoes"])
        lucro = float(linha["lucro"])
        ini_aj = _valor_ate(ajustado[ticker].dropna(), dia - pd.DateOffset(years=1))
        ini_px = _valor_ate(fechamento[ticker].dropna(), dia - pd.DateOffset(years=1))
        fim_aj = _valor_ate(ajustado[ticker].dropna(), dia)
        dy = 0.0
        if ini_aj and ini_px and fim_aj:
            dy = max(0.0, ((fim_aj / ini_aj) / (preco / ini_px) - 1) * 100)
        universo.append(
            {
                "ticker": ticker,
                "cnpj": cnpj,
                "cotacao": preco,
                "pl": mcap / lucro if lucro else 0.0,
                "pvp": mcap / float(linha["patrimonio"]),
                "roe": lucro / float(linha["patrimonio"]) * 100,
                "dy": dy,
                "liquidez": float((janela * volume[ticker].reindex(janela.index).fillna(0)).mean()),
                "mktcap_proxy": mcap,
                "dividendos_consistentes": False,
                "crescimento_receita": 0,
                "divida_patrimonio": 0,
            }
        )
    return universo


def validar_acoes() -> dict[str, Any]:
    """Aplica ``screener.ranquear_acoes`` em datas passadas e mede 12 meses à frente.

    Limitações: receita e dívida (pesos pequenos no score) ficam fora; o
    número de ações é o do balanço anual; empresas que deixaram de enviar
    DFP antes de 2011 não entram.
    """
    from acoes_fiis import screener
    from acoes_fiis.ativos import MIN_LIQUIDEZ_ACOES

    fundamentos = fundamentos_acoes()
    mapa_df = tickers_acoes()
    mapa = dict(zip(mapa_df["Codigo_Negociacao"], mapa_df["CNPJ_Companhia"]))
    fechamento, ajustado, volume = precos_acoes(sorted(mapa))
    ibov = serie_yahoo("^BVSP")
    hoje = pd.Timestamp(date.today())
    registros, universos = [], []
    for dia in datas_base("2013-01-01", (hoje - pd.DateOffset(years=1)).strftime("%Y-%m-%d")):
        fim = dia + pd.DateOffset(years=1)
        cdi = cdi_realizado(dia, fim)
        universo = universo_acoes_em(dia, fundamentos, mapa, fechamento, ajustado, volume)
        for acao in universo:
            serie = ajustado[acao["ticker"]]
            entrada, saida = _valor_ate(serie.dropna(), dia), _valor_ate(serie.dropna(), fim)
            confiavel = _serie_confiavel(serie, dia - pd.DateOffset(years=1), fim)
            acao["retorno_realizado"] = saida / entrada - 1 if (entrada and saida and confiavel) else None
        universo = [a for a in universo if a["retorno_realizado"] is not None]
        liquidos = [a for a in universo if a["liquidez"] >= MIN_LIQUIDEZ_ACOES]
        if len(liquidos) < 30:
            continue
        ibov_ret = _valor_ate(ibov, fim) / _valor_ate(ibov, dia) - 1
        universos.append(
            {
                "data_base": dia.date().isoformat(),
                "cdi": cdi - 1 if cdi else None,
                "ibov": ibov_ret,
                "acoes": [
                    {k: a[k] for k in ("ticker", "pl", "pvp", "roe", "dy", "liquidez", "mktcap_proxy", "retorno_realizado")}
                    for a in liquidos
                ],
            }
        )
        retornos = {a["ticker"]: a["retorno_realizado"] for a in liquidos}
        for perfil in (1, 2, 3):
            ranking = screener.ranquear_acoes([dict(a) for a in liquidos], perfil, n=10)
            if len(ranking) < 5:
                continue
            escolhidos = [retornos[a["ticker"]] for a in ranking]
            todos = list(retornos.values())
            registros.append(
                {
                    "data_base": dia.date().isoformat(),
                    "anos": 1,
                    "perfil": perfil,
                    "acoes": len(todos),
                    "escolhido": ranking[0]["ticker"],
                    "retorno_escolhido": escolhidos[0],
                    "retorno_top3": statistics.fmean(escolhidos[:3]),
                    "retorno_top10": statistics.fmean(escolhidos),
                    "retorno_medio": statistics.fmean(todos),
                    "retorno_mediano": statistics.median(todos),
                    "melhor_possivel": max(todos),
                    "cdi": cdi - 1 if cdi else None,
                    "ibov": ibov_ret,
                    "spearman": None,
                }
            )
        print(f"   ações {dia.date()}: {len(liquidos)} líquidas", flush=True)
    return {"resumo": _resumir_ranking(registros), "registros": registros, "universos": universos}


# ── Parte 6: carteiras recomendadas por perfil ─────────────────────────────────

INICIO_CARTEIRAS = "2008-01-01"


def _mensal(serie: pd.Series) -> pd.Series:
    return serie.dropna().resample("ME").last()


def indice_ipca_mais() -> pd.Series:
    """Índice diário de um Tesouro IPCA+ sem cupom com ~5 anos, rolado no vencimento.

    Usa o PU de mercado do próprio Tesouro: captura a marcação a mercado que
    um investidor em IPCA+ sentiria (semelhante ao IMA-B 5).
    """
    precos = historico_tesouro()
    ipca = precos.loc[precos["Tipo Titulo"] == "Tesouro IPCA+"].copy()
    ipca = ipca.loc[ipca["PU Base Manha"] > 0]
    tabela = ipca.pivot_table(index="Data Base", columns="Data Vencimento", values="PU Base Manha")
    datas = tabela.index.sort_values()
    nivel, valores, escolhido = 1.0, [], None
    for anterior, atual in zip(datas[:-1], datas[1:]):
        if escolhido is None or (escolhido - anterior).days < 365 * 2 or pd.isna(tabela.at[anterior, escolhido]):
            vivos = [v for v in tabela.columns if v > anterior + pd.DateOffset(years=3) and not pd.isna(tabela.at[anterior, v])]
            if not vivos:
                valores.append((atual, nivel))
                continue
            escolhido = min(vivos, key=lambda v: abs((v - anterior).days - 365 * 5))
        p0, p1 = tabela.at[anterior, escolhido], tabela.at[atual, escolhido]
        if pd.notna(p0) and pd.notna(p1) and p0 > 0 and abs(p1 / p0 - 1) < 0.2:
            nivel *= p1 / p0
        valores.append((atual, nivel))
    return pd.Series(dict(valores)).sort_index()


def indice_fii() -> pd.Series:
    """Média igual dos FIIs líquidos (retorno total), sem séries com desdobramento quebrado."""
    informes = informes_fii()
    tickers = sorted(informes["ticker"].unique())
    fechamento, ajustado, volume = precos_fii(tickers)
    retornos = ajustado.pct_change(fill_method=None)
    liquidez = (fechamento * volume).rolling(63, min_periods=20).mean().shift(1)
    elegivel = (liquidez >= 500_000) & (retornos.abs() <= SALTO_DIARIO_MAXIMO)
    media = retornos.where(elegivel).mean(axis=1)
    contagem = elegivel.sum(axis=1)
    media = media.where(contagem >= 20).dropna()
    return (1 + media).cumprod()


def proxies_mensais() -> pd.DataFrame:
    """Índices mensais que representam cada classe da carteira."""
    cdi = (1 + serie_cdi() / 100).cumprod()
    tabela = pd.DataFrame(
        {
            "cdi": _mensal(cdi),
            "ipca_mais": _mensal(indice_ipca_mais()),
            "ibov": _mensal(serie_yahoo("^BVSP")),
            "fii": _mensal(indice_fii()),
        }
    )
    for nome, ticker in (("usd", "USDBRL=X"), ("btc", "BTC-BRL")):
        try:
            tabela[nome] = _mensal(serie_yahoo(ticker))
        except Exception as exc:  # noqa: BLE001 — opcional
            print(f"   {ticker} indisponível: {exc}")
    return tabela.loc[INICIO_CARTEIRAS:]


# Cada categoria do app vira uma mistura das séries acima. Multimercado e
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
# Quando uma série não existe no início do período (FIIs antes de 2019,
# bitcoin antes de 2014), usa-se um substituto de risco parecido.
_SUBSTITUTO = {"fii": {"ipca_mais": 0.5, "ibov": 0.5}, "btc": {"ibov": 1}, "usd": {"cdi": 1}}


def simular_carteira(carteira: dict[str, float], proxies: pd.DataFrame) -> dict[str, Any]:
    """Carteira rebalanceada todo mês: retorno anual, pior queda e pior 12 meses."""
    retornos = proxies.pct_change(fill_method=None)
    total = pd.Series(0.0, index=retornos.index)
    for categoria, peso in carteira.items():
        mistura = PROXY_CATEGORIA.get(categoria, {"cdi": 1})
        for serie, fracao in mistura.items():
            r = retornos[serie] if serie in retornos else pd.Series(index=retornos.index, dtype=float)
            if r.isna().any():
                substituto = sum(retornos[s] * f for s, f in _SUBSTITUTO.get(serie, {"cdi": 1}).items())
                r = r.fillna(substituto)
            total += peso / 100 * fracao * r.fillna(0)
    total = total.iloc[1:]
    nivel = (1 + total).cumprod()
    queda = nivel / nivel.cummax() - 1
    doze = (1 + total).rolling(12).apply(lambda x: x.prod(), raw=True) - 1
    cdi12 = (1 + retornos["cdi"].iloc[1:]).rolling(12).apply(lambda x: x.prod(), raw=True) - 1
    anos = len(total) / 12
    return {
        "retorno_anual": float(nivel.iloc[-1] ** (1 / anos) - 1),
        "cdi_anual": float((1 + retornos["cdi"].iloc[1:]).prod() ** (1 / anos) - 1),
        "pior_queda": float(queda.min()),
        "pior_12m": float(doze.min()),
        "perdeu_dinheiro_12m": float((doze < 0).mean()),
        "perdeu_do_cdi_12m": float((doze < cdi12).mean()),
    }


def validar_carteiras(quantidade_perfis: int = 1500) -> dict[str, Any]:
    """Simula as carteiras que o app recomenda, desde 2008, por perfil.

    Os perfis são gerados como nos testes de invariantes; a carteira de cada
    um vem do próprio ``engine.criar_analise``.
    """
    import random

    import engine
    import mercado as modulo_mercado

    mercado = modulo_mercado.load_market_data()
    proxies = proxies_mensais()
    rng = random.Random(20261102)
    experiencias = sorted(set(engine._EXPERIENCIAS.values()))
    cache_sim: dict[tuple, dict] = {}
    registros = []
    for _ in range(quantidade_perfis):
        respostas = {campo: rng.choice(sorted(op)) for campo, op in engine.RESPOSTAS_MAP.items()}
        respostas.update(
            {
                "liquidez_pct": rng.choice([0, 10, 50]),
                "experiencia": rng.sample(experiencias, rng.randint(0, 3)),
                "cap_inicial": rng.choice([10_000, 100_000, 1_000_000]),
                "aporte_mensal": rng.choice([0, 1_000]),
                "despesas_essenciais_mensais": 4_000,
                "reserva_atual": rng.choice([0, 30_000, 200_000]),
                "modo_meta": "rendendo",
                "regime_previdencia": "regressivo",
            }
        )
        try:
            analise = engine.criar_analise(respostas, mercado, data_referencia=date.today())
        except (engine.DividaJurosAltosError, engine.RecomendacaoBloqueadaError):
            continue
        resultado = analise["resultado"]
        carteira = {k: float(v) for k, v in resultado["portfolio"].items() if float(v) > 0}
        chave = tuple(sorted(carteira.items()))
        if chave not in cache_sim:
            cache_sim[chave] = simular_carteira(carteira, proxies)
        registros.append(
            {
                "nivel_risco": resultado["nivel_risco_perfil"],
                "emocional": engine.RESPOSTAS_MAP["emocional"][respostas["emocional"]],
                "prazo": engine.RESPOSTAS_MAP["prazo"][respostas["prazo"]],
                "idade": engine.RESPOSTAS_MAP["idade"][respostas["idade"]],
                "renda": engine.RESPOSTAS_MAP["renda"][respostas["renda"]],
                "carteira": carteira,
                "taxa_projetada": resultado["taxa_perfil"],
                **cache_sim[chave],
            }
        )

    def resumir(grupo: list[dict]) -> dict[str, Any]:
        return {
            "perfis": len(grupo),
            "carteiras_distintas": len({tuple(sorted(r["carteira"].items())) for r in grupo}),
            "retorno_anual_medio": statistics.fmean(r["retorno_anual"] for r in grupo),
            "pior_queda_media": statistics.fmean(r["pior_queda"] for r in grupo),
            "pior_queda_extrema": min(r["pior_queda"] for r in grupo),
            "pior_12m_medio": statistics.fmean(r["pior_12m"] for r in grupo),
            "pior_12m_extremo": min(r["pior_12m"] for r in grupo),
            "perdeu_dinheiro_12m": statistics.fmean(r["perdeu_dinheiro_12m"] for r in grupo),
            "perdeu_do_cdi_12m": statistics.fmean(r["perdeu_do_cdi_12m"] for r in grupo),
        }

    resumo: dict[str, Any] = {"periodo": f"{proxies.index[1].date()} a {proxies.index[-1].date()}"}
    resumo["cdi_anual"] = registros[0]["cdi_anual"] if registros else None
    for nivel in (1, 2, 3):
        grupo = [r for r in registros if r["nivel_risco"] == nivel]
        if grupo:
            resumo[f"nivel_{nivel}"] = resumir(grupo)
    for emocional, rotulo in ((1, "venderia_tudo"), (2, "esperaria"), (3, "compraria_mais")):
        grupo = [r for r in registros if r["emocional"] == emocional]
        if grupo:
            resumo[f"emocional_{rotulo}"] = resumir(grupo)
    for prazo, rotulo in ((1, "curto"), (2, "medio"), (3, "longo")):
        grupo = [r for r in registros if r["prazo"] == prazo]
        if grupo:
            resumo[f"prazo_{rotulo}"] = resumir(grupo)
    piores = sorted(registros, key=lambda r: r["pior_queda"])[:15]
    return {"resumo": resumo, "piores": piores, "registros": registros[:300]}


# ── CLI ───────────────────────────────────────────────────────────────────────

PARTES: dict[str, Callable[[], dict[str, Any]]] = {
    "projecoes": validar_projecoes,
    "tesouro": validar_tesouro,
    "fundos": validar_fundos,
    "previdencia": lambda: validar_fundos(previdencia=True),
    "etfs": validar_etfs,
    "fiis": validar_fiis,
    "carteiras": validar_carteiras,
    "acoes": validar_acoes,
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
    novos = {}
    for parte in args.partes:
        print(f"→ {parte}...", flush=True)
        novos[parte] = PARTES[parte]()
    # Relê o arquivo só agora: outra execução pode ter gravado outras partes
    # enquanto esta rodava.
    if SAIDA_JSON.exists():
        resultados = {**json.loads(SAIDA_JSON.read_text(encoding="utf-8")), **resultados}
    resultados.update(novos)
    SAIDA_JSON.parent.mkdir(parents=True, exist_ok=True)
    SAIDA_JSON.write_text(
        json.dumps(resultados, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(f"Resultados em {SAIDA_JSON}")
    return resultados


if __name__ == "__main__":
    main()
