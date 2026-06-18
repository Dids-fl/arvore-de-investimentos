"""
Traduz o portfólio em sugestões de ativos específicos por classe.

Lógica: para cada classe presente no portfólio com alocação >= MIN_PCT,
busca e rankeia os melhores ativos daquela classe.

Classes suportadas
──────────────────
  acoes   → ações e ETFs de renda variável
  fiis    → fundos imobiliários
  cripto  → criptomoedas
  rf      → renda fixa (Tesouro, CDB, LCI/LCA) — lista estática curada
"""

from categorias import RK
from screener import top_acoes, top_fiis, top_cripto

# Mapeamento rk → classe de ativo
_CLASSE: dict[str, str] = {
    # ── Renda Variável → ações ────────────────────────────────────────────────
    RK.RV:               "acoes",
    RK.RV_DCA:           "acoes",
    RK.RV_COMPL:         "acoes",
    RK.FUNDOS_ACOES:     "acoes",
    RK.FUNDOS_ACOES_ETF: "acoes",
    RK.FUNDOS_ACOES_DCA: "acoes",
    # ── FIIs ──────────────────────────────────────────────────────────────────
    RK.FIIS:             "fiis",
    RK.FIIS_DEL:         "fiis",
    # ── Cripto ────────────────────────────────────────────────────────────────
    RK.RV_CRIPTO:        "cripto",
    RK.FUNDOS_CRIPTO:    "cripto",
    # ── Renda Fixa — mapeados para sugestão curada ───────────────────────────
    RK.RF:               "rf",
    RK.RF_LIQUIDEZ:      "rf",
    RK.RF_SELIC_CDB:     "rf",
    RK.RF_IPCA:          "rf",
    RK.RF_RESERVA:       "rf",
    RK.FUNDOS_RF:        "rf",
    RK.FUNDOS_RF_LIQ:    "rf",
    # ── Fundos genéricos → ações (via ETF/multimercado) ──────────────────────
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

# Percentual mínimo no portfólio para valer buscar ativos da classe
MIN_PCT = 5

# ── Sugestões curadas de Renda Fixa ──────────────────────────────────────────
# A renda fixa não tem API de ranking dinâmico como ações/FIIs.
# Retornamos uma lista curada por subtipo, com orientações práticas.

def _sugestoes_rf(perfil_risco: int) -> list[dict]:
    """
    Sugestões curadas de renda fixa por perfil.
    Não usa API — dados são estruturais (produtos não mudam, só as taxas).
    """
    if perfil_risco == 1:
        return [
            {
                "ticker": "SELIC",
                "nome":   "Tesouro Selic",
                "preco":  0,
                "score":  95,
                "motivos": [
                    "✅ Maior segurança do Brasil — garantia governo federal",
                    "✅ Liquidez D+1: resgata qualquer dia útil",
                    "✅ Rende 100% da SELIC — referência do mercado",
                    "ℹ️  IR regressivo: 22.5% (<6m) → 15% (>2 anos)",
                ],
            },
            {
                "ticker": "CDB-DI",
                "nome":   "CDB com liquidez diária (banco digital)",
                "preco":  0,
                "score":  88,
                "motivos": [
                    "✅ Busque 100%+ do CDI (Nubank, Inter, C6, PicPay)",
                    "✅ FGC até R$250k por CPF por instituição",
                    "✅ Liquidez diária — igual ao Tesouro Selic",
                    "ℹ️  IR regressivo igual ao Tesouro Selic",
                ],
            },
            {
                "ticker": "LCI/LCA",
                "nome":   "LCI/LCA (Letra de Crédito Imobiliário/Agronegócio)",
                "preco":  0,
                "score":  82,
                "motivos": [
                    "✅ ISENTO de IR para pessoa física",
                    "✅ FGC até R$250k por CPF por instituição",
                    "⚠️  Carência mínima: verifique prazo de resgate",
                    "ℹ️  Isenção equivale a ~3-4% de retorno extra líquido",
                ],
            },
        ]
    elif perfil_risco == 2:
        return [
            {
                "ticker": "IPCA+",
                "nome":   "Tesouro IPCA+ (proteção contra inflação)",
                "preco":  0,
                "score":  92,
                "motivos": [
                    "✅ Protege o poder de compra: IPCA + taxa real garantida",
                    "✅ Garantia governo federal",
                    "ℹ️  Ideal para prazo médio/longo (5+ anos)",
                    "ℹ️  IR 15% sobre ganhos reais (não sobre inflação)",
                ],
            },
            {
                "ticker": "CDB-CDI",
                "nome":   "CDB prefixado ou pós-fixado (banco menor)",
                "preco":  0,
                "score":  84,
                "motivos": [
                    "✅ Bancos menores pagam 110-130% do CDI",
                    "✅ FGC até R$250k por CPF por instituição",
                    "ℹ️  Compare no Yubb ou Renda Fixa Pro",
                    "ℹ️  IR regressivo: melhor manter por 2+ anos",
                ],
            },
            {
                "ticker": "DEBN",
                "nome":   "Debêntures incentivadas (infraestrutura)",
                "preco":  0,
                "score":  78,
                "motivos": [
                    "✅ ISENTO de IR — Lei 12.431/2011",
                    "✅ Taxa real costuma superar Tesouro IPCA+",
                    "⚠️  SEM FGC — risco de crédito do emissor",
                    "ℹ️  Verifique rating (AAA/AA = mais seguro)",
                ],
            },
        ]
    else:  # agressivo
        return [
            {
                "ticker": "IPCA+",
                "nome":   "Tesouro IPCA+ (âncora da carteira)",
                "preco":  0,
                "score":  80,
                "motivos": [
                    "✅ Âncora de longo prazo — trava taxa real",
                    "ℹ️  Complementa RV com estabilidade anti-inflação",
                    "ℹ️  Vencimentos longos (2035, 2045) dão mais taxa real",
                    "ℹ️  Marque a mercado: pode valorizar com queda de juros",
                ],
            },
            {
                "ticker": "CRI/CRA",
                "nome":   "CRI / CRA (recebíveis imobiliários/agro)",
                "preco":  0,
                "score":  75,
                "motivos": [
                    "✅ ISENTO de IR para pessoa física",
                    "✅ Taxa real geralmente acima do Tesouro IPCA+",
                    "⚠️  SEM FGC — avalie o emissor e o lastro",
                    "ℹ️  Mínimo típico: R$1.000; liquidez variável",
                ],
            },
        ]


# ── Sugestões curadas de Fundos ───────────────────────────────────────────────

def _sugestoes_fundos(perfil_risco: int) -> list[dict]:
    """
    Sugestões curadas de fundos multimercado/diversificados por perfil.
    Não usa API — orienta sobre critérios de seleção.
    """
    if perfil_risco == 1:
        return [
            {
                "ticker": "FDO-RF",
                "nome":   "Fundo de Renda Fixa DI (taxa admin <0.5% a.a.)",
                "preco":  0,
                "score":  85,
                "motivos": [
                    "✅ Liquidez diária, baixo risco",
                    "✅ Taxa admin abaixo de 0.5% a.a. é essencial",
                    "ℹ️  Come-cotas em maio/nov reduz rentabilidade efetiva",
                    "ℹ️  Prefira Tesouro Selic se puder investir direto",
                ],
            },
            {
                "ticker": "FDO-PREV",
                "nome":   "VGBL/PGBL de renda fixa (aposentadoria)",
                "preco":  0,
                "score":  80,
                "motivos": [
                    "✅ IR regressivo: 10% no resgate após 10+ anos",
                    "✅ PGBL: deduz até 12% da renda bruta (IR completo)",
                    "ℹ️  Zero taxa de carregamento — exija isso",
                    "ℹ️  Gestoras: Icatu, XP Seguros, Zurich",
                ],
            },
        ]
    elif perfil_risco == 2:
        return [
            {
                "ticker": "FDO-MULTI",
                "nome":   "Fundo Multimercado macro (CDI+ com baixa vol.)",
                "preco":  0,
                "score":  88,
                "motivos": [
                    "✅ Retorno CDI+ independente do mercado",
                    "✅ Gestoras reconhecidas: SPX, Verde, Ibiúna, Kinea",
                    "ℹ️  Taxa admin <1.5% a.a. + performance 20% do CDI",
                    "ℹ️  Come-cotas semestral — plano para 2+ anos",
                ],
            },
            {
                "ticker": "FDO-DEBN",
                "nome":   "Fundo de Debêntures Incentivadas",
                "preco":  0,
                "score":  82,
                "motivos": [
                    "✅ ISENTO de IR para o cotista",
                    "✅ Diversifica risco de crédito automaticamente",
                    "ℹ️  Geralmente supera o Tesouro IPCA+ líquido",
                    "ℹ️  Plataformas: XP, BTG, Órama",
                ],
            },
        ]
    else:  # agressivo
        return [
            {
                "ticker": "FDO-MULTI",
                "nome":   "Fundo Multimercado long biased / long short",
                "preco":  0,
                "score":  85,
                "motivos": [
                    "✅ Exposição a ações com gestão ativa de risco",
                    "ℹ️  Long biased: mais retorno que multimercado puro",
                    "ℹ️  Long short: pode ganhar em quedas do mercado",
                    "ℹ️  Gestoras: Kapitalo, Vinland, Constellation",
                ],
            },
            {
                "ticker": "ETF-IVVB",
                "nome":   "IVVB11 — ETF S&P500 (diversificação EUA)",
                "preco":  0,
                "score":  82,
                "motivos": [
                    "✅ Exposição às 500 maiores empresas americanas",
                    "✅ Taxa de admin ~0.24% a.a. — muito barato",
                    "ℹ️  Proteção cambial embutida: lucra com alta do dólar",
                    "ℹ️  15% sobre ganho de capital (sem come-cotas)",
                ],
            },
        ]


# ── Função principal ──────────────────────────────────────────────────────────

def recomendar_por_portfolio(portfolio: dict, perfil_risco: int,
                              n: int = 5) -> dict[str, list]:
    """
    Recebe o portfólio completo e retorna um dict com os top N ativos
    de cada classe que tiver alocação >= MIN_PCT no portfólio.

    Retorna: {"rf": [...], "fiis": [...], "acoes": [...], "cripto": [...], "fundos": [...]}
    Só inclui as classes que aparecem no portfólio.
    """
    # Descobre quais classes estão no portfólio com pct suficiente
    classes: set[str] = set()
    for rk, pct in portfolio.items():
        if pct >= MIN_PCT and rk in _CLASSE:
            classes.add(_CLASSE[rk])

    if not classes:
        return {}

    # Ordem de exibição: RF primeiro (contexto), depois as demais
    ordem = ["rf", "fundos", "fiis", "acoes", "cripto"]

    resultado: dict[str, list] = {}
    for classe in ordem:
        if classe not in classes:
            continue
        try:
            if classe == "acoes":
                resultado["acoes"] = top_acoes(perfil_risco, n=n)
            elif classe == "fiis":
                resultado["fiis"] = top_fiis(perfil_risco, n=n)
            elif classe == "cripto":
                resultado["cripto"] = top_cripto(perfil_risco, n=min(n, 4))
            elif classe == "rf":
                resultado["rf"] = _sugestoes_rf(perfil_risco)
            elif classe == "fundos":
                resultado["fundos"] = _sugestoes_fundos(perfil_risco)
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
        if classe == "rf":
            return _sugestoes_rf(perfil_risco)
        if classe == "fundos":
            return _sugestoes_fundos(perfil_risco)
    except Exception as e:
        return [{"ticker": "ERRO", "score": 0, "preco": 0,
                 "motivos": [f"Falha: {e}"]}]
    return None