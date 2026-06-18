"""
Traduz o portfólio em sugestões de ativos específicos por classe.

Lógica: para cada classe presente no portfólio com alocação >= MIN_PCT,
busca e rankeia os melhores ativos daquela classe.
"""

from categorias import RK
from screener import top_acoes, top_fiis, top_cripto

# Mapeamento rk → classe de ativo
_CLASSE: dict[str, str] = {
    RK.RV:               "acoes",
    RK.RV_DCA:           "acoes",
    RK.RV_COMPL:         "acoes",
    RK.FUNDOS_ACOES:     "acoes",
    RK.FUNDOS_ACOES_ETF: "acoes",
    RK.FUNDOS_ACOES_DCA: "acoes",
    RK.FIIS:             "fiis",
    RK.FIIS_DEL:         "fiis",
    RK.RV_CRIPTO:        "cripto",
    RK.FUNDOS_CRIPTO:    "cripto",
}

_LABEL: dict[str, str] = {
    "acoes":  "AÇÕES",
    "fiis":   "FIIs",
    "cripto": "CRIPTO",
}

# Percentual mínimo no portfólio para valer buscar ativos da classe
MIN_PCT = 5


def recomendar_por_portfolio(portfolio: dict, perfil_risco: int,
                              n: int = 5) -> dict[str, list]:
    """
    Recebe o portfólio completo e retorna um dict com os top N ativos
    de cada classe que tiver alocação >= MIN_PCT no portfólio.

    Retorna: {"fiis": [...], "acoes": [...], "cripto": [...]}
    Só inclui as classes que aparecem no portfólio.

    Exemplo:
        portfolio = {"rf": 60, "fundos": 35, "fiis": 5}
        resultado = recomendar_por_portfolio(portfolio, perfil_risco=1)
        # resultado = {"fiis": [top5 FIIs]}
    """
    # Descobre quais classes estão no portfólio com pct suficiente
    classes: set[str] = set()
    for rk, pct in portfolio.items():
        if pct >= MIN_PCT and rk in _CLASSE:
            classes.add(_CLASSE[rk])

    if not classes:
        return {}

    resultado: dict[str, list] = {}
    for classe in sorted(classes):  # ordem consistente
        try:
            if classe == "acoes":
                resultado["acoes"] = top_acoes(perfil_risco, n=n)
            elif classe == "fiis":
                resultado["fiis"] = top_fiis(perfil_risco, n=n)
            elif classe == "cripto":
                resultado["cripto"] = top_cripto(perfil_risco, n=min(n, 4))
        except Exception as e:
            resultado[classe] = [{
                "ticker": "ERRO", "score": 0, "preco": 0, "nome": "",
                "motivos": [f"Falha ao buscar dados: {e}"],
            }]

    return resultado


def recomendar_ativos(rec_key: str, perfil_risco: int,
                      n: int = 5) -> list[dict] | None:
    """
    Versão legada: usa só o rec_key principal.
    Mantida para compatibilidade. Prefira recomendar_por_portfolio().
    """
    classe = _CLASSE.get(rec_key)
    if classe is None:
        return None
    try:
        if classe == "acoes":
            return top_acoes(perfil_risco, n=n)
        if classe == "fiis":
            return top_fiis(perfil_risco, n=n)
        if classe == "cripto":
            return top_cripto(perfil_risco, n=min(n, 4))
    except Exception as e:
        return [{"ticker": "ERRO", "score": 0, "preco": 0,
                 "motivos": [f"Falha: {e}"]}]
    return None