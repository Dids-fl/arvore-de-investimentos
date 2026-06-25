"""
Configurações do screener: pesos de score, referências de normalização
e parâmetros do universo dinâmico.

Nenhum ticker é fixo aqui — o universo vem das APIs em tempo real.

Filosofia de pontuação por perfil
──────────────────────────────────
  Conservador (1) — DY recorrente e alto é o critério dominante.
      Quer dividendos previsíveis todo ano: peso DY elevado, P/L baixo
      como confirmação de preço justo, ROE mínimo como filtro de qualidade.
      Tolerância zero a empresas sem histórico de proventos.

  Moderado (2) — melhor relação retorno total / risco.
      Equilíbrio entre ROE (qualidade do negócio), DY razoável e preço
      justo (P/L + P/VP). Busca empresas que crescem E distribuem — o
      chamado "compounding com renda". ROE é o indicador-âncora.

  Agressivo (3) — crescimento acima de tudo.
      ROE altíssimo é o critério dominante; DY quase irrelevante
      (empresa que reinveste lucro cresce mais). P/L alto é aceitável
      se o ROE justificar — por isso a referência de P/L "ruim" foi
      ampliada para não penalizar crescimento. P/VP como tiebreaker.
"""

# ── Liquidez mínima para entrar no universo ───────────────────────────────────
MIN_LIQUIDEZ_ACOES = 1_000_000   # R$1M/dia (elimina penny stocks e ilíquidos)
MIN_LIQUIDEZ_FIIS  =   200_000   # R$200k/dia
UNIVERSO_ACOES_N   = 150         # quantos buscar da API antes de filtrar
UNIVERSO_FIIS_N    = 100
CRIPTO_TOP_N       = 20          # top 20 por market cap da CoinGecko

# ── Componente de tamanho/robustez no score de ações ─────────────────────────
# Reflete que tamanho e liquidez são atributos de risco independentes dos
# fundamentos — e devem ser pesados conforme o perfil de RISCO, não de
# conhecimento. Um agressivo experiente aceita small caps; um conservador
# experiente ainda quer empresas grandes.
#
# Score composto de tamanho:
#   0.20 × market_cap_norm  +  0.10 × liquidez_norm  (quando mktcap disponível)
#   0.30 × liquidez_norm                              (quando mktcap não disponível)
#
# Pesos do componente de tamanho sobre o score final, por perfil de risco:
#   Conservador: 0.30 — tamanho importa muito; quer empresa reconhecida e estável
#   Moderado:    0.20 — equilíbrio entre fundamentals e robustez
#   Agressivo:   0.08 — fundamentos dominam; small cap OK se ROE excepcional
PESO_TAMANHO_ACOES: dict[int, float] = {1: 0.30, 2: 0.20, 3: 0.08}

# Referências para normalização em escala log
# Market cap: VALE3/PETR4 ~R$400B = score 1.0; R$500M = score ~0.18 (small cap)
MKTCAP_REF_MAX_B  = 200.0   # R$200B — patrimônio dos maiores bancos/mineradoras
MKTCAP_REF_MIN_B  = 0.5     # R$500M = threshold mínimo de relevância
# Liquidez: ITUB4 ~R$500M/dia = score 1.0; R$1M/dia = score 0.0
LIQ_REF_MAX_M     = 500.0   # R$500M/dia

# ── Pesos de score por perfil ─────────────────────────────────────────────────
# Campos disponíveis no batch do Status Invest: dy, pl, roe, pvp

PESOS_ACOES: dict[int, dict[str, float]] = {
    1: {  # Conservador — DY recorrente é rei; P/L como confirmação de preço justo
        "dy":  0.50,   # critério dominante: renda previsível e alta
        "pl":  0.25,   # preço justo: não pagar caro por quem distribui pouco
        "roe": 0.15,   # qualidade mínima do negócio (filtro, não motor)
        "pvp": 0.10,   # tiebreaker: margem de segurança no preço
    },
    2: {  # Moderado — ROE como âncora; DY + P/L como equilíbrio risco/retorno
        "dy":  0.25,   # renda relevante mas não dominante
        "pl":  0.20,   # preço justo ainda importa
        "roe": 0.40,   # qualidade do negócio é o motor principal
        "pvp": 0.15,   # complementa avaliação de preço
    },
    3: {  # Agressivo — ROE máximo; DY quase ignorado (reinvestimento > distribuição)
        "dy":  0.05,   # irrelevante: empresa de crescimento reinveste, não distribui
        "pl":  0.10,   # tolerante a P/L alto se ROE justificar
        "roe": 0.70,   # critério dominante: retorno sobre capital é tudo
        "pvp": 0.15,   # tiebreaker entre empresas igualmente rentáveis
    },
}

PESOS_FIIS: dict[int, dict[str, float]] = {
    1: {  # Conservador — DY alto e recorrente + vacância zero + P/VP seguro
        "dy":       0.45,  # renda mensal previsível é o objetivo principal
        "pvp":      0.25,  # não pagar prêmio excessivo sobre o patrimônio
        "liquidez": 0.15,  # saída rápida se precisar
        "vacancia": 0.15,  # vacância alta corrói o DY — critério eliminatório
    },
    2: {  # Moderado — equilíbrio entre renda e potencial de valorização
        "dy":       0.35,
        "pvp":      0.25,
        "liquidez": 0.25,  # liquidez maior: carteira moderada gira mais
        "vacancia": 0.15,
    },
    3: {  # Agressivo — liquidez e potencial de valorização (P/VP baixo = upside)
        "dy":       0.20,  # DY menos importante: busca ganho de capital também
        "pvp":      0.35,  # P/VP baixo = maior upside de valorização
        "liquidez": 0.30,  # alta liquidez para operar com agilidade
        "vacancia": 0.15,
    },
}

PESOS_CRIPTO: dict[int, dict[str, float]] = {
    1: {  # Conservador — segurança máxima: BTC/ETH dominam por market cap e volume
        "market_cap": 0.60,
        "volume":     0.35,
        "retorno_12m": 0.05,  # retorno histórico quase irrelevante: quer estabilidade
    },
    2: {  # Moderado — equilíbrio: market cap sólido + retorno razoável
        "market_cap": 0.35,
        "volume":     0.30,
        "retorno_12m": 0.35,
    },
    3: {  # Agressivo — retorno 12m domina: busca altcoins com momentum forte
        "market_cap": 0.15,
        "volume":     0.25,
        "retorno_12m": 0.60,  # critério dominante: aceita mais risco por mais retorno
    },
}

# ── Referências para normalização (bom=melhor, ruim=pior) ─────────────────────
#
# Ações — nota: as referências são GLOBAIS (independentes de perfil).
# Quem muda o comportamento por perfil são os PESOS acima, não as referências.
# Exceção: REF_ACOES_AGRESSIVO redefine a tolerância ao P/L para não penalizar
# empresas de crescimento que naturalmente negociam a múltiplos mais altos.

REF_ACOES = {
    "dy":  {"bom": 12.0, "ruim": 0.0},
    "roe": {"bom": 35.0, "ruim": 0.0},
    "pl":  {"bom": 6.0,  "ruim": 35.0},   # menor é melhor → bom < ruim
    "pvp": {"bom": 0.8,  "ruim": 3.0},    # menor é melhor
}

# Para o perfil agressivo: P/L "ruim" ampliado — empresa de crescimento com
# P/L 50 não deve ser penalizada tão duramente quanto uma value stock cara.
REF_ACOES_AGRESSIVO = {
    "dy":  {"bom": 12.0, "ruim": 0.0},    # igual (mas peso ~0, então irrelevante)
    "roe": {"bom": 40.0, "ruim": 5.0},    # exige ROE mais alto; abaixo de 5% = ruim
    "pl":  {"bom": 8.0,  "ruim": 60.0},   # tolera P/L até 60 sem punição severa
    "pvp": {"bom": 1.0,  "ruim": 5.0},    # aceita P/VP maior (empresas premium)
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

# ── Limiares de feedback nos motivos — variam por perfil ─────────────────────
# Define quando um indicador merece ✅, ℹ️  ou ⚠️  para cada tipo de carteira.

LIMIARES_DY_ACOES: dict[int, dict[str, float]] = {
    1: {"otimo": 8.0,  "ok": 5.0},   # conservador exige DY alto
    2: {"otimo": 5.0,  "ok": 3.0},   # moderado: DY razoável já satisfaz
    3: {"otimo": 3.0,  "ok": 1.0},   # agressivo: qualquer dividendo é bônus
}

LIMIARES_ROE_ACOES: dict[int, dict[str, float]] = {
    1: {"otimo": 15.0, "ok": 10.0},  # conservador: ROE como filtro de qualidade mínima
    2: {"otimo": 20.0, "ok": 12.0},  # moderado: ROE bom é requisito
    3: {"otimo": 28.0, "ok": 18.0},  # agressivo: exige ROE excepcional
}

LIMIARES_PL_ACOES: dict[int, dict[str, float]] = {
    1: {"otimo": 10.0, "ok": 15.0},  # conservador: quer P/L baixo (preço barato)
    2: {"otimo": 14.0, "ok": 22.0},  # moderado: tolera múltiplo um pouco maior
    3: {"otimo": 20.0, "ok": 40.0},  # agressivo: P/L alto OK se ROE justificar
}