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
    Filtra por nível de governança (ex: ["NM", "N2"]).
    Extrai do ticker: se termina em 3 -> NM, 4 -> N2, 5 -> N1, 6 -> N2.
    """
    if not niveis:
        return acoes
    def nivel_do_ticker(ticker):
        if ticker[-1] == '3':
            return 'NM'
        elif ticker[-1] == '4':
            return 'N2'
        elif ticker[-1] == '5':
            return 'N1'
        elif ticker[-1] == '6':
            return 'N2'
        else:
            return 'OUTRO'
    return [a for a in acoes if nivel_do_ticker(a['ticker']) in niveis]

def aplicar_filtros(acoes: List[Dict], filtros: List[Callable]) -> List[Dict]:
    """
    Aplica uma lista de funções de filtro.
    """
    for f in filtros:
        acoes = f(acoes)
    return acoes