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

from .cvm_cadastro_downloader import download_cadastro

from .informe_diario_coletor import (
    buscar_historico,
    buscar_historico_completo,
    buscar_ultimo_registro,
    listar_historicos,
    listar_cnpjs_distintos,
    total_registros,
    carregar_ultimos_meses,
    carregar_historico,
)

# Deixamos esses imports comentados até criar os arquivos
# from .ranker import rankear_fundos, calcular_score
# from .indicadores import (
#     calcular_indicadores,
#     calcular_indicadores_df,
#     serie_cotas,
#     serie_patrimonio,
#     serie_cotistas,
# )
# from .sharpe_sortino import calcular_indicadores_risco

# Deixamos também o __all__ apenas com o que já existe
__all__ = [
    "download_cadastro",
    "get_coletor",
    "listar_fundos",
    "listar_fundos_ativos",
    "buscar_por_nome",
    "buscar_por_cnpj",
    "listar_por_classe",
    "buscar_historico",
    "buscar_historico_completo",
    "buscar_ultimo_registro",
    "listar_historicos",
    "listar_cnpjs_distintos",
    "total_registros",
    "carregar_ultimos_meses",
    "carregar_historico",
    # "calcular_indicadores",
    # "calcular_indicadores_df",
    # "serie_cotas",
    # "serie_patrimonio",
    # "serie_cotistas",
    # "calcular_indicadores_risco",
    # "rankear_fundos",
    # "calcular_score",
]