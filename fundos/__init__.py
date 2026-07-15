# fundos/__init__.py
"""
Módulo de Fundos de Investimento.

Fornece download, cache local, indicadores e ranking por perfil.
"""

from .cadastro_coletor import (
    get_coletor,
    listar_fundos,
    listar_fundos_ativos,
    buscar_por_nome,
    buscar_por_cnpj,
    listar_por_classe,
)

from .ranker import rankear_fundos, calcular_score
from .indicadores import (
    calcular_indicadores,
    calcular_indicadores_df,
    serie_cotas,
    serie_patrimonio,
    serie_cotistas,
)
from .sharpe_sortino import calcular_indicadores_risco
from .cvm_cadastro_downloader import download_cadastro

__all__ = [
    # Downloader
    "download_cadastro",
    # Coletor
    "get_coletor",
    "listar_fundos",
    "listar_fundos_ativos",
    "buscar_por_nome",
    "buscar_por_cnpj",
    "listar_por_classe",
    # Indicadores
    "calcular_indicadores",
    "calcular_indicadores_df",
    "serie_cotas",
    "serie_patrimonio",
    "serie_cotistas",
    # Risco
    "calcular_indicadores_risco",
    # Ranking
    "rankear_fundos",
    "calcular_score",
]