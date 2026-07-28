# engine.py
"""
Núcleo de negócio compartilhado entre main.py (CLI) e app.py (Streamlit).

Antes desta refatoração, main.py e app.py reimplementavam separadamente:
  - a chamada de calcular_recomendacao() + _build_portfolio() + _classificar_portfolio_final()
  - o cálculo de taxa_perfil / taxa_pess
  - o filtro de "quais classes de ativo aparecem no portfólio"
  - o mapeamento de respostas em texto (formulário web) para os inteiros
    canônicos usados pelo motor — com dois dicionários distintos que
    podiam divergir silenciosamente.

Este módulo centraliza tudo isso. main.py e app.py continuam responsáveis
apenas pela apresentação (print no terminal vs. componentes do Streamlit).
"""

from typing import Optional

from calculos import _vf_bruto, _vf_liquido, _vf_real
from core.categorias import _risco
from core.catalogo import _get_prod, _disp, _aliq
from portfolio import _build_portfolio, _classificar_portfolio_final
from recomendador import calcular_recomendacao
from recomendador_ativos import recomendar_por_portfolio, _CLASSE, _LABEL, MIN_PCT
from cli import (
    _PD, _RD, _OD, _FD, _CD, _LD, _RSD, _ID, _DD, _VD, _PPD,
    _RND, _DVd, _KD, _DPD, _APD, _EMD, _IRD, _CAD, _MTD,
)

# ── Mapeamento único de respostas (texto -> inteiro canônico) ────────────────
# Reaproveita EXATAMENTE os dicionários que o CLI usa (cli.py), para que o
# webapp nunca interprete uma opção de forma diferente do terminal.
RESPOSTAS_MAP = {
    "prazo":         _PD,
    "risco":         _RD,
    "objetivo":      _OD,
    "fluxo":         _FD,
    "controle":      _CD,
    "liquidez":      _LD,
    "reserva_emerg": _RSD,
    "idade":         _ID,
    "despesas":      _DD,
    "faixa_valor":   _VD,
    "patrim_pct":    _PPD,
    "renda":         _RND,
    "dividas":       _DVd,
    "conhecimento":  _KD,
    "dependentes":   _DPD,
    "aporte":        _APD,
    "emocional":     _EMD,
    "ir_tipo":       _IRD,
    "carteira_atual": _CAD,
    "modo_meta":     _MTD,
}


def mapear_respostas_formulario(respostas_texto: dict) -> dict:
    """
    Converte respostas em texto (ex.: vindas de um st.selectbox do webapp)
    para os inteiros canônicos usados pelo motor de recomendação — usando
    os MESMOS dicionários que o CLI usa, para eliminar o risco de os dois
    canais divergirem no significado de cada opção.

    Campos que não têm mapeamento em RESPOSTAS_MAP (ex.: "experiencia",
    "liquidez_pct", "cap_inicial", "aporte_mensal") passam direto.
    """
    out = {}
    for campo, valor in respostas_texto.items():
        mapa = RESPOSTAS_MAP.get(campo)
        if mapa is not None and isinstance(valor, str):
            if valor not in mapa:
                raise ValueError(f"Opção inválida para '{campo}': {valor!r}")
            out[campo] = mapa[valor]
        else:
            out[campo] = valor
    return out


def taxas_por_risco(market: dict) -> dict:
    """{1: taxa conservadora, 2: moderada, 3: agressiva} a partir do dict
    devolvido por mercado.load_market_data()."""
    selic = market["selic"]
    ibov_cagr = market["ibov_cagr"]
    return {1: selic, 2: (selic + ibov_cagr) / 2, 3: ibov_cagr}


def gerar_recomendacao_completa(respostas: dict, market: dict) -> dict:
    """
    Função de negócio única: respostas do questionário -> classificação de
    perfil -> alocação percentual -> catálogo -> classes de ativo elegíveis.

    `respostas` deve conter os valores já em inteiros canônicos (use
    `mapear_respostas_formulario` antes, se vierem em texto de um form).
    `market` é o dict devolvido por mercado.load_market_data().

    Não decide apresentação (print/streamlit) — devolve um dict plano com
    tudo que main.py e app.py precisam para exibir o resultado. A busca
    de ativos (rede, mais lenta) fica separada em `buscar_ativos_sugeridos`,
    para que cada canal decida quando/se vale a pena buscar.
    """
    ipca = market["ipca"]
    TAXAS = taxas_por_risco(market)

    rec_key, nivel_risco_perfil, meses_res, avisos, conhecimento_ajustado = calcular_recomendacao(
        prazo=respostas["prazo"],
        risco=respostas["risco"],
        objetivo=respostas["objetivo"],
        fluxo=respostas["fluxo"],
        controle=respostas["controle"],
        liquidez=respostas["liquidez"],
        liquidez_pct=respostas["liquidez_pct"],
        reserva_emerg=respostas["reserva_emerg"],
        idade=respostas["idade"],
        despesas=respostas["despesas"],
        faixa_valor=respostas["faixa_valor"],
        patrim_pct=respostas["patrim_pct"],
        renda=respostas["renda"],
        dividas=respostas["dividas"],
        conhecimento=respostas["conhecimento"],
        experiencia=respostas["experiencia"],
        dependentes=respostas["dependentes"],
        aporte=respostas["aporte"],
        emocional=respostas["emocional"],
        ir_tipo=respostas["ir_tipo"],
        carteira_atual=respostas["carteira_atual"],
        TAXAS=TAXAS,
    )

    portfolio = _build_portfolio(
        nivel_risco_perfil, conhecimento_ajustado, respostas["faixa_valor"],
        respostas["objetivo"], respostas["renda"], respostas["dividas"],
        respostas["dependentes"], respostas["aporte"], respostas["carteira_atual"],
        respostas["ir_tipo"], respostas["fluxo"], respostas["patrim_pct"],
        respostas["liquidez_pct"], respostas["despesas"], respostas["idade"], avisos,
    )

    perfil_exibido, risco_recomendado = _classificar_portfolio_final(portfolio)
    info = _get_prod(perfil_exibido)
    aliq, pgbl = _aliq(perfil_exibido)

    taxa_perfil = sum((pct / 100) * TAXAS[_risco(k)] for k, pct in portfolio.items())
    taxa_pess = max(ipca + 0.02, taxa_perfil * 0.6)

    classes_no_portfolio = {
        _CLASSE[rk] for rk, pct in portfolio.items()
        if pct >= MIN_PCT and rk in _CLASSE
    }

    return {
        "rec_key": rec_key,
        "perfil_exibido": perfil_exibido,
        "perfil_display": _disp(perfil_exibido),
        "portfolio": portfolio,
        "nivel_risco_perfil": nivel_risco_perfil,
        "risco_recomendado": risco_recomendado,
        "info": info,
        "aliq": aliq,
        "pgbl": pgbl,
        "taxa_perfil": taxa_perfil,
        "taxa_pess": taxa_pess,
        "avisos": avisos,
        "meses_res": meses_res,
        "conhecimento_ajustado": conhecimento_ajustado,
        "classes_no_portfolio": classes_no_portfolio,
        "TAXAS": TAXAS,
    }


def buscar_ativos_sugeridos(portfolio: dict, nivel_risco_perfil: int, market: dict) -> tuple[dict, dict]:
    """
    Busca o top 5 de ativos reais e online para cada classe presente no
    portfólio. Devolve (ativos_sugeridos, classes_indisponiveis) sempre
    separados — nunca mistura um aviso de indisponibilidade de fonte com
    um ativo de verdade na mesma lista (sem mock/fallback).
    """
    resultado = recomendar_por_portfolio(
        portfolio, nivel_risco_perfil,
        selic=market["selic"], ipca=market["ipca"], ibov_cagr=market["ibov_cagr"],
    )
    indisponiveis = resultado.pop("_indisponiveis", {})
    return resultado, indisponiveis


def tabela_projecao(
    cap_inicial: float,
    aporte_mensal: float,
    taxa_perfil: float,
    taxa_pess: float,
    ipca: float,
    aliq: float,
    pgbl: bool,
    anos_lista=(1, 2, 5, 10, 20, 30),
) -> list[dict]:
    """Projeção de valor futuro (bruto, líquido, real, pessimista) por ano,
    usada tanto na tabela do terminal quanto no gráfico/tabela do webapp."""
    linhas = []
    for anos in anos_lista:
        vf_b = _vf_bruto(cap_inicial, aporte_mensal, taxa_perfil, anos)
        vf_l = _vf_liquido(cap_inicial, aporte_mensal, taxa_perfil, anos, aliq, pgbl)
        vf_r = _vf_real(vf_l, ipca, anos)
        vf_p = _vf_liquido(cap_inicial, aporte_mensal, taxa_pess, anos, aliq, pgbl)
        linhas.append({
            "anos": anos, "vf_bruto": vf_b, "vf_liquido": vf_l,
            "vf_real": vf_r, "vf_pessimista": vf_p,
        })
    return linhas