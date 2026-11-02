"""Garantias da carteira: FGC, Tesouro e o que fica sem garantia.

Regras do FGC para pessoa física (Resolução CMN 4.222/2013 e regulamento do
FGC, mantidas na revisão de junho de 2026): até R$ 250 mil por CPF em cada
instituição ou conglomerado, incluindo os juros, e teto global de R$ 1 milhão
a cada quatro anos. O Tesouro Direto não tem limite: a garantia é do Tesouro
Nacional.
"""

from __future__ import annotations

import math

LIMITE_POR_INSTITUICAO = 250_000.0
TETO_GLOBAL_4_ANOS = 1_000_000.0

# Categorias em que o app sugere Tesouro ou CDB/LCI/LCA (coberto pelo FGC).
CATEGORIAS_FGC_OU_TESOURO = {
    "rf", "rf_liq", "rf_reserva", "rf_ipca", "rf_selic_cdb", "rf_equilibrio",
}
CATEGORIAS_SO_TESOURO = {"rf_reavalie"}
CATEGORIAS_FUNDOS = {
    "fundos", "fundos_div", "fundos_multi", "fundos_rf", "fundos_rf_liq",
    "fundos_acoes", "fundos_etf", "fundos_dca", "fundos_cripto",
    "prev_pgbl", "prev_vgbl", "prev_pgbl_rf", "prev_vgbl_rf",
}
# Sem garantia nenhuma: risco de mercado ou de crédito do emissor.
CATEGORIAS_SEM_GARANTIA = {
    "rv", "rv_dca", "rv_compl", "rv_cripto", "fiis", "fiis_del", "coe",
    "estruturados", "cambio", "ofertas",
}


def analisar_garantias(
    carteira: dict[str, float],
    valor: float,
    *,
    rendimento_ate_vencimento: float = 0.0,
) -> dict:
    """Divide o valor por tipo de garantia e gera os alertas de FGC.

    ``rendimento_ate_vencimento`` (fração) estima os juros que o FGC também
    precisa cobrir: R$ 240 mil hoje podem passar de R$ 250 mil no vencimento.
    """
    soma = sum(float(p) for p in carteira.values()) or 1.0
    grupos = {"fgc_ou_tesouro": 0.0, "tesouro": 0.0, "fundos": 0.0, "sem_garantia": 0.0}
    for categoria, peso in carteira.items():
        parte = valor * float(peso) / soma
        if categoria in CATEGORIAS_FGC_OU_TESOURO:
            grupos["fgc_ou_tesouro"] += parte
        elif categoria in CATEGORIAS_SO_TESOURO:
            grupos["tesouro"] += parte
        elif categoria in CATEGORIAS_FUNDOS:
            grupos["fundos"] += parte
        else:
            grupos["sem_garantia"] += parte

    alertas: list[str] = []
    bancario = grupos["fgc_ou_tesouro"]
    no_vencimento = bancario * (1 + max(rendimento_ate_vencimento, 0.0))
    instituicoes = max(1, math.ceil(no_vencimento / LIMITE_POR_INSTITUICAO)) if bancario else 0
    if no_vencimento > LIMITE_POR_INSTITUICAO:
        alertas.append(
            f"Se usar CDB, LCI ou LCA, divida entre pelo menos {instituicoes} "
            "bancos de conglomerados diferentes: o FGC cobre até R$ 250 mil por "
            "CPF em cada um, já contando os juros."
        )
    if no_vencimento > TETO_GLOBAL_4_ANOS:
        alertas.append(
            "O FGC paga no máximo R$ 1 milhão por CPF a cada 4 anos, somando todos "
            "os bancos que quebrarem. Para a parte acima disso, prefira Tesouro "
            "Direto, que não tem limite."
        )
    if grupos["sem_garantia"] > 0 and grupos["sem_garantia"] / max(valor, 1) > 0.5:
        alertas.append(
            "Mais da metade do valor fica sem garantia (ações, FIIs, cripto, COE "
            "ou crédito privado). Só invista o que puder ver cair sem precisar vender."
        )
    if grupos["fundos"] > 0:
        alertas.append(
            "Fundos e previdência não têm FGC, mas o patrimônio fica separado do "
            "banco ou da seguradora: se a gestora quebrar, as cotas continuam suas. "
            "O risco é o dos ativos do fundo."
        )
    return {
        "grupos": grupos,
        "instituicoes_necessarias": instituicoes,
        "valor_bancario_no_vencimento": no_vencimento,
        "alertas": alertas,
    }
