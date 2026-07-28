# produtos_estruturados/filtros.py
"""
Filtros de elegibilidade por perfil, aplicados ANTES do ranking — mesmo
princípio do fundos/filtros.py: descartar o que não serve para o perfil
antes de gastar tempo/score com isso.

Produtos Estruturados (CRA/CRI/Debênture) são, por definição, produtos de
risco médio/alto e prazo mais longo (ver core/categorias.py: RK.ESTRUTURADOS
tem nível de risco 2, mas exige conhecimento >= 2 e ticket alto — ver
recomendador.py). Os filtros abaixo refletem isso.
"""

PRAZO_MIN_DIAS = 180        # evita ativos prestes a vencer/ilíquidos por natureza

# Ajustado com base em dados reais de produção (jul/2026): debêntures
# incentivadas (Lei 12.431) — que são justamente as isentas de IR e o
# produto mais interessante desta categoria — costumam ter prazo de
# 7 a 12 anos. Um limite de ~5 anos para o perfil moderado descartava
# ~1800 de ~5200 ativos candidatos (quase toda a categoria).
PRAZO_MAX_DIAS_PERFIL = {
    1: 1460,   # conservador: até ~4 anos
    2: 3650,   # moderado: até ~10 anos (cobre a maioria das incentivadas)
    3: None,   # agressivo: sem limite de prazo
}

# Ajustado com base em dados reais: balcão de CRA/CRI/debênture é
# estruturalmente ilíquido — a maioria não negocia todo dia. Limiares
# antigos (2.0/4.0) descartavam ~1850 de ~5200 candidatos por falta de
# negócio na janela de 20 dias. Reduzidos e combinados com uma janela de
# negociação maior (ver ranker.py: DIAS_NEGOCIACAO_PADRAO = 60).
SCORE_LIQUIDEZ_MINIMO = {
    1: 2.5,   # conservador exige mais liquidez comprovada
    2: 1.0,
    3: 0.0,   # agressivo aceita ativos sem negociação recente
}


import logging

logger = logging.getLogger(__name__)


def motivo_inelegibilidade(ativo: dict, perfil: int) -> str | None:
    """Retorna o motivo (string) pelo qual o ativo seria descartado, ou
    None se ele for elegível. Usado tanto por `elegivel()` quanto para
    diagnóstico em `filtrar_para_ranking()`."""
    # Sanidade primeiro: taxa implausível (>35% a.a. equivalente) é quase
    # sempre outlier de dado (negócio isolado de baixíssimo volume, erro
    # na B3) ou dívida em estado de distress real. Nos dois casos, não é
    # apropriado ranquear como "melhor opção" para conservador/moderado.
    # Agressivo pode ver (o investidor assume o risco conscientemente),
    # mas o ativo fica marcado com `taxa_suspeita=True` para o front-end
    # sinalizar isso claramente ao usuário.
    if ativo.get("taxa_suspeita") and perfil != 3:
        return "taxa_implausivel_possivel_outlier"

    prazo_dias = ativo.get("prazo_dias")

    if prazo_dias is None:
        return "sem_data_vencimento"

    if prazo_dias < PRAZO_MIN_DIAS:
        return "prazo_curto_demais"

    prazo_max = PRAZO_MAX_DIAS_PERFIL.get(perfil)
    if prazo_max is not None and prazo_dias > prazo_max:
        return "prazo_longo_demais_para_perfil"

    minimo_liquidez = SCORE_LIQUIDEZ_MINIMO.get(perfil, 2.0)
    if ativo.get("score_liquidez", 0) < minimo_liquidez:
        return "liquidez_insuficiente"

    if ativo.get("taxa") is None and perfil != 3:
        return "sem_taxa_negociada_recente"

    return None


def elegivel(ativo: dict, perfil: int) -> bool:
    return motivo_inelegibilidade(ativo, perfil) is None


def filtrar_para_ranking(ativos: list[dict], perfil: int, tipos: set[str] | None = None) -> list[dict]:
    """
    Args:
        ativos: saída de produtos_estruturados.indicadores.montar_indicadores
        perfil: 1=Conservador, 2=Moderado, 3=Agressivo
        tipos: subconjunto opcional {"CRA", "CRI", "DEBENTURE"} para filtrar
            por tipo de produto (ex.: só debêntures incentivadas)

    Loga a contagem de descarte por motivo — essencial para diagnosticar
    rapidamente por que "N ativos -> 0 elegíveis" (ex.: campo de vencimento
    não localizado no CSV da B3, mudança de layout, etc.).
    """
    candidatos = [a for a in ativos if not tipos or a["tipo"] in tipos]

    motivos: dict[str, int] = {}
    elegiveis = []
    for ativo in candidatos:
        motivo = motivo_inelegibilidade(ativo, perfil)
        if motivo is None:
            elegiveis.append(ativo)
        else:
            motivos[motivo] = motivos.get(motivo, 0) + 1

    if candidatos and not elegiveis:
        logger.warning(
            f"Nenhum ativo elegível (perfil {perfil}) entre {len(candidatos)} candidatos. "
            f"Motivos de descarte: {motivos}"
        )
    elif motivos:
        logger.info(f"Descarte por motivo (perfil {perfil}): {motivos}")

    return elegiveis