# fundos/ranker_fundos.py
"""
Ranker de Fundos de Investimento, por perfil (conservador/moderado/agressivo).

Pipeline em 3 estágios, do mais barato para o mais caro:

1. INTERSEÇÃO  — só considera fundos com cadastro ativo E dados no Informe
   Diário (fundos.intersecao).
2. PRÉ-FILTRO QUALITATIVO — usa métricas agregadas calculadas via SQL
   (fundos.informe_diario_coletor.listar_metricas_agregadas) e o
   fundos.filtros.FiltroFundos para descartar, por perfil, fundos fora de
   categoria, com PL/histórico/cotistas insuficientes, restritos, etc.
   Isso reduz a lista de ~25 mil fundos para dezenas/centenas de candidatos
   ANTES de qualquer cálculo pesado.
3. CÁLCULO COMPLETO — só para os candidatos que sobraram, busca o histórico
   diário (listar_historicos) e calcula retorno, volatilidade, drawdown,
   Sharpe e Sortino, then aplica o score ponderado por perfil.
"""

import datetime as dt
import logging

import pandas as pd

from core.ranking_liquido import avaliar_fundo_liquido, combinar_scores

from .filtros import filtrar_para_ranking
from .indicadores import calcular_indicadores_df
from .informe_diario_coletor import listar_historicos, listar_metricas_agregadas
from .intersecao import carregar_interseccao_dataframe
from .sharpe_sortino import (
    calcular_indicadores_risco,
    obter_taxa_livre_risco,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------
# Configurações
# ---------------------------------------------------------------------

PERFIL_CONSERVADOR = 1
PERFIL_MODERADO = 2
PERFIL_AGRESSIVO = 3

DIAS_ANO = 252

# ---------------------------------------------------------------------
# Pesos base (sem Sharpe/Sortino)
# ---------------------------------------------------------------------

PESOS_BASE = {
    PERFIL_CONSERVADOR: {
        "retorno_12m": 0.20,
        "volatilidade": 0.35,
        "drawdown": 0.25,
        "fluxo": 0.10,
        "patrimonio": 0.10,
    },
    PERFIL_MODERADO: {
        "retorno_12m": 0.35,
        "volatilidade": 0.25,
        "drawdown": 0.15,
        "fluxo": 0.15,
        "patrimonio": 0.10,
    },
    PERFIL_AGRESSIVO: {
        "retorno_12m": 0.50,
        "volatilidade": 0.10,
        "drawdown": 0.10,
        "fluxo": 0.20,
        "patrimonio": 0.10,
    },
}

# Pesos para Sharpe e Sortino (opcionais)
PESO_SHARPE = 0.10
PESO_SORTINO = 0.10


# ---------------------------------------------------------------------
# Normalizações
# ---------------------------------------------------------------------

def _numero(valor):
    try:
        if valor is None:
            return 0.0
        return float(valor)
    except (TypeError, ValueError):
        return 0.0


def _limitar(valor, minimo, maximo):
    return max(minimo, min(valor, maximo))


def _score_retorno(retorno):
    if retorno is None:
        return 0.0
    retorno = _numero(retorno)
    score = ((retorno + 0.50) / 1.00) * 10
    return _limitar(score, 0, 10)


def _score_volatilidade(volatilidade):
    if volatilidade is None:
        return 0.0
    volatilidade = _numero(volatilidade)
    score = 10 - (volatilidade * 20)
    return _limitar(score, 0, 10)


def _score_drawdown(drawdown):
    if drawdown is None:
        return 0.0
    drawdown = abs(_numero(drawdown))
    score = 10 - (drawdown * 20)
    return _limitar(score, 0, 10)


def _score_fluxo(fluxo, patrimonio):
    if fluxo is None or patrimonio is None or patrimonio == 0:
        return 0.0
    fluxo = _numero(fluxo)
    patrimonio = _numero(patrimonio)
    proporcao = fluxo / patrimonio
    score = 5 + (proporcao * 10)
    return _limitar(score, 0, 10)


def _score_patrimonio(patrimonio):
    if patrimonio is None:
        return 0.0
    patrimonio = _numero(patrimonio)
    if patrimonio <= 0:
        return 0
    if patrimonio >= 10_000_000_000:
        return 10
    if patrimonio >= 5_000_000_000:
        return 9
    if patrimonio >= 1_000_000_000:
        return 8
    if patrimonio >= 500_000_000:
        return 7
    if patrimonio >= 100_000_000:
        return 6
    return 5


def _score_sharpe(sharpe):
    if sharpe is None:
        return 0.0
    sharpe = _numero(sharpe)
    score = (sharpe / 2) * 10
    return _limitar(score, 0, 10)


def _score_sortino(sortino):
    if sortino is None:
        return 0.0
    sortino = _numero(sortino)
    score = (sortino / 2) * 10
    return _limitar(score, 0, 10)


# ---------------------------------------------------------------------
# Score unificado
# ---------------------------------------------------------------------

def _data_referencia(valor):
    if valor is None:
        return dt.datetime.now(dt.UTC).date()
    if isinstance(valor, dt.date):
        return valor
    if isinstance(valor, str):
        try:
            return dt.date.fromisoformat(valor)
        except ValueError as exc:
            raise ValueError(
                "data_referencia deve estar no formato AAAA-MM-DD."
            ) from exc
    raise TypeError("data_referencia deve ser date, texto ISO ou None.")


def calcular_score(
    indicadores,
    perfil,
    incluir_sharpe_sortino=True,
    *,
    prazo_anos=None,
    data_referencia=None,
    retorno_esperado_anual=None,
):
    """
    Calcula o score de um fundo com base nos indicadores e perfil.
    """
    pesos = PESOS_BASE[perfil].copy()

    # Se incluir Sharpe/Sortino, redistribui os pesos
    if incluir_sharpe_sortino:
        fator_restante = 1 - (PESO_SHARPE + PESO_SORTINO)  # 0.80
        soma_base = sum(pesos.values())
        for chave in pesos:
            pesos[chave] = (pesos[chave] / soma_base) * fator_restante
        pesos["sharpe"] = PESO_SHARPE
        pesos["sortino"] = PESO_SORTINO

    # Calcula os scores individuais
    scores = {
        "retorno": _score_retorno(indicadores.get("retorno_12m")),
        "volatilidade": _score_volatilidade(indicadores.get("volatilidade")),
        "drawdown": _score_drawdown(indicadores.get("drawdown")),
        "fluxo": _score_fluxo(
            indicadores.get("fluxo_liquido"),
            indicadores.get("patrimonio_atual"),
        ),
        "patrimonio": _score_patrimonio(indicadores.get("patrimonio_atual")),
    }

    if incluir_sharpe_sortino:
        scores["sharpe"] = _score_sharpe(indicadores.get("sharpe"))
        scores["sortino"] = _score_sortino(indicadores.get("sortino"))

    # Calcula o score ponderado
    score_total = 0.0
    for chave, peso in pesos.items():
        if chave == "retorno_12m":
            chave_score = "retorno"
        elif chave == "sharpe":
            chave_score = "sharpe"
        elif chave == "sortino":
            chave_score = "sortino"
        else:
            chave_score = chave
        score_total += scores.get(chave_score, 0) * peso

    score_adequacao = round(score_total, 2)
    resultado = {
        "score": score_adequacao,
        "retorno": round(scores["retorno"], 2),
        "volatilidade": round(scores["volatilidade"], 2),
        "drawdown": round(scores["drawdown"], 2),
        "fluxo": round(scores["fluxo"], 2),
        "patrimonio": round(scores["patrimonio"], 2),
    }
    if incluir_sharpe_sortino:
        resultado["sharpe"] = round(scores["sharpe"], 2)
        resultado["sortino"] = round(scores["sortino"], 2)

    if prazo_anos is not None:
        eficiencia = avaliar_fundo_liquido(
            indicadores,
            prazo_anos=prazo_anos,
            data_referencia=_data_referencia(data_referencia),
            retorno_esperado_anual=retorno_esperado_anual,
        )
        resultado["eficiencia_liquida"] = eficiencia
        resultado["score_adequacao"] = score_adequacao
        if eficiencia["aplicado"]:
            score_liquido = _score_retorno(
                eficiencia["retorno_liquido_anual"]
            )
            resultado["score_eficiencia_liquida"] = round(
                score_liquido,
                2,
            )
            resultado["score"] = combinar_scores(
                score_adequacao,
                score_liquido,
            )

    return resultado


# ---------------------------------------------------------------------
# Ranker principal (interseção -> pré-filtro -> cálculo completo)
# ---------------------------------------------------------------------

class RankerFundos:
    def __init__(
        self,
        perfil=PERFIL_MODERADO,
        incluir_sharpe_sortino=True,
        *,
        prazo_anos=None,
        data_referencia=None,
        retorno_esperado_anual=None,
        **filtro_kwargs,
    ):
        """
        Args:
            perfil: 1=Conservador, 2=Moderado, 3=Agressivo
            incluir_sharpe_sortino: se True, calcula Sharpe/Sortino (precisa
                do CDI do período — ver fundos.sharpe_sortino)
            **filtro_kwargs: repassado para fundos.filtros.FiltroFundos
                (ex.: esg=True, permitir_restrito=True, pl_global_minimo=...)
        """
        self.perfil = perfil
        self.incluir_sharpe_sortino = incluir_sharpe_sortino
        self.prazo_anos = prazo_anos
        self.data_referencia = data_referencia
        self.retorno_esperado_anual = retorno_esperado_anual
        self.filtro_kwargs = filtro_kwargs
        self._ranking = None  # Cache do ranking

    def _obter_ranking(self):
        """Retorna o ranking, calculando apenas uma vez."""
        if self._ranking is None:
            self._ranking = self._gerar_ranking()
        return self._ranking

    def limpar_cache(self):
        """Força o recálculo do ranking na próxima chamada."""
        self._ranking = None

    def _gerar_ranking(self):
        """Executa o cálculo do ranking (chamado apenas quando necessário)."""

        # -----------------------------------------------------------
        # ESTÁGIO 1: interseção (cadastro ativo + tem dado no informe)
        # -----------------------------------------------------------
        df_cad = carregar_interseccao_dataframe()
        if df_cad.empty:
            logger.warning("Interseção vazia — nenhum fundo com cadastro e informe ao mesmo tempo.")
            return []

        cnpjs = df_cad["CNPJ_Classe"].tolist()
        logger.info(f"Interseção: {len(cnpjs)} fundos candidatos.")

        # -----------------------------------------------------------
        # ESTÁGIO 2: pré-filtro qualitativo (métricas agregadas via SQL,
        # sem carregar histórico diário linha a linha para todo mundo)
        # -----------------------------------------------------------
        df_metricas = listar_metricas_agregadas(cnpjs)
        if df_metricas.empty:
            logger.warning("Não foi possível calcular métricas agregadas.")
            return []

        df_filtrado = filtrar_para_ranking(
            df_cad,
            df_metricas=df_metricas,
            perfil=self.perfil,
            **self.filtro_kwargs,
        )
        if df_filtrado.empty:
            logger.warning(f"Nenhum fundo passou no pré-filtro (perfil {self.perfil}).")
            return []

        cnpjs_filtrados = df_filtrado["CNPJ_Classe"].tolist()
        logger.info(
            f"Pré-filtro (perfil {self.perfil}): {len(cnpjs)} -> {len(cnpjs_filtrados)} "
            f"fundos vão para o cálculo completo (Sharpe/Sortino)."
        )

        # -----------------------------------------------------------
        # ESTÁGIO 3: cálculo completo — histórico diário só dos
        # candidatos que sobraram, indicadores, Sharpe/Sortino e score
        # -----------------------------------------------------------
        df_hist = listar_historicos(cnpjs_filtrados, limite=DIAS_ANO * 2)
        if df_hist.empty:
            logger.warning("Nenhum histórico diário encontrado para os fundos filtrados.")
            return []

        ranking = []
        taxa_livre_risco = None
        incluir_risco_no_score = False
        if self.incluir_sharpe_sortino:
            taxa_livre_risco = obter_taxa_livre_risco(
                df_hist["Data_Competencia"]
            )
            incluir_risco_no_score = taxa_livre_risco is not None
            if not incluir_risco_no_score:
                logger.warning(
                    "CDI indisponível; ranking seguirá sem Sharpe/Sortino."
                )

        for cnpj, group in df_hist.groupby("CNPJ_Classe"):
            cad_row = df_filtrado[df_filtrado["CNPJ_Classe"] == cnpj]
            if cad_row.empty:
                continue

            indicadores = calcular_indicadores_df(group, cad_row.iloc[0].to_dict())
            if indicadores is None or indicadores.get("cagr") is None:
                continue

            if self.incluir_sharpe_sortino:
                risco = calcular_indicadores_risco(
                    group["Valor_Cota"],
                    pd.to_datetime(group["Data_Competencia"]),
                    taxa_livre_risco=taxa_livre_risco,
                )
                indicadores["sharpe"] = risco.get("sharpe")
                indicadores["sortino"] = risco.get("sortino")

            score = calcular_score(
                indicadores,
                self.perfil,
                incluir_sharpe_sortino=incluir_risco_no_score,
                prazo_anos=self.prazo_anos,
                data_referencia=self.data_referencia,
                retorno_esperado_anual=self.retorno_esperado_anual,
            )

            item = {
                "cnpj": cnpj,
                "nome": indicadores.get("nome"),
                "classe": indicadores.get("classe"),
                "tipo": indicadores.get("tipo"),
                "score": score["score"],
                "subscores": {
                    k: v
                    for k, v in score.items()
                    if k not in {"score", "eficiencia_liquida"}
                },
                "indicadores": indicadores,
            }
            if "eficiencia_liquida" in score:
                item["eficiencia_liquida"] = score["eficiencia_liquida"]
            ranking.append(item)

        ranking.sort(key=lambda x: x["score"], reverse=True)
        logger.info(f"Ranking final: {len(ranking)} fundos com score calculado.")
        return ranking

    # -------------------------------------------------------------
    # Métodos públicos (usam o cache)
    # -------------------------------------------------------------

    def gerar_ranking(self):
        """Retorna o ranking completo (com cache)."""
        return self._obter_ranking()

    def top(self, quantidade=20):
        ranking = self._obter_ranking()
        return ranking[:quantidade]

    def buscar_cnpj(self, cnpj):
        ranking = self._obter_ranking()
        cnpj = str(cnpj).replace(".", "").replace("/", "").replace("-", "").zfill(14)
        for fundo in ranking:
            if fundo["cnpj"] == cnpj:
                return fundo
        return None

    def buscar_nome(self, texto):
        ranking = self._obter_ranking()
        texto = texto.upper()
        return [f for f in ranking if f.get("nome") and texto in f["nome"].upper()]

    def por_classe(self, classe):
        ranking = self._obter_ranking()
        classe = classe.upper()
        return [f for f in ranking if f.get("classe") and classe in f["classe"].upper()]

    def estatisticas(self):
        ranking = self._obter_ranking()
        if not ranking:
            return {}
        scores = [f["score"] for f in ranking]
        return {
            "fundos": len(ranking),
            "score_medio": round(sum(scores) / len(scores), 2),
            "score_maximo": max(scores),
            "score_minimo": min(scores),
        }


# ---------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------

def gerar_ranking(
    perfil=PERFIL_MODERADO,
    incluir_sharpe_sortino=True,
    *,
    prazo_anos=None,
    data_referencia=None,
    retorno_esperado_anual=None,
    **filtro_kwargs,
):
    return RankerFundos(
        perfil,
        incluir_sharpe_sortino,
        prazo_anos=prazo_anos,
        data_referencia=data_referencia,
        retorno_esperado_anual=retorno_esperado_anual,
        **filtro_kwargs,
    ).gerar_ranking()


def top_fundos(
    quantidade=20,
    perfil=PERFIL_MODERADO,
    incluir_sharpe_sortino=True,
    *,
    prazo_anos=None,
    data_referencia=None,
    retorno_esperado_anual=None,
    **filtro_kwargs,
):
    return RankerFundos(
        perfil,
        incluir_sharpe_sortino,
        prazo_anos=prazo_anos,
        data_referencia=data_referencia,
        retorno_esperado_anual=retorno_esperado_anual,
        **filtro_kwargs,
    ).top(quantidade)


def rankear_fundos(
    perfil=PERFIL_MODERADO,
    limite=10,
    incluir_sharpe_sortino=True,
    *,
    prazo_anos=None,
    data_referencia=None,
    retorno_esperado_anual=None,
    **filtro_kwargs,
):
    """
    Função principal para o recomendador.
    """
    ranking = RankerFundos(
        perfil,
        incluir_sharpe_sortino,
        prazo_anos=prazo_anos,
        data_referencia=data_referencia,
        retorno_esperado_anual=retorno_esperado_anual,
        **filtro_kwargs,
    ).gerar_ranking()
    return ranking[:limite]


def buscar_fundo_cnpj(cnpj, perfil=PERFIL_MODERADO, incluir_sharpe_sortino=True):
    return RankerFundos(perfil, incluir_sharpe_sortino).buscar_cnpj(cnpj)


def buscar_fundo_nome(nome, perfil=PERFIL_MODERADO, incluir_sharpe_sortino=True):
    return RankerFundos(perfil, incluir_sharpe_sortino).buscar_nome(nome)


def fundos_por_classe(classe, perfil=PERFIL_MODERADO, incluir_sharpe_sortino=True):
    return RankerFundos(perfil, incluir_sharpe_sortino).por_classe(classe)


# ---------------------------------------------------------------------
# Teste
# ---------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")

    ranking = top_fundos(quantidade=10, perfil=PERFIL_MODERADO, incluir_sharpe_sortino=True)

    print("\n" + "=" * 100)
    print("TOP 10 FUNDOS (interseção -> pré-filtro -> Sharpe/Sortino)")
    print("=" * 100)

    for pos, fundo in enumerate(ranking, start=1):
        print(f"\n{pos:02d}º")
        print(f"Nome  : {fundo['nome']}")
        print(f"Classe: {fundo['classe']}")
        print(f"Score : {fundo['score']:.2f}")
        print("Subscores:")
        for chave, valor in fundo["subscores"].items():
            print(f"   {chave:15}: {valor:.2f}")

    print("\n" + "=" * 100)
