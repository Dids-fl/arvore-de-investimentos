# fundos/indicadores.py
import logging
import pandas as pd
from .cadastro_coletor import buscar_por_cnpj
from .informe_diario_coletor import buscar_historico
from .utils import (
    retorno_periodo,
    retorno,
    cagr,
    volatilidade,
    drawdown,
)

logger = logging.getLogger(__name__)
DIAS_MES = 21
DIAS_ANO = 252


class IndicadoresFundos:
    def __init__(self, cnpj):
        self.cnpj = (
            str(cnpj)
            .replace(".", "")
            .replace("/", "")
            .replace("-", "")
            .zfill(14)
        )

        self.cadastro = buscar_por_cnpj(self.cnpj)
        self.df = buscar_historico(self.cnpj, limite=DIAS_ANO * 2)

        if self.df.empty:
            raise ValueError("Fundo não encontrado.")

        self.df = self.df.sort_values("Data_Competencia")

        colunas_numericas = [
            "Valor_Cota",
            "Patrimonio_Liquido",
            "Numero_Cotistas",
            "Captacao_Dia",
            "Resgate_Dia",
        ]
        for col in colunas_numericas:
            if col in self.df.columns:
                self.df[col] = (
                    pd.to_numeric(self.df[col], errors="coerce").fillna(0)
                )

        self.datas = pd.to_datetime(self.df["Data_Competencia"])
        self.cotas = self.df["Valor_Cota"]
        self.pl = self.df["Patrimonio_Liquido"]
        self.cotistas = self.df["Numero_Cotistas"]
        self.captacao = self.df["Captacao_Dia"]
        self.resgates = self.df["Resgate_Dia"]

    # ... (todos os métodos retorno_1m, etc., usando as funções de utils)

    def indicadores(self):
        return {
            "cnpj": self.cnpj,
            "nome": self.cadastro.get("Denominacao_Social") if self.cadastro else None,
            "classe": self.cadastro.get("Classificacao_Anbima") if self.cadastro else None,
            # ... etc.
        }


def calcular_indicadores(cnpj):
    return IndicadoresFundos(cnpj).indicadores()