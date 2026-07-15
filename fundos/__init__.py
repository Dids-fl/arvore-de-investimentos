# fundos/__init__.py

"""
Módulo de Fundos de Investimento.

Este pacote fornece:

- Download automático do cadastro oficial da CVM
- Cache local em SQLite
- Busca de fundos
- Ranking por perfil de investidor
"""

from .cadastro_coletor import (
    get_coletor,
    listar_fundos,
    listar_fundos_ativos,
    buscar_por_nome,
    buscar_por_cnpj,
    listar_por_classe,
)

from .ranker import (
    rankear_fundos,
    calcular_score,
)

from cvm_downloader import (
    download_cadastro,
)

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

    # Ranking
    "rankear_fundos",
    "calcular_score",

]

# fundos/__init__.py
from .ranker import rankear_fundos
from .indicadores import calcular_indicadores
from .sharpe_sortino import calcular_indicadores_risco

__all__ = [
    "rankear_fundos",
    "calcular_indicadores",
    "calcular_indicadores_risco",
]