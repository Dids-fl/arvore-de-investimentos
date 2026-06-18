"""
Configurações do screener: pesos de score, referências de normalização
e parâmetros do universo dinâmico.

Nenhum ticker é fixo aqui — o universo vem das APIs em tempo real.

Filosofia de pontuação por perfil
──────────────────────────────────
  Conservador (1) — DY recorrente e alto é o critério dominante.
  Moderado    (2) — melhor relação retorno total / risco. ROE é a âncora.
  Agressivo   (3) — crescimento acima de tudo. ROE dominante; DY irrelevante.
"""

MIN_LIQUIDEZ_ACOES = 1_000_000
MIN_LIQUIDEZ_FIIS  =   200_000
UNIVERSO_ACOES_N   = 150
UNIVERSO_FIIS_N    = 100
CRIPTO_TOP_N       = 20

PESOS_ACOES: dict[int, dict[str, float]] = {
    1: {"dy": 0.50, "pl": 0.25, "roe": 0.15, "pvp": 0.10},
    2: {"dy": 0.25, "pl": 0.20, "roe": 0.40, "pvp": 0.15},
    3: {"dy": 0.05, "pl": 0.10, "roe": 0.70, "pvp": 0.15},
}

PESOS_FIIS: dict[int, dict[str, float]] = {
    1: {"dy": 0.45, "pvp": 0.25, "liquidez": 0.15, "vacancia": 0.15},
    2: {"dy": 0.35, "pvp": 0.25, "liquidez": 0.25, "vacancia": 0.15},
    3: {"dy": 0.20, "pvp": 0.35, "liquidez": 0.30, "vacancia": 0.15},
}

PESOS_CRIPTO: dict[int, dict[str, float]] = {
    1: {"market_cap": 0.60, "volume": 0.35, "retorno_12m": 0.05},
    2: {"market_cap": 0.35, "volume": 0.30, "retorno_12m": 0.35},
    3: {"market_cap": 0.15, "volume": 0.25, "retorno_12m": 0.60},
}

REF_ACOES = {
    "dy":  {"bom": 12.0, "ruim": 0.0},
    "roe": {"bom": 35.0, "ruim": 0.0},
    "pl":  {"bom": 6.0,  "ruim": 35.0},
    "pvp": {"bom": 0.8,  "ruim": 3.0},
}

REF_ACOES_AGRESSIVO = {
    "dy":  {"bom": 12.0, "ruim": 0.0},
    "roe": {"bom": 40.0, "ruim": 5.0},
    "pl":  {"bom": 8.0,  "ruim": 60.0},
    "pvp": {"bom": 1.0,  "ruim": 5.0},
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

LIMIARES_DY_ACOES: dict[int, dict[str, float]] = {
    1: {"otimo": 8.0, "ok": 5.0},
    2: {"otimo": 5.0, "ok": 3.0},
    3: {"otimo": 3.0, "ok": 1.0},
}

LIMIARES_ROE_ACOES: dict[int, dict[str, float]] = {
    1: {"otimo": 15.0, "ok": 10.0},
    2: {"otimo": 20.0, "ok": 12.0},
    3: {"otimo": 28.0, "ok": 18.0},
}

LIMIARES_PL_ACOES: dict[int, dict[str, float]] = {
    1: {"otimo": 10.0, "ok": 15.0},
    2: {"otimo": 14.0, "ok": 22.0},
    3: {"otimo": 20.0, "ok": 40.0},
}
