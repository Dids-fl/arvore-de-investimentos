"""
Filtros para refinar lista de ações por setor, índice de governança, etc.
"""

from typing import List, Dict, Callable

def filtrar_por_setor(acoes: List[Dict], setores: List[str]) -> List[Dict]:
    """
    Filtra ações por setor (ex: ["Financeiro", "Petróleo"]).
    """
    if not setores:
        return acoes
    return [a for a in acoes if a.get('setor', '').lower() in [s.lower() for s in setores]]

def filtrar_por_governanca(acoes: List[Dict], niveis: List[str]) -> List[Dict]:
    """
    Filtra por nível de governança corporativa (ex: ["NM", "N2", "N1"]).

    IMPORTANTE: o sufixo do ticker NÃO determina o nível de governança.
    BBAS3 e ITUB4 são ambos Novo Mercado (NM), apesar dos sufixos diferentes.
    A inferência correta exige consulta à B3 ou campo "governanca" da API.

    Comportamento:
      - Se o campo "governanca" estiver presente no ativo: filtra por ele.
      - Se o campo estiver ausente em todos os ativos: retorna todos sem filtrar
        (evita descartar erroneamente empresas por lógica de sufixo incorreta).
    """
    if not niveis:
        return acoes
    ativos_com_campo = [a for a in acoes if a.get("governanca")]
    if not ativos_com_campo:
        # Campo não disponível na API atual — não filtra para não descartar indevidamente
        return acoes
    return [a for a in acoes if a.get("governanca", "") in niveis]

def aplicar_filtros(acoes: List[Dict], filtros: List[Callable]) -> List[Dict]:
    """
    Aplica uma lista de funções de filtro.
    """
    for f in filtros:
        acoes = f(acoes)
    return acoes