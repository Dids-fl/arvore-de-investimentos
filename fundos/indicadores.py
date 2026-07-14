# fundos/indicadores.py

import logging
import math

import pandas as pd

from .cadastro_coletor import (
    buscar_por_cnpj,
)

from .informe_diario_coletor import (
    buscar_informe,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------
# Configurações
# ---------------------------------------------------------------------

DIAS_MES = 21
DIAS_ANO = 252

# ---------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------

def _to_float(valor):
    try:
        if valor is None:
            return 0.0
        if pd.isna(valor):
            return 0.0
        return float(valor)
    except Exception:
        return 0.0


def _serie_retorno(cotas):
    return cotas.pct_change().dropna()


def _retorno(cotas):
    if len(cotas) < 2:
        return 0.0
    inicial = _to_float(cotas.iloc[0])
    final = _to_float(cotas.iloc[-1])
    if inicial <= 0:
        return 0.0
    return (final / inicial) - 1


def _retorno_periodo(cotas, dias):
    if len(cotas) < dias + 1:
        return None
    serie = cotas.iloc[-(dias + 1):]
    return _retorno(serie)


def _cagr(cotas, datas):
    """
    Calcula o CAGR (Taxa de Crescimento Anual Composta) usando datas reais.
    """
    if len(cotas) < 2 or len(datas) < 2:
        return None

    dias_totais = (datas.iloc[-1] - datas.iloc[0]).days
    if dias_totais <= 0:
        return None

    anos = dias_totais / 365.25
    if anos <= 0:
        return None

    inicial = _to_float(cotas.iloc[0])
    final = _to_float(cotas.iloc[-1])
    if inicial <= 0:
        return None

    return (final / inicial) ** (1 / anos) - 1


# ---------------------------------------------------------------------
# Classe principal
# ---------------------------------------------------------------------

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
        self.df = buscar_informe(self.cnpj)

        if self.df.empty:
            raise ValueError("Fundo não encontrado.")

        self.df = self.df.sort_values("Data_Competencia")

        # Converter colunas para numérico
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

        # Converter datas uma única vez
        self.datas = pd.to_datetime(self.df["Data_Competencia"])

        self.cotas = self.df["Valor_Cota"]
        self.pl = self.df["Patrimonio_Liquido"]
        self.cotistas = self.df["Numero_Cotistas"]
        self.captacao = self.df["Captacao_Dia"]
        self.resgates = self.df["Resgate_Dia"]

    # -------------------------------------------------------------
    # Retornos
    # -------------------------------------------------------------

    def retorno_1m(self):
        return _retorno_periodo(self.cotas, DIAS_MES)

    def retorno_3m(self):
        return _retorno_periodo(self.cotas, DIAS_MES * 3)

    def retorno_6m(self):
        return _retorno_periodo(self.cotas, DIAS_MES * 6)

    def retorno_12m(self):
        return _retorno_periodo(self.cotas, DIAS_ANO)

    def retorno_total(self):
        return _retorno(self.cotas)

    def cagr(self):
        return _cagr(self.cotas, self.datas)

    # -------------------------------------------------------------
    # Patrimônio
    # -------------------------------------------------------------

    def crescimento_patrimonio(self):
        return _retorno(self.pl)

    # -------------------------------------------------------------
    # Cotistas
    # -------------------------------------------------------------

    def crescimento_cotistas(self):
        return _retorno(self.cotistas)

    # -------------------------------------------------------------
    # Fluxo
    # -------------------------------------------------------------

    def fluxo_liquido(self):
        return float(self.captacao.sum() - self.resgates.sum())

    def captacao_total(self):
        return float(self.captacao.sum())

    def resgate_total(self):
        return float(self.resgates.sum())

    # -------------------------------------------------------------
    # Volatilidade
    # -------------------------------------------------------------

    def volatilidade(self):
        retornos = _serie_retorno(self.cotas)
        if retornos.empty:
            return None
        return retornos.std() * math.sqrt(DIAS_ANO)

    # -------------------------------------------------------------
    # Drawdown
    # -------------------------------------------------------------

    def drawdown(self):
        if len(self.cotas) < 2:
            return None
        maximos = self.cotas.cummax()
        drawdowns = (self.cotas / maximos) - 1
        return float(drawdowns.min())

    # -------------------------------------------------------------
    # Estatísticas
    # -------------------------------------------------------------

    def maior_cota(self):
        return float(self.cotas.max())

    def menor_cota(self):
        return float(self.cotas.min())

    def patrimonio_atual(self):
        return float(self.pl.iloc[-1])

    def patrimonio_maximo(self):
        return float(self.pl.max())

    def patrimonio_medio(self):
        return float(self.pl.mean())

    def cotistas_atuais(self):
        return int(self.cotistas.iloc[-1])

    def cotistas_maximo(self):
        return int(self.cotistas.max())

    # -------------------------------------------------------------
    # Resumo dos indicadores
    # -------------------------------------------------------------

    def indicadores(self):
        """
        Retorna um dicionário com todos os indicadores calculados.
        """
        return {
            "cnpj": self.cnpj,
            "nome": (
                self.cadastro["Denominacao_Social"]
                if self.cadastro
                else None
            ),
            "classe": (
                self.cadastro["Classificacao_Anbima"]
                if self.cadastro
                else None
            ),
            "tipo": (
                self.cadastro["Tipo_Classe"]
                if self.cadastro
                else None
            ),
            "retorno_1m": self.retorno_1m(),
            "retorno_3m": self.retorno_3m(),
            "retorno_6m": self.retorno_6m(),
            "retorno_12m": self.retorno_12m(),
            "retorno_total": self.retorno_total(),
            "cagr": self.cagr(),
            "volatilidade": self.volatilidade(),
            "drawdown": self.drawdown(),
            "fluxo_liquido": self.fluxo_liquido(),
            "captacao_total": self.captacao_total(),
            "resgate_total": self.resgate_total(),
            "crescimento_patrimonio": self.crescimento_patrimonio(),
            "crescimento_cotistas": self.crescimento_cotistas(),
            "patrimonio_atual": self.patrimonio_atual(),
            "patrimonio_maximo": self.patrimonio_maximo(),
            "patrimonio_medio": self.patrimonio_medio(),
            "cotistas_atuais": self.cotistas_atuais(),
            "cotistas_maximo": self.cotistas_maximo(),
            "maior_cota": self.maior_cota(),
            "menor_cota": self.menor_cota(),
            "dias_historico": len(self.df),
        }

    # -------------------------------------------------------------
    # DataFrame e séries
    # -------------------------------------------------------------

    def dataframe(self):
        return self.df.copy()

    def serie_cotas(self):
        return self.cotas.copy()

    def serie_patrimonio(self):
        return self.pl.copy()

    def serie_cotistas(self):
        return self.cotistas.copy()


# ---------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------

def calcular_indicadores(cnpj):
    """
    Calcula todos os indicadores para um fundo (sem Sharpe e Sortino).
    """
    return IndicadoresFundos(cnpj).indicadores()


def serie_cotas(cnpj):
    return IndicadoresFundos(cnpj).serie_cotas()


def serie_patrimonio(cnpj):
    return IndicadoresFundos(cnpj).serie_patrimonio()


def serie_cotistas(cnpj):
    return IndicadoresFundos(cnpj).serie_cotistas()


# ---------------------------------------------------------------------
# Teste
# ---------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s - %(message)s",
    )

    cnpj = "00017024000153"

    try:
        indicadores = calcular_indicadores(cnpj)

        print()
        print("=" * 80)
        print("INDICADORES DO FUNDO (SEM SHARPE E SORTINO)")
        print("=" * 80)

        for chave, valor in indicadores.items():
            print(f"{chave:30}: {valor}")

        print()
        print("=" * 80)

    except Exception as e:
        logger.exception(e)