"""
Controle de concentração setorial no ranking de ações.

Problema
────────
Um screener puramente quantitativo pode retornar 5 construtoras ou
4 bancos no top 5, porque setores inteiros costumam ter indicadores
parecidos em determinado momento de ciclo econômico.

Mesmo com scores perfeitos, o usuário percebe isso como uma
recomendação ruim — e tem razão: concentração setorial é um risco
não capturado por DY, ROE, P/L ou patrimônio.

Solução
───────
Após o ranking por score, aplica-se um filtro de diversificação:
no top N final, nenhum setor pode ter mais de MAX_POR_SETOR ações.

Quando um setor atinge o limite, as próximas ações desse setor são
puladas e substituídas pela melhor ação do próximo setor disponível.

O score NÃO é alterado — apenas a seleção final é diversificada.
Isso preserva a informação de qualidade e evita vieses artificiais.

Limites por perfil
──────────────────
  Conservador: max 2 por setor — quer diversificação ampla
  Moderado:    max 2 por setor — equilíbrio padrão
  Agressivo:   max 3 por setor — aceita mais concentração se ROE justificar

Inferência de setor
───────────────────
Prioridade:
  1. Campo "segment" retornado pela API (quando disponível)
  2. Dicionário curado por prefixo de ticker (4 letras)
  3. Fallback: "Outro" (não penaliza, mas não agrupa)

O dicionário cobre os ~120 tickers mais líquidos do Ibovespa e
small/mid caps frequentes. Tickers desconhecidos caem em "Outro"
e cada um é tratado como setor único (não concentram entre si).
"""

from __future__ import annotations

# ── Limite de ações por setor no top N final ─────────────────────────────────
MAX_POR_SETOR: dict[int, int] = {
    1: 2,   # Conservador
    2: 2,   # Moderado
    3: 3,   # Agressivo
}

# ── Mapeamento prefixo → setor ────────────────────────────────────────────────
# Prefixo de 4 letras do ticker (ex: "ITUB" de ITUB4, ITUB3).
# Setores agrupados em categorias econômicas amplas para evitar
# over-segmentação (ex: "Bancos" e "Seguradoras" → ambos "Financeiro").

_SETOR_POR_PREFIXO: dict[str, str] = {
    # Financeiro — bancos
    "ITUB": "Financeiro", "BBAS": "Financeiro", "BBDC": "Financeiro",
    "SANB": "Financeiro", "BPAC": "Financeiro", "BRSR": "Financeiro",
    "BMGB": "Financeiro", "PINE": "Financeiro", "BRBI": "Financeiro",
    "ABCB": "Financeiro", "INTER": "Financeiro", "MODL": "Financeiro",
    # Financeiro — seguros, corretoras, serviços financeiros
    "BBSE": "Financeiro", "IRBR": "Financeiro", "WIZC": "Financeiro",
    "SULA": "Financeiro", "PSSA": "Financeiro", "CXSE": "Financeiro",
    "ATOM": "Financeiro", "AFLT": "Financeiro",
    # Energia — petróleo, gás, combustíveis
    "PETR": "Energia",    "UGPA": "Energia",    "VBBR": "Energia",
    "CSAN": "Energia",    "RRRP": "Energia",    "PRIO": "Energia",
    "RECV": "Energia",    "ENAT": "Energia",
    # Mineração e siderurgia
    "VALE": "Mineração",  "CSNA": "Siderurgia", "GGBR": "Siderurgia",
    "USIM": "Siderurgia", "CBA0": "Mineração",  "BRAP": "Mineração",
    "FESA": "Mineração",
    # Construção civil e incorporação
    "CYRE": "Construção", "EVEN": "Construção", "MDNE": "Construção",
    "MRVE": "Construção", "DIRR": "Construção", "TRIS": "Construção",
    "LAVV": "Construção", "EZTC": "Construção", "JHSF": "Construção",
    "PLPL": "Construção", "HBTS": "Construção", "TEND": "Construção",
    "CALI": "Construção", "AUCA": "Construção",
    # Indústria e bens de capital
    "WEGE": "Indústria",  "POMO": "Indústria",  "ROMI": "Indústria",
    "FRAS": "Indústria",  "TUPY": "Indústria",  "MYPK": "Indústria",
    "FHER": "Indústria",  "MEAL": "Indústria",  "KEPL": "Indústria",
    # Consumo e varejo
    "MGLU": "Varejo",     "VIVA": "Varejo",     "AMER": "Varejo",
    "LREN": "Varejo",     "SOMA": "Varejo",     "AMAR": "Varejo",
    "ALPA": "Varejo",     "VULC": "Varejo",     "GUAR": "Varejo",
    "VSTE": "Varejo",
    # Alimentos e bebidas
    "JBSS": "Alimentos",  "BRFS": "Alimentos",  "MRFG": "Alimentos",
    "ABEV": "Alimentos",  "SMTO": "Alimentos",  "CAML": "Alimentos",
    "BEEF": "Alimentos",  "MDIA": "Alimentos",
    # Utilities — energia elétrica
    "CMIG": "Utilities",  "CPFE": "Utilities",  "EGIE": "Utilities",
    "ENEV": "Utilities",  "TAEE": "Utilities",  "TRPL": "Utilities",
    "ENBR": "Utilities",  "NEOE": "Utilities",  "ELET": "Utilities",
    "AURE": "Utilities",  "ISAE": "Utilities",  "CPLE": "Utilities",
    # Utilities — saneamento e gás
    "SBSP": "Utilities",  "SAPR": "Utilities",  "CSMG": "Utilities",
    "GGPS": "Utilities",
    # Telecom
    "VIVT": "Telecom",    "TIMS": "Telecom",
    # Tecnologia
    "TOTS": "Tecnologia", "TOTVS": "Tecnologia", "LWSA": "Tecnologia",
    "INTB": "Tecnologia", "MLAS": "Tecnologia",
    # Saúde
    "RDOR": "Saúde",      "HAPV": "Saúde",      "FLRY": "Saúde",
    "DASA": "Saúde",      "GNDI": "Saúde",      "QUAL": "Saúde",
    "ONCO": "Saúde",
    # Logística e transporte
    "RAIL": "Logística",  "GETT": "Logística",  "ALLD": "Logística",
    "HBSA": "Logística",  "TGMA": "Logística",  "VAMO": "Logística",
    "SIMH": "Logística",
    # Papel e celulose
    "KLBN": "Papel",      "SUZB": "Papel",
    # Agronegócio
    "SLCE": "Agronegócio","AGRO": "Agronegócio","SOJA": "Agronegócio",
    "TTEN": "Agronegócio","LAND": "Agronegócio",
    # Imóveis comerciais (não FII)
    "MULT": "Imóveis",    "BRPR": "Imóveis",    "IGBR": "Imóveis",
}


def inferir_setor(ind: dict) -> str:
    """
    Infere o setor de uma ação com prioridade:
      1. Campo 'segment' da API (quando não vazio)
      2. Dicionário curado por prefixo de 4 letras
      3. Fallback único por ticker (evita agrupar desconhecidos)
    """
    segment = (ind.get("segment") or "").strip()
    if segment:
        return segment

    ticker  = ind.get("ticker", "").upper()
    prefixo = ticker[:4]
    if prefixo in _SETOR_POR_PREFIXO:
        return _SETOR_POR_PREFIXO[prefixo]

    # Tenta prefixo de 3 letras como último recurso
    if ticker[:3] in _SETOR_POR_PREFIXO:
        return _SETOR_POR_PREFIXO[ticker[:3]]

    # Fallback: trata o ticker como setor único — não agrupa com outros
    return f"_unico_{ticker}"


def diversificar(ranking: list[dict], n: int, perfil: int) -> list[dict]:
    """
    Seleciona os top N do ranking garantindo diversificação setorial.

    Algoritmo:
      1. Percorre o ranking na ordem de score (melhor primeiro)
      2. Adiciona o ativo se o setor ainda não atingiu o limite
      3. Pula se o setor estiver cheio
      4. Para quando tiver N ativos ou esgotar o ranking

    Parâmetros
    ──────────
      ranking — lista ordenada por score (maior primeiro), com campo 'score'
      n       — quantos ativos retornar
      perfil  — perfil de risco (1=conservador, 2=moderado, 3=agressivo)

    Retorna lista de no máximo N ativos diversificados.
    Pode retornar menos que N se o universo for pequeno.
    """
    limite = MAX_POR_SETOR.get(perfil, 2)
    contagem_setor: dict[str, int] = {}
    selecionados: list[dict] = []

    for ativo in ranking:
        if len(selecionados) >= n:
            break
        setor = inferir_setor(ativo)
        if contagem_setor.get(setor, 0) < limite:
            contagem_setor[setor] = contagem_setor.get(setor, 0) + 1
            ativo_com_setor = dict(ativo)
            ativo_com_setor["setor"] = setor   # anexa o setor ao resultado
            selecionados.append(ativo_com_setor)

    return selecionados
