"""
Configurações do screener: pesos de score, referências de normalização
e parâmetros do universo dinâmico.

Nenhum ticker é fixo aqui — o universo vem das APIs em tempo real.
"""

# ── Liquidez mínima para entrar no universo ───────────────────────────────────
MIN_LIQUIDEZ_ACOES = 1_000_000   # R$1M/dia (elimina penny stocks e ilíquidos)
MIN_LIQUIDEZ_FIIS  =   200_000   # R$200k/dia
UNIVERSO_ACOES_N   = 150         # quantos buscar da API antes de filtrar
UNIVERSO_FIIS_N    = 100
CRIPTO_TOP_N       = 20          # top 20 por market cap da CoinGecko

# ── Pesos de score por perfil ─────────────────────────────────────────────────
# Campos disponíveis no batch do Status Invest: dy, pl, roe, pvp, liquidez

PESOS_ACOES: dict[int, dict[str, float]] = {
    1: {  # Conservador — renda + preço barato + qualidade
        "dy":  0.40,
        "pl":  0.25,
        "roe": 0.20,
        "pvp": 0.15,
    },
    2: {  # Moderado — equilíbrio
        "dy":  0.25,
        "pl":  0.20,
        "roe": 0.35,
        "pvp": 0.20,
    },
    3: {  # Agressivo — crescimento
        "dy":  0.10,
        "pl":  0.15,
        "roe": 0.55,
        "pvp": 0.20,
    },
}

PESOS_FIIS: dict[int, dict[str, float]] = {
    1: {"dy": 0.40, "pvp": 0.25, "liquidez": 0.20, "vacancia": 0.15},
    2: {"dy": 0.35, "pvp": 0.25, "liquidez": 0.25, "vacancia": 0.15},
    3: {"dy": 0.28, "pvp": 0.27, "liquidez": 0.25, "vacancia": 0.20},
}

PESOS_CRIPTO: dict[int, dict[str, float]] = {
    1: {"market_cap": 0.55, "volume": 0.35, "retorno_12m": 0.10},
    2: {"market_cap": 0.35, "volume": 0.30, "retorno_12m": 0.35},
    3: {"market_cap": 0.20, "volume": 0.25, "retorno_12m": 0.55},
}

# ── Referências para normalização (bom=melhor, ruim=pior) ─────────────────────

REF_ACOES = {
    "dy":  {"bom": 12.0, "ruim": 0.0},
    "roe": {"bom": 35.0, "ruim": 0.0},
    "pl":  {"bom": 6.0,  "ruim": 35.0},   # menor é melhor → bom < ruim
    "pvp": {"bom": 0.8,  "ruim": 3.0},    # menor é melhor
}

REF_FIIS = {
    "dy":       {"bom": 14.0,      "ruim": 4.0},
    "pvp":      {"bom": 0.90,      "ruim": 1.60},
    "liquidez": {"bom": 3_000_000, "ruim": 100_000},
    "vacancia": {"bom": 0.0,       "ruim": 20.0},
}

REF_CRIPTO = {
    "market_cap":  {"bom": 2_000_000_000_000, "ruim": 5_000_000_000},
    "volume":      {"bom": 100_000_000_000,   "ruim": 500_000_000},
    "retorno_12m": {"bom": 300.0,             "ruim": -70.0},
}
