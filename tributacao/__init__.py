"""Fachada do motor tributário versionado e orientado a premissas."""

from __future__ import annotations

from tributacao.base import (
    ContextoTributario,
    PrecisaoTributaria,
    ResultadoTributario,
    resultado_indeterminado,
)
from tributacao.cripto import calcular_cripto
from tributacao.estruturados import calcular_estruturado
from tributacao.fundos import calcular_fundo
from tributacao.previdencia import calcular_previdencia
from tributacao.projecoes import (
    FUNDOS_COM_COME_COTAS,
    ProjecaoComeCotas,
    projetar_come_cotas,
)
from tributacao.regras import FONTE_RECEITA_RENDIMENTOS_CAPITAL, VIGENCIA_BASE
from tributacao.renda_fixa import calcular_renda_fixa
from tributacao.renda_variavel import calcular_renda_variavel

RENDA_FIXA = {
    "tesouro",
    "cdb",
    "lci",
    "lca",
}
FUNDOS = {
    "fundo_curto_prazo",
    "fundo_longo_prazo",
    "fundo_rf",
    "fundo_acoes",
    "fundo_etf_acoes",
}
PREVIDENCIA = {"pgbl", "vgbl"}
RENDA_VARIAVEL = {"acao", "acoes", "etf", "fii"}
CRIPTO = {"cripto", "bitcoin", "ethereum"}
ESTRUTURADOS = {
    "coe",
    "cri",
    "cra",
    "debenture_incentivada",
    "debenture_comum",
    "estruturado",
}


def calcular_tributacao(
    contexto: ContextoTributario,
) -> ResultadoTributario:
    """Seleciona a estratégia sem aplicar fallback tributário arbitrário."""
    if not isinstance(contexto, ContextoTributario):
        raise TypeError("contexto deve ser ContextoTributario.")
    if not contexto.pessoa_fisica:
        return resultado_indeterminado(
            contexto,
            motivo=(
                "O motor implementa regras para pessoa física. "
                "Pessoa jurídica exige regime, IRPJ, CSLL e contexto contábil."
            ),
            fonte=FONTE_RECEITA_RENDIMENTOS_CAPITAL,
            vigencia=VIGENCIA_BASE,
            regra_id="pessoa_juridica_fora_escopo",
        )
    tipo = contexto.tipo_produto
    if tipo in RENDA_FIXA:
        return calcular_renda_fixa(contexto)
    if tipo in FUNDOS:
        return calcular_fundo(contexto)
    if tipo in PREVIDENCIA:
        return calcular_previdencia(contexto)
    if tipo in RENDA_VARIAVEL:
        return calcular_renda_variavel(contexto)
    if tipo in CRIPTO:
        return calcular_cripto(contexto)
    if tipo in ESTRUTURADOS:
        return calcular_estruturado(contexto)
    return resultado_indeterminado(
        contexto,
        motivo=f"Produto sem estratégia tributária: {tipo!r}.",
        fonte=FONTE_RECEITA_RENDIMENTOS_CAPITAL,
        vigencia=VIGENCIA_BASE,
        regra_id="produto_nao_suportado",
    )


__all__ = [
    "FUNDOS_COM_COME_COTAS",
    "ContextoTributario",
    "PrecisaoTributaria",
    "ProjecaoComeCotas",
    "ResultadoTributario",
    "calcular_tributacao",
    "projetar_come_cotas",
]
