# macroeconomia/cdi.py
"""
Módulo para obtenção da taxa CDI (Certificado de Depósito Interbancário)
diretamente do Banco Central do Brasil via API SGS.

Séries SGS oficiais:
    - 12: CDI diário (taxa percentual ao dia) - recomendado para cálculos
    - 4391: CDI mensal (taxa acumulada no mês) - para consultas/relatórios

Referência: https://dadosabertos.bcb.gov.br/dataset/sistema-gerenciador-de-series-temporarias-sgs
"""

import logging
import pandas as pd
from datetime import datetime, timedelta
from bcb import sgs

logger = logging.getLogger(__name__)

# Séries SGS oficiais
SERIE_CDI_DIARIO = 12   # Taxa percentual ao dia
SERIE_CDI_MENSAL = 4391 # Taxa acumulada no mês

# Dias úteis por ano (aproximado para anualização)
DIAS_UTEIS_ANO = 252


def obter_cdi_diario(data: str = None) -> float:
    """
    Retorna a taxa CDI diária (percentual ao dia) para uma data específica.
    Se data não for fornecida, retorna o último valor disponível.

    Args:
        data (str, optional): Data no formato 'YYYY-MM-DD'.

    Returns:
        float: Taxa CDI diária em decimal (ex: 0.0005 para 0,05% ao dia),
               ou None se não houver dado disponível.
    """
    try:
        if data is None:
            data = datetime.now().strftime("%Y-%m-%d")

        # Busca apenas o dia específico
        df = sgs.get(
            {f"cdi_diario": SERIE_CDI_DIARIO},
            start=data,
            end=data,
        )
        if df.empty:
            # Se não houver dado para a data, tenta o último dia útil disponível
            df = sgs.get({f"cdi_diario": SERIE_CDI_DIARIO}, end=data)
            if df.empty:
                return None

        # A série 12 retorna valores percentuais (ex: 0.05 para 0,05% ao dia)
        valor = df.iloc[-1, 0]
        return valor / 100  # converte para decimal
    except Exception as e:
        logger.warning(f"Erro ao buscar CDI diário: {e}")
        return None


def obter_cdi_mensal(ano: int, mes: int) -> float:
    """
    Retorna a taxa CDI acumulada em um mês específico (série 4391).
    Útil para relatórios e conferência.

    Args:
        ano (int): Ano (ex: 2026).
        mes (int): Mês (1 a 12).

    Returns:
        float: Taxa CDI mensal em decimal (ex: 0.0087 para 0,87% ao mês),
               ou None se não houver dados.
    """
    try:
        data_inicio = f"{ano:04d}-{mes:02d}-01"
        # Último dia do mês
        if mes == 12:
            data_fim = f"{ano + 1:04d}-01-01"
        else:
            data_fim = f"{ano:04d}-{mes + 1:02d}-01"
        data_fim = (
            datetime.strptime(data_fim, "%Y-%m-%d") - timedelta(days=1)
        ).strftime("%Y-%m-%d")

        df = sgs.get(
            {f"cdi_mensal": SERIE_CDI_MENSAL},
            start=data_inicio,
            end=data_fim,
        )
        if df.empty:
            return None

        # A série 4391 já retorna a taxa mensal acumulada em percentual
        valor = df.iloc[-1, 0]
        return valor / 100  # converte para decimal
    except Exception as e:
        logger.warning(f"Erro ao buscar CDI mensal: {e}")
        return None


def obter_cdi_periodo(data_inicio: str, data_fim: str) -> float:
    """
    Retorna a taxa CDI acumulada no período, anualizada (equivalente anual),
    calculada a partir da série diária (série 12).

    Args:
        data_inicio (str): Data de início no formato 'YYYY-MM-DD'.
        data_fim (str): Data de fim no formato 'YYYY-MM-DD'.

    Returns:
        float: Taxa CDI anualizada em decimal (ex: 0.105 para 10,5% ao ano),
               ou None se não houver dados suficientes.
    """
    try:
        inicio = datetime.strptime(data_inicio, "%Y-%m-%d")
        fim = datetime.strptime(data_fim, "%Y-%m-%d")

        if inicio >= fim:
            logger.warning("Data de início deve ser anterior à data de fim.")
            return None

        # Busca a série diária no período
        df = sgs.get(
            {f"cdi_diario": SERIE_CDI_DIARIO},
            start=data_inicio,
            end=data_fim,
        )

        if df.empty:
            logger.warning("Nenhum dado de CDI diário encontrado no período.")
            return None

        # Cálculo: fator acumulado = (1 + taxa/100) para cada dia
        fator_acumulado = (1 + df.iloc[:, 0] / 100).prod()

        dias_uteis = len(df)
        if dias_uteis == 0:
            return None

        # Anualiza: fator ^ (252 / dias_uteis) - 1
        cdi_anual = fator_acumulado ** (DIAS_UTEIS_ANO / dias_uteis) - 1

        return float(cdi_anual)
    except Exception as e:
        logger.warning(f"Erro ao calcular CDI do período: {e}")
        return None


def obter_cdi_anualizado() -> float:
    """
    Retorna o CDI anualizado aproximado (últimos 12 meses).
    Usa a série diária para calcular o acumulado do período.

    Returns:
        float: Taxa CDI anualizada em decimal, ou None se não houver dados.
    """
    try:
        hoje = datetime.now()
        um_ano_atras = hoje - timedelta(days=365)
        return obter_cdi_periodo(
            um_ano_atras.strftime("%Y-%m-%d"),
            hoje.strftime("%Y-%m-%d"),
        )
    except Exception as e:
        logger.warning(f"Erro ao buscar CDI anualizado: {e}")
        return None


# ---------------------------------------------------------------------
# Teste rápido
# ---------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # CDI diário atual
    cdi_dia = obter_cdi_diario()
    print(f"CDI diário (último): {cdi_dia:.6%}" if cdi_dia else "CDI diário não disponível")

    # CDI anualizado
    cdi_ano = obter_cdi_anualizado()
    print(f"CDI anualizado: {cdi_ano:.2%}" if cdi_ano else "CDI anual não disponível")

    # CDI de um período específico (ex: 2025)
    cdi_periodo = obter_cdi_periodo("2025-01-01", "2025-12-31")
    print(f"CDI 2025: {cdi_periodo:.2%}" if cdi_periodo else "CDI 2025 não disponível")

    # CDI mensal (ex: Janeiro 2026)
    cdi_mensal = obter_cdi_mensal(2026, 1)
    print(f"CDI Janeiro 2026: {cdi_mensal:.4%}" if cdi_mensal else "CDI mensal não disponível")