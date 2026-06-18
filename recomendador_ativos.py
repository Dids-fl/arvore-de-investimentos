"""
Traduz o portfólio em sugestões de ativos específicos por classe.
"""

from categorias import RK
from screener import top_acoes, top_fiis, top_cripto

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
    RK.RF:               "rf",
    RK.RF_LIQUIDEZ:      "rf",
    RK.RF_SELIC_CDB:     "rf",
    RK.RF_IPCA:          "rf",
    RK.RF_RESERVA:       "rf",
    RK.FUNDOS_RF:        "rf",
    RK.FUNDOS_RF_LIQ:    "rf",
    RK.FUNDOS:           "fundos",
    RK.FUNDOS_DIVERSIF:  "fundos",
    RK.FUNDOS_MULTI:     "fundos",
}

_LABEL: dict[str, str] = {
    "acoes":  "AÇÕES / ETFs",
    "fiis":   "FIIs",
    "cripto": "CRIPTO",
    "rf":     "RENDA FIXA",
    "fundos": "FUNDOS",
}

MIN_PCT = 5


def _sugestoes_rf(perfil_risco: int) -> list[dict]:
    if perfil_risco == 1:
        return [
            {"ticker": "SELIC",  "nome": "Tesouro Selic", "preco": 0, "score": 95,
             "motivos": ["✅ Maior segurança do Brasil — garantia governo federal",
                         "✅ Liquidez D+1: resgata qualquer dia útil",
                         "✅ Rende 100% da SELIC — referência do mercado",
                         "ℹ️  IR regressivo: 22.5% (<6m) → 15% (>2 anos)"]},
            {"ticker": "CDB-DI", "nome": "CDB liquidez diária (banco digital)", "preco": 0, "score": 88,
             "motivos": ["✅ Busque 100%+ do CDI (Nubank, Inter, C6, PicPay)",
                         "✅ FGC até R$250k por CPF por instituição",
                         "✅ Liquidez diária — igual ao Tesouro Selic",
                         "ℹ️  IR regressivo igual ao Tesouro Selic"]},
            {"ticker": "LCI/LCA", "nome": "LCI / LCA", "preco": 0, "score": 82,
             "motivos": ["✅ ISENTO de IR para pessoa física",
                         "✅ FGC até R$250k por CPF por instituição",
                         "⚠️  Carência mínima: verifique prazo de resgate",
                         "ℹ️  Isenção equivale a ~3-4% de retorno extra líquido"]},
        ]
    elif perfil_risco == 2:
        return [
            {"ticker": "IPCA+",  "nome": "Tesouro IPCA+", "preco": 0, "score": 92,
             "motivos": ["✅ Protege o poder de compra: IPCA + taxa real garantida",
                         "✅ Garantia governo federal",
                         "ℹ️  Ideal para prazo médio/longo (5+ anos)",
                         "ℹ️  IR 15% sobre ganhos reais"]},
            {"ticker": "CDB-CDI", "nome": "CDB prefixado/pós-fixado (banco menor)", "preco": 0, "score": 84,
             "motivos": ["✅ Bancos menores pagam 110-130% do CDI",
                         "✅ FGC até R$250k por CPF por instituição",
                         "ℹ️  Compare no Yubb ou Renda Fixa Pro",
                         "ℹ️  Melhor manter por 2+ anos (IR regressivo)"]},
            {"ticker": "DEBN",   "nome": "Debêntures incentivadas (infraestrutura)", "preco": 0, "score": 78,
             "motivos": ["✅ ISENTO de IR — Lei 12.431/2011",
                         "✅ Taxa real costuma superar Tesouro IPCA+",
                         "⚠️  SEM FGC — risco de crédito do emissor",
                         "ℹ️  Verifique rating (AAA/AA = mais seguro)"]},
        ]
    else:
        return [
            {"ticker": "IPCA+",  "nome": "Tesouro IPCA+ (âncora da carteira)", "preco": 0, "score": 80,
             "motivos": ["✅ Âncora de longo prazo — trava taxa real",
                         "ℹ️  Complementa RV com estabilidade anti-inflação",
                         "ℹ️  Vencimentos longos (2035, 2045) dão mais taxa real",
                         "ℹ️  Pode valorizar com queda de juros (marcação a mercado)"]},
            {"ticker": "CRI/CRA", "nome": "CRI / CRA (recebíveis imobiliários/agro)", "preco": 0, "score": 75,
             "motivos": ["✅ ISENTO de IR para pessoa física",
                         "✅ Taxa real geralmente acima do Tesouro IPCA+",
                         "⚠️  SEM FGC — avalie o emissor e o lastro",
                         "ℹ️  Mínimo típico: R$1.000; liquidez variável"]},
        ]


def _sugestoes_fundos(perfil_risco: int) -> list[dict]:
    if perfil_risco == 1:
        return [
            {"ticker": "FDO-RF",   "nome": "Fundo de Renda Fixa DI (taxa admin <0.5% a.a.)", "preco": 0, "score": 85,
             "motivos": ["✅ Liquidez diária, baixo risco",
                         "✅ Taxa admin abaixo de 0.5% a.a. é essencial",
                         "ℹ️  Come-cotas em maio/nov reduz rentabilidade efetiva",
                         "ℹ️  Prefira Tesouro Selic se puder investir direto"]},
            {"ticker": "FDO-PREV", "nome": "VGBL/PGBL de renda fixa (aposentadoria)", "preco": 0, "score": 80,
             "motivos": ["✅ IR regressivo: 10% no resgate após 10+ anos",
                         "✅ PGBL: deduz até 12% da renda bruta (IR completo)",
                         "ℹ️  Zero taxa de carregamento — exija isso",
                         "ℹ️  Gestoras: Icatu, XP Seguros, Zurich"]},
        ]
    elif perfil_risco == 2:
        return [
            {"ticker": "FDO-MULTI", "nome": "Fundo Multimercado macro (CDI+ com baixa vol.)", "preco": 0, "score": 88,
             "motivos": ["✅ Retorno CDI+ independente do mercado",
                         "✅ Gestoras: SPX, Verde, Ibiúna, Kinea",
                         "ℹ️  Taxa admin <1.5% a.a. + performance 20% do CDI",
                         "ℹ️  Come-cotas semestral — planeje para 2+ anos"]},
            {"ticker": "FDO-DEBN", "nome": "Fundo de Debêntures Incentivadas", "preco": 0, "score": 82,
             "motivos": ["✅ ISENTO de IR para o cotista",
                         "✅ Diversifica risco de crédito automaticamente",
                         "ℹ️  Geralmente supera o Tesouro IPCA+ líquido",
                         "ℹ️  Plataformas: XP, BTG, Órama"]},
        ]
    else:
        return [
            {"ticker": "FDO-LONG", "nome": "Fundo Multimercado long biased / long short", "preco": 0, "score": 85,
             "motivos": ["✅ Exposição a ações com gestão ativa de risco",
                         "ℹ️  Long biased: mais retorno que multimercado puro",
                         "ℹ️  Long short: pode ganhar em quedas do mercado",
                         "ℹ️  Gestoras: Kapitalo, Vinland, Constellation"]},
            {"ticker": "IVVB11",   "nome": "IVVB11 — ETF S&P500 (diversificação EUA)", "preco": 0, "score": 82,
             "motivos": ["✅ Exposição às 500 maiores empresas americanas",
                         "✅ Taxa de admin ~0.24% a.a. — muito barato",
                         "ℹ️  Proteção cambial embutida: lucra com alta do dólar",
                         "ℹ️  15% sobre ganho de capital (sem come-cotas)"]},
        ]


def recomendar_por_portfolio(portfolio: dict, perfil_risco: int,
                              n: int = 5) -> dict[str, list]:
    classes: set[str] = set()
    for rk, pct in portfolio.items():
        if pct >= MIN_PCT and rk in _CLASSE:
            classes.add(_CLASSE[rk])

    if not classes:
        return {}

    ordem = ["rf", "fundos", "fiis", "acoes", "cripto"]
    resultado: dict[str, list] = {}

    for classe in ordem:
        if classe not in classes:
            continue
        try:
            if classe == "acoes":
                resultado["acoes"]  = top_acoes(perfil_risco, n=n)
            elif classe == "fiis":
                resultado["fiis"]   = top_fiis(perfil_risco, n=n)
            elif classe == "cripto":
                resultado["cripto"] = top_cripto(perfil_risco, n=min(n, 4))
            elif classe == "rf":
                resultado["rf"]     = _sugestoes_rf(perfil_risco)
            elif classe == "fundos":
                resultado["fundos"] = _sugestoes_fundos(perfil_risco)
        except Exception as e:
            resultado[classe] = [{"ticker": "ERRO", "score": 0, "preco": 0,
                                  "nome": "", "motivos": [f"Falha: {e}"]}]

    return resultado


def recomendar_ativos(rec_key: str, perfil_risco: int,
                      n: int = 5) -> list[dict] | None:
    """Versão legada — prefira recomendar_por_portfolio()."""
    classe = _CLASSE.get(rec_key)
    if classe is None:
        return None
    try:
        if classe == "acoes":   return top_acoes(perfil_risco, n=n)
        if classe == "fiis":    return top_fiis(perfil_risco, n=n)
        if classe == "cripto":  return top_cripto(perfil_risco, n=min(n, 4))
        if classe == "rf":      return _sugestoes_rf(perfil_risco)
        if classe == "fundos":  return _sugestoes_fundos(perfil_risco)
    except Exception as e:
        return [{"ticker": "ERRO", "score": 0, "preco": 0, "motivos": [f"Falha: {e}"]}]
    return None
