"""
Traduz o rec_key do recomendador de perfil em sugestões de ativos específicos.

Apenas categorias de renda variável e FIIs recebem recomendações específicas.
Renda Fixa já está detalhada no catálogo (_get_prod).
"""

from categorias import RK
from screener import top_acoes, top_fiis, top_cripto

# Mapeamento rec_key → classe de ativo
_CLASSE: dict[str, str] = {
    RK.RV:               "acoes",
    RK.RV_DCA:           "acoes",
    RK.RV_COMPL:         "acoes",
    RK.FUNDOS_ACOES:     "acoes",
    RK.FIIS:             "fiis",
    RK.FIIS_DEL:         "fiis",
    RK.RV_CRIPTO:        "cripto",
    RK.FUNDOS_CRIPTO:    "cripto",
}


def recomendar_ativos(rec_key: str, perfil_risco: int,
                      n: int = 5) -> list[dict] | None:
    """
    Retorna lista com os top N ativos específicos para o rec_key e perfil.
    Retorna None para categorias sem recomendação individual
    (RF, previdência, ETFs, fundos multimercado).

    Exemplo:
        sugestoes = recomendar_ativos(RK.FIIS, perfil_risco=1)
        for s in sugestoes:
            print(f"{s['ticker']}  score {s['score']:.0f}/100")
            for m in s['motivos']:
                print(f"  {m}")
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
        return [{"ticker": "ERRO", "score": 0,
                 "motivos": [f"Falha ao buscar dados: {e}"],
                 "preco": 0}]

    return None
