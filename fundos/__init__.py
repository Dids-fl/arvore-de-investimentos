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
    listar_metricas_agregadas,
    listar_cnpjs_distintos,
    total_registros,
    carregar_ultimos_meses,
    carregar_historico,
)

from .indicadores import (
    calcular_indicadores,
    calcular_indicadores_df,
    serie_cotas,
    serie_patrimonio,
    serie_cotistas,
)

from .sharpe_sortino import calcular_indicadores_risco

from .filtros import FiltroFundos, filtrar_para_ranking

from .ranker import (
    rankear_fundos,
    calcular_score,
    gerar_ranking,
    top_fundos,
    buscar_fundo_cnpj,
    buscar_fundo_nome,
    fundos_por_classe,
    PERFIL_CONSERVADOR,
    PERFIL_MODERADO,
    PERFIL_AGRESSIVO,
)

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
    "listar_metricas_agregadas",
    "listar_cnpjs_distintos",
    "total_registros",
    "carregar_ultimos_meses",
    "carregar_historico",
    "calcular_indicadores",
    "calcular_indicadores_df",
    "serie_cotas",
    "serie_patrimonio",
    "serie_cotistas",
    "calcular_indicadores_risco",
    "FiltroFundos",
    "filtrar_para_ranking",
    "rankear_fundos",
    "calcular_score",
    "gerar_ranking",
    "top_fundos",
    "buscar_fundo_cnpj",
    "buscar_fundo_nome",
    "fundos_por_classe",
    "PERFIL_CONSERVADOR",
    "PERFIL_MODERADO",
    "PERFIL_AGRESSIVO",
]