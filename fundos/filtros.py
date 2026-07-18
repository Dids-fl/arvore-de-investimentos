# fundos/filtros.py
"""
Módulo de filtros qualitativos para Fundos de Investimento.

Aplica filtros antes do ranking para eliminar fundos que não fazem sentido
para cada perfil de investidor, melhorando qualidade e performance.

NOTA: O mapeamento de classes ANBIMA depende das nomenclaturas atuais.
      Caso a ANBIMA introduza novas descrições, este mapeamento deve ser revisado.
"""

import logging
from typing import Optional, Dict, Any, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------
# Mapeamento de classes ANBIMA para categorias internas
# NOTA: A ordem das chaves é importante para correspondência de substring.
#       Chaves mais específicas devem vir primeiro para evitar conflitos.
# ---------------------------------------------------------------------

CATEGORIAS_ANBIMA = {
    # Renda Fixa (mais específicas primeiro)
    "Renda Fixa Duração Alta Grau de Investimento": "RENDA_FIXA",
    "Renda Fixa Duração Baixa Grau de Investimento": "RENDA_FIXA",
    "Renda Fixa Duração": "RENDA_FIXA",
    "Renda Fixa": "RENDA_FIXA",
    "Referenciado DI": "RENDA_FIXA",
    "Referenciado": "RENDA_FIXA",
    "DI": "RENDA_FIXA",
    "Inflação": "RENDA_FIXA",
    "Curto Prazo": "RENDA_FIXA",
    "Soberano": "RENDA_FIXA",
    "Crédito Privado High Grade": "RENDA_FIXA",
    "Credito Privado High Grade": "RENDA_FIXA",
    "Crédito Privado Grau de Investimento": "RENDA_FIXA",
    "Credito Privado Grau de Investimento": "RENDA_FIXA",
    "Crédito Privado": "RENDA_FIXA",
    # Multimercado
    "Multimercado Long Short": "MULTIMERCADO",
    "Multimercado Macro": "MULTIMERCADO",
    "Multimercado Estratégia Livre": "MULTIMERCADO",
    "Multimercado Estratégia": "MULTIMERCADO",
    "Multimercado": "MULTIMERCADO",
    "Long Short": "MULTIMERCADO",
    "Balanceado": "MULTIMERCADO",
    # Ações
    "Ações Livre": "ACOES",
    "Ações Indexado": "ACOES",
    "Ações Small Caps": "ACOES",
    "Ações Valor": "ACOES",
    "Ações Growth": "ACOES",
    "Ações Dividendos": "ACOES",
    "Ações Setorial": "ACOES",
    "Ações": "ACOES",
    "Índice": "ACOES",
    "Setorial": "ACOES",
    "Valor": "ACOES",
    "Growth": "ACOES",
    "Dividendos": "ACOES",
    "Small Caps": "ACOES",
    # Outros
    "Cambial": "CAMBIAL",
    "Commodities": "COMMODITIES",
    "Alavancado": "ALAVANCADO",
    "Cripto": "CRIPTO",
    "Event Driven": "EVENT_DRIVEN",
}

# Ordem de prioridade para classificação (mais específicas primeiro)
_ORDEM_CLASSIFICACAO = sorted(
    CATEGORIAS_ANBIMA.keys(),
    key=len,
    reverse=True,
)


def _classificar_fundo(classe_anbima: str) -> str:
    """
    Mapeia a classe ANBIMA para uma categoria interna.
    Retorna 'OUTROS' se não encontrar correspondência.
    """
    if pd.isna(classe_anbima):
        return "OUTROS"
    classe = str(classe_anbima).strip()
    for chave in _ORDEM_CLASSIFICACAO:
        if chave.lower() in classe.lower():
            return CATEGORIAS_ANBIMA[chave]
    return "OUTROS"


# ---------------------------------------------------------------------
# Configurações centralizadas (evita duplicação)
# ---------------------------------------------------------------------

# Limites por categoria
# Fundos não classificados (OUTROS) são excluídos, não recebem limites padrão
PL_MINIMO_POR_CATEGORIA = {
    "RENDA_FIXA": 10_000_000,      # R$ 10M
    "MULTIMERCADO": 50_000_000,    # R$ 50M
    "ACOES": 100_000_000,          # R$ 100M
    "CAMBIAL": 50_000_000,         # R$ 50M
    "COMMODITIES": 100_000_000,    # R$ 100M
    "ALAVANCADO": 200_000_000,     # R$ 200M
    "EVENT_DRIVEN": 200_000_000,   # R$ 200M
    "CRIPTO": 50_000_000,          # R$ 50M
}

DIAS_MINIMOS_POR_CATEGORIA = {
    "RENDA_FIXA": 252,        # 1 ano
    "MULTIMERCADO": 504,      # 2 anos
    "ACOES": 504,             # 2 anos
    "CAMBIAL": 252,           # 1 ano
    "COMMODITIES": 252,       # 1 ano
    "ALAVANCADO": 504,        # 2 anos
    "EVENT_DRIVEN": 504,      # 2 anos
    "CRIPTO": 126,            # 6 meses
}

COTISTAS_MINIMOS_POR_CATEGORIA = {
    "RENDA_FIXA": 20,
    "MULTIMERCADO": 50,
    "ACOES": 100,
    "CAMBIAL": 50,
    "COMMODITIES": 50,
    "ALAVANCADO": 100,
    "EVENT_DRIVEN": 100,
    "CRIPTO": 20,
}

# Público-alvo restrito
PUBLICO_RESTRITO = {"Exclusivo", "Restrito", "Profissionais", "Qualificados"}


# ---------------------------------------------------------------------
# Configurações por perfil
# ---------------------------------------------------------------------

# Categorias permitidas por perfil
CATEGORIAS_PERMITIDAS = {
    1: {  # Conservador
        "RENDA_FIXA",
    },
    2: {  # Moderado
        "RENDA_FIXA",
        "MULTIMERCADO",
        "ACOES",
    },
    3: {  # Agressivo
        "RENDA_FIXA",
        "MULTIMERCADO",
        "ACOES",
        "CAMBIAL",
        "COMMODITIES",
        "ALAVANCADO",
        "EVENT_DRIVEN",
        "CRIPTO",
    },
}

# Categorias explicitamente excluídas por perfil
CATEGORIAS_EXCLUIDAS = {
    1: {"ALAVANCADO", "CRIPTO", "CAMBIAL", "COMMODITIES", "EVENT_DRIVEN"},
    2: {"ALAVANCADO", "CRIPTO", "EVENT_DRIVEN"},
    3: set(),
}


# ---------------------------------------------------------------------
# Classe principal
# ---------------------------------------------------------------------

class FiltroFundos:
    """
    Aplica filtros qualitativos ao cadastro de fundos.

    Uso (caminho eficiente, recomendado para milhares de fundos):
        filtro = FiltroFundos(perfil=2)
        df_filtrado = filtro.aplicar(df_cadastro, df_metricas=df_metricas_agregadas)

    Uso (caminho antigo, recebe o informe diário bruto linha a linha):
        filtro = FiltroFundos(perfil=2)
        df_filtrado = filtro.aplicar(df_cadastro, df_informe=df_informe_diario)
    """

    def __init__(self, perfil: int = 2, **kwargs):
        """
        Inicializa o filtro com configurações.

        Args:
            perfil: 1=Conservador, 2=Moderado, 3=Agressivo
            **kwargs: Parâmetros opcionais:
                - permitir_restrito (bool): Permitir fundos restritos?
                - esg (bool): Apenas fundos ESG?
                - pl_global_minimo (float): PL mínimo global (sobrescreve categoria)
                - cotistas_global_minimo (int): Cotistas mínimo global
        """
        self.perfil = perfil
        self.categorias_permitidas = CATEGORIAS_PERMITIDAS.get(perfil, set())
        self.categorias_excluidas = CATEGORIAS_EXCLUIDAS.get(perfil, set())

        self.permitir_restrito = kwargs.get("permitir_restrito", False)
        self.esg = kwargs.get("esg", False)
        self.pl_global_minimo = kwargs.get("pl_global_minimo", 0)
        self.cotistas_global_minimo = kwargs.get("cotistas_global_minimo", 0)

    # -------------------------------------------------------------
    # Pré-cálculo de métricas auxiliares
    # -------------------------------------------------------------

    @staticmethod
    def _preparar_metricas(
        df_cadastro: pd.DataFrame,
        df_informe: Optional[pd.DataFrame] = None,
        df_metricas: Optional[pd.DataFrame] = None,
    ) -> pd.DataFrame:
        """
        Adiciona colunas auxiliares ao cadastro para acelerar filtros.

        Dois caminhos possíveis:
        - df_metricas: DataFrame JÁ AGREGADO por CNPJ (ex.: saída de
          informe_diario_coletor.listar_metricas_agregadas), com colunas
          Dias_Historico, Ultimo_Cotistas, Proporcao_Resgate e,
          opcionalmente, Patrimonio_Liquido. Caminho RÁPIDO — recomendado
          quando há milhares de fundos, pois evita carregar linha a linha
          o histórico diário em memória.
        - df_informe: histórico diário BRUTO (uma linha por fundo por dia).
          Caminho antigo, mais pesado, mantido por compatibilidade.
        """
        df = df_cadastro.copy()

        # 1. Categoria (calculada uma única vez, vetorizada)
        df["Categoria"] = df["Classificacao_Anbima"].apply(_classificar_fundo)

        if df_metricas is not None and not df_metricas.empty:
            # Caminho rápido: métricas já vieram agregadas (via SQL)
            metricas = df_metricas.set_index("CNPJ_Classe")

            df["Dias_Historico"] = (
                df["CNPJ_Classe"].map(metricas["Dias_Historico"]).fillna(0)
            )
            df["Ultimo_Cotistas"] = (
                df["CNPJ_Classe"].map(metricas["Ultimo_Cotistas"]).fillna(0)
            )
            df["Proporcao_Resgate"] = (
                df["CNPJ_Classe"].map(metricas["Proporcao_Resgate"]).fillna(0)
            )

            # Se o PL mais recente do informe estiver disponível, ele é mais
            # atual que o valor estático do cadastro — usamos preferencialmente.
            if "Patrimonio_Liquido" in metricas.columns:
                pl_informe = df["CNPJ_Classe"].map(metricas["Patrimonio_Liquido"])
                if "Patrimonio_Liquido" in df.columns:
                    df["Patrimonio_Liquido"] = pl_informe.fillna(df["Patrimonio_Liquido"])
                else:
                    df["Patrimonio_Liquido"] = pl_informe.fillna(0)

        elif df_informe is not None and not df_informe.empty:
            # Caminho antigo: recebe o informe diário bruto e agrega em pandas
            dias_por_fundo = df_informe.groupby("CNPJ_Classe")["Data_Competencia"].nunique()
            df["Dias_Historico"] = df["CNPJ_Classe"].map(dias_por_fundo).fillna(0)

            cotistas_por_fundo = (
                df_informe
                .sort_values("Data_Competencia")
                .groupby("CNPJ_Classe")["Numero_Cotistas"]
                .last()
            )
            df["Ultimo_Cotistas"] = df["CNPJ_Classe"].map(cotistas_por_fundo).fillna(0)

            grupo_resgate = df_informe.groupby("CNPJ_Classe").agg({
                "Resgate_Dia": "sum",
                "Patrimonio_Liquido": "mean",
            }).reset_index()
            grupo_resgate["Proporcao_Resgate"] = (
                grupo_resgate["Resgate_Dia"] / (grupo_resgate["Patrimonio_Liquido"] + 1e-9)
            )
            df["Proporcao_Resgate"] = df["CNPJ_Classe"].map(
                grupo_resgate.set_index("CNPJ_Classe")["Proporcao_Resgate"]
            ).fillna(0)

        else:
            df["Dias_Historico"] = 0
            df["Ultimo_Cotistas"] = 0
            df["Proporcao_Resgate"] = 0

        return df

    # -------------------------------------------------------------
    # Filtros individuais (vetorizados)
    # -------------------------------------------------------------

    def filtrar_situacao(self, df: pd.DataFrame) -> pd.DataFrame:
        """Mantém apenas fundos com situação normal."""
        if "Situacao" not in df.columns:
            return df
        mascara = df["Situacao"].str.upper() == "EM FUNCIONAMENTO NORMAL"
        removidos = len(df) - mascara.sum()
        if removidos:
            logger.info(f"Filtro situação: removidos {removidos} fundos.")
        return df[mascara].copy()

    def filtrar_por_categoria(self, df: pd.DataFrame) -> pd.DataFrame:
        """Filtra fundos por categoria permitida."""
        if not self.categorias_permitidas and not self.categorias_excluidas:
            return df

        mascara = pd.Series(True, index=df.index)
        if self.categorias_excluidas:
            mascara &= ~df["Categoria"].isin(self.categorias_excluidas)
        if self.categorias_permitidas:
            mascara &= df["Categoria"].isin(self.categorias_permitidas)

        removidos = len(df) - mascara.sum()
        if removidos:
            logger.info(f"Filtro por categoria (perfil {self.perfil}): removidos {removidos} fundos.")
        return df[mascara].copy()

    def filtrar_outros(self, df: pd.DataFrame) -> pd.DataFrame:
        """Remove fundos não classificados (OUTROS)."""
        mascara = df["Categoria"] != "OUTROS"
        removidos = len(df) - mascara.sum()
        if removidos:
            logger.info(f"Filtro OUTROS: removidos {removidos} fundos não classificados.")
        return df[mascara].copy()

    def filtrar_patrimonio_minimo(self, df: pd.DataFrame) -> pd.DataFrame:
        """Filtra por patrimônio mínimo por categoria."""
        if "Patrimonio_Liquido" not in df.columns:
            return df

        # Mapeamento vetorizado direto via dicionário (sem função por linha).
        # Categorias sem entrada no dicionário caem em +inf (reprovam sempre),
        # e o piso global é aplicado com clip, também vetorizado.
        pl_minimos = df["Categoria"].map(PL_MINIMO_POR_CATEGORIA).fillna(float("inf"))
        df["PL_Minimo"] = pl_minimos.clip(lower=self.pl_global_minimo)

        mascara = df["Patrimonio_Liquido"] >= df["PL_Minimo"]
        removidos = len(df) - mascara.sum()
        if removidos:
            logger.info(f"Filtro patrimônio mínimo: removidos {removidos} fundos.")
        return df[mascara].copy()

    def filtrar_historico_minimo(self, df: pd.DataFrame) -> pd.DataFrame:
        """Filtra por histórico mínimo (em dias) por categoria."""
        if "Dias_Historico" not in df.columns:
            return df

        df["Dias_Minimo"] = df["Categoria"].map(DIAS_MINIMOS_POR_CATEGORIA).fillna(float("inf"))
        mascara = df["Dias_Historico"] >= df["Dias_Minimo"]
        removidos = len(df) - mascara.sum()
        if removidos:
            logger.info(f"Filtro histórico mínimo: removidos {removidos} fundos.")
        return df[mascara].copy()

    def filtrar_cotistas_minimo(self, df: pd.DataFrame) -> pd.DataFrame:
        """Filtra por número mínimo de cotistas por categoria."""
        if "Ultimo_Cotistas" not in df.columns:
            return df

        # Mesmo padrão vetorizado usado em filtrar_patrimonio_minimo.
        cotistas_minimos = df["Categoria"].map(COTISTAS_MINIMOS_POR_CATEGORIA).fillna(float("inf"))
        df["Cotistas_Minimo"] = cotistas_minimos.clip(lower=self.cotistas_global_minimo)

        mascara = df["Ultimo_Cotistas"] >= df["Cotistas_Minimo"]
        removidos = len(df) - mascara.sum()
        if removidos:
            logger.info(f"Filtro cotistas mínimo: removidos {removidos} fundos.")
        return df[mascara].copy()

    def filtrar_publico_alvo(self, df: pd.DataFrame) -> pd.DataFrame:
        """Remove fundos com público-alvo restrito."""
        if self.permitir_restrito:
            return df
        if "Publico_Alvo" not in df.columns:
            return df

        df["Publico_Alvo"] = df["Publico_Alvo"].astype(str).str.strip()
        mascara = ~df["Publico_Alvo"].isin(PUBLICO_RESTRITO)
        removidos = len(df) - mascara.sum()
        if removidos:
            logger.info(f"Filtro público-alvo: removidos {removidos} fundos restritos.")
        return df[mascara].copy()

    def filtrar_esg(self, df: pd.DataFrame) -> pd.DataFrame:
        """Filtra fundos ESG."""
        if not self.esg:
            return df
        if "Classe_ESG" not in df.columns:
            return df

        mascara = df["Classe_ESG"].astype(str).str.upper().isin(["SIM", "S", "1", "TRUE"])
        removidos = len(df) - mascara.sum()
        if removidos:
            logger.info(f"Filtro ESG: removidos {removidos} fundos não-ESG.")
        return df[mascara].copy()

    # -------------------------------------------------------------
    # Método principal
    # -------------------------------------------------------------

    def aplicar(
        self,
        df_cadastro: pd.DataFrame,
        df_informe: Optional[pd.DataFrame] = None,
        df_metricas: Optional[pd.DataFrame] = None,
    ) -> pd.DataFrame:
        """
        Aplica todos os filtros ao cadastro de fundos.

        Passe df_metricas (métricas já agregadas via SQL — ver
        informe_diario_coletor.listar_metricas_agregadas) sempre que possível:
        é muito mais rápido que passar df_informe bruto para milhares de fundos.

        Returns:
            DataFrame com fundos que passaram em todos os filtros.
        """
        if df_cadastro.empty:
            return df_cadastro

        logger.info(f"Aplicando filtros (perfil {self.perfil})...")
        total_inicial = len(df_cadastro)

        # Pré-calcula métricas auxiliares
        df_filtrado = self._preparar_metricas(df_cadastro, df_informe=df_informe, df_metricas=df_metricas)

        # 1. Remove não classificados (OUTROS) logo após o pré-processamento,
        #    para não gastar cálculo de PL/histórico/cotistas com fundos
        #    que serão descartados de qualquer forma.
        df_filtrado = self.filtrar_outros(df_filtrado)

        # 2. Situação
        df_filtrado = self.filtrar_situacao(df_filtrado)

        # 3. Categoria (perfil)
        df_filtrado = self.filtrar_por_categoria(df_filtrado)

        # 4. Patrimônio mínimo
        df_filtrado = self.filtrar_patrimonio_minimo(df_filtrado)

        # 5. Histórico mínimo
        df_filtrado = self.filtrar_historico_minimo(df_filtrado)

        # 6. Cotistas mínimo
        df_filtrado = self.filtrar_cotistas_minimo(df_filtrado)

        # 7. Público-alvo
        df_filtrado = self.filtrar_publico_alvo(df_filtrado)

        # 8. ESG
        df_filtrado = self.filtrar_esg(df_filtrado)

        total_final = len(df_filtrado)
        removidos = total_inicial - total_final

        logger.info(f"Filtros aplicados: {total_inicial} -> {total_final} fundos ({removidos} removidos).")

        # Remove colunas auxiliares antes de retornar
        cols_aux = {"Categoria", "Dias_Historico", "Ultimo_Cotistas", "Proporcao_Resgate",
                    "PL_Minimo", "Dias_Minimo", "Cotistas_Minimo"}
        for col in cols_aux:
            if col in df_filtrado.columns:
                df_filtrado = df_filtrado.drop(columns=[col])

        return df_filtrado


# ---------------------------------------------------------------------
# Função de conveniência
# ---------------------------------------------------------------------

def filtrar_para_ranking(
    df_cadastro: pd.DataFrame,
    df_informe: Optional[pd.DataFrame] = None,
    df_metricas: Optional[pd.DataFrame] = None,
    perfil: int = 2,
    **kwargs,
) -> pd.DataFrame:
    """
    Função de alto nível para aplicar filtros antes do ranking.

    Prefira passar df_metricas (agregado via SQL) em vez de df_informe
    (bruto) quando estiver filtrando milhares de fundos de uma vez.
    """
    filtro = FiltroFundos(perfil=perfil, **kwargs)
    return filtro.aplicar(df_cadastro, df_informe=df_informe, df_metricas=df_metricas)
