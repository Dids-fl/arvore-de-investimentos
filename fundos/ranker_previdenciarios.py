# fundos/ranker_previdenciarios.py
"""
Ranker de Fundos PREVIDENCIÁRIOS, por perfil (conservador/moderado/agressivo).

É um espelho de fundos/ranker_fundos.py: mesmo pipeline em 3 estágios,
mesmos pesos e mesma fórmula de score (reaproveitados diretamente de
ranker_fundos, para não duplicar a lógica). A única diferença é a fonte
dos candidatos no Estágio 1, que usa a interseção previdenciária
(cad_fi_previdenciario ∩ Informe Diário) em vez da interseção normal
(cad_fi ∩ Informe Diário).

1. INTERSEÇÃO — só considera fundos previdenciários com cadastro ativo E
   dados no Informe Diário (fundos.intersecao_previdenciaria).
2. PRÉ-FILTRO QUALITATIVO — mesmas métricas agregadas e mesmo
   fundos.filtros.FiltroFundos usado para fundos comuns.
3. CÁLCULO COMPLETO — mesmo cálculo de retorno, volatilidade, drawdown,
   Sharpe, Sortino e score ponderado por perfil.
"""

import logging

import pandas as pd

from .filtros import (
    COTISTAS_MINIMOS_POR_CATEGORIA_PREVIDENCIA,
    DIAS_MINIMOS_POR_CATEGORIA_PREVIDENCIA,
    PL_MINIMO_POR_CATEGORIA_PREVIDENCIA,
    filtrar_para_ranking,
)
from .indicadores import calcular_indicadores_df
from .informe_diario_coletor import listar_historicos, listar_metricas_agregadas
from .intersecao_previdenciaria import carregar_interseccao_previdenciaria_dataframe
from .ranker_fundos import (
    DIAS_ANO,
    PERFIL_AGRESSIVO,
    PERFIL_CONSERVADOR,
    PERFIL_MODERADO,
    calcular_score,
)
from .sharpe_sortino import calcular_indicadores_risco

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# Ranker principal (interseção previdenciária -> pré-filtro -> cálculo completo)
# ---------------------------------------------------------------------

class RankerPrevidenciarios:
    def __init__(self, perfil=PERFIL_MODERADO, incluir_sharpe_sortino=True, **filtro_kwargs):
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

        # Limiares de PL/histórico/cotistas calibrados para FIEs de
        # previdência (ver fundos/filtros.py). Usados como default, mas
        # o caller pode sobrescrever passando esses mesmos nomes em
        # filtro_kwargs (ex.: pl_minimo_por_categoria={...}).
        filtro_kwargs.setdefault(
            "pl_minimo_por_categoria", PL_MINIMO_POR_CATEGORIA_PREVIDENCIA
        )
        filtro_kwargs.setdefault(
            "dias_minimos_por_categoria", DIAS_MINIMOS_POR_CATEGORIA_PREVIDENCIA
        )
        filtro_kwargs.setdefault(
            "cotistas_minimos_por_categoria", COTISTAS_MINIMOS_POR_CATEGORIA_PREVIDENCIA
        )
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
        # ESTÁGIO 1: interseção previdenciária (cadastro previdenciário
        # ativo + tem dado no informe)
        # -----------------------------------------------------------
        df_cad = carregar_interseccao_previdenciaria_dataframe()
        if df_cad.empty:
            logger.warning(
                "Interseção previdenciária vazia — nenhum fundo previdenciário "
                "com cadastro e informe ao mesmo tempo."
            )
            return []

        cnpjs = df_cad["CNPJ_Classe"].tolist()
        logger.info(f"Interseção previdenciária: {len(cnpjs)} fundos candidatos.")

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
            logger.warning(f"Nenhum fundo previdenciário passou no pré-filtro (perfil {self.perfil}).")
            return []

        cnpjs_filtrados = df_filtrado["CNPJ_Classe"].tolist()
        logger.info(
            f"Pré-filtro previdenciário (perfil {self.perfil}): {len(cnpjs)} -> {len(cnpjs_filtrados)} "
            f"fundos vão para o cálculo completo (Sharpe/Sortino)."
        )

        # -----------------------------------------------------------
        # ESTÁGIO 3: cálculo completo — histórico diário só dos
        # candidatos que sobraram, indicadores, Sharpe/Sortino e score
        # -----------------------------------------------------------
        df_hist = listar_historicos(cnpjs_filtrados, limite=DIAS_ANO * 2)
        if df_hist.empty:
            logger.warning("Nenhum histórico diário encontrado para os fundos previdenciários filtrados.")
            return []

        ranking = []

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
                )
                indicadores["sharpe"] = risco.get("sharpe")
                indicadores["sortino"] = risco.get("sortino")

            score = calcular_score(
                indicadores,
                self.perfil,
                incluir_sharpe_sortino=self.incluir_sharpe_sortino,
            )

            ranking.append({
                "cnpj": cnpj,
                "nome": indicadores.get("nome"),
                "classe": indicadores.get("classe"),
                "tipo": indicadores.get("tipo"),
                "score": score["score"],
                "subscores": {k: v for k, v in score.items() if k != "score"},
                "indicadores": indicadores,
            })

        ranking.sort(key=lambda x: x["score"], reverse=True)
        logger.info(f"Ranking previdenciário final: {len(ranking)} fundos com score calculado.")
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

def gerar_ranking_previdenciario(perfil=PERFIL_MODERADO, incluir_sharpe_sortino=True, **filtro_kwargs):
    return RankerPrevidenciarios(perfil, incluir_sharpe_sortino, **filtro_kwargs).gerar_ranking()


def top_fundos_previdenciarios(quantidade=20, perfil=PERFIL_MODERADO, incluir_sharpe_sortino=True, **filtro_kwargs):
    return RankerPrevidenciarios(perfil, incluir_sharpe_sortino, **filtro_kwargs).top(quantidade)


def rankear_fundos_previdenciarios(perfil=PERFIL_MODERADO, limite=10, incluir_sharpe_sortino=True, **filtro_kwargs):
    """
    Função principal para o recomendador previdenciário.
    """
    ranking = RankerPrevidenciarios(perfil, incluir_sharpe_sortino, **filtro_kwargs).gerar_ranking()
    return ranking[:limite]


def buscar_fundo_previdenciario_cnpj(cnpj, perfil=PERFIL_MODERADO, incluir_sharpe_sortino=True):
    return RankerPrevidenciarios(perfil, incluir_sharpe_sortino).buscar_cnpj(cnpj)


def buscar_fundo_previdenciario_nome(nome, perfil=PERFIL_MODERADO, incluir_sharpe_sortino=True):
    return RankerPrevidenciarios(perfil, incluir_sharpe_sortino).buscar_nome(nome)


def fundos_previdenciarios_por_classe(classe, perfil=PERFIL_MODERADO, incluir_sharpe_sortino=True):
    return RankerPrevidenciarios(perfil, incluir_sharpe_sortino).por_classe(classe)


# ---------------------------------------------------------------------
# Teste
# ---------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")

    ranking = top_fundos_previdenciarios(quantidade=10, perfil=PERFIL_MODERADO, incluir_sharpe_sortino=True)

    print("\n" + "=" * 100)
    print("TOP 10 FUNDOS PREVIDENCIÁRIOS (interseção -> pré-filtro -> Sharpe/Sortino)")
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