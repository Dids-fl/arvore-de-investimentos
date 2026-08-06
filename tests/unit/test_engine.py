"""Contrato da operação de alto nível do engine."""

from __future__ import annotations

import json
from datetime import date

import pytest

engine = pytest.importorskip("engine")
RK = pytest.importorskip("core.categorias").RK


def test_taxas_por_risco_usam_curva_selic_focus_e_ibov(
    mercado_valido,
) -> None:
    data_base = date(2026, 7, 29)

    taxas = engine.taxas_por_risco(
        mercado_valido,
        prazo_meses=12,
        data_referencia=data_base,
    )
    taxa_base = engine.taxa_base_mercado(
        mercado_valido,
        prazo_meses=12,
        data_referencia=data_base,
    )

    assert taxas[1] == pytest.approx(taxa_base)
    assert taxas[2] == pytest.approx(
        (taxa_base + mercado_valido["ibov_cagr"]) / 2
    )
    assert taxas[3] == pytest.approx(
        mercado_valido["ibov_cagr"]
    )


def test_curva_selic_muda_conforme_o_prazo(
    mercado_valido,
) -> None:
    data_base = date(2026, 7, 29)

    taxa_12_meses = engine.taxa_base_mercado(
        mercado_valido,
        prazo_meses=12,
        data_referencia=data_base,
    )
    taxa_60_meses = engine.taxa_base_mercado(
        mercado_valido,
        prazo_meses=60,
        data_referencia=data_base,
    )

    assert taxa_60_meses < taxa_12_meses


def test_criar_analise_entrega_contrato_completo(
    respostas_padrao,
    mercado_valido,
) -> None:
    analise = engine.criar_analise(
        respostas_padrao,
        mercado_valido,
        data_referencia=date(2026, 7, 29),
    )
    resultado = analise["resultado"]

    assert sum(resultado["portfolio"].values()) == 100
    assert len(analise["projecoes"]) == 6
    assert len(analise["serie_projecao"]) == 30
    assert analise["meta"] is not None
    assert resultado["portfolio_itens"]
    assert resultado["perfil_resumo"]

    assert resultado["metodo_taxa_base"] == (
        "curva_selic_focus_composta"
    )
    assert resultado["prazo_taxa_meses"] == 120


def test_sem_reserva_concentra_carteira_em_liquidez(
    respostas_padrao,
    mercado_valido,
) -> None:
    respostas = {
        **respostas_padrao,
        "reserva_emerg": "não tenho",
        "despesas_essenciais_mensais": 2_000,
        "reserva_atual": 0,
        "renda": "sem renda",
        "patrim_pct": "alto",
        "conhecimento": "iniciante",
        "experiencia": ["nenhum"],
        "aporte": "único",
        "aporte_mensal": 0,
        "modo_meta": "rendendo",
    }

    analise = engine.criar_analise(
        respostas,
        mercado_valido,
        data_referencia=date(2026, 7, 29),
    )
    resultado = analise["resultado"]

    assert resultado["rec_key"] == RK.RF_RESERVA
    assert resultado["portfolio"] == {RK.RF_RESERVA: 100.0}
    assert resultado["classes_no_portfolio"] == {"rf"}
    assert any(
        "Todo o capital inicial é necessário" in aviso
        for aviso in resultado["avisos"]
    )


def test_sem_despesas_nao_inventa_deficit_de_reserva(
    respostas_padrao,
    mercado_valido,
) -> None:
    respostas = {
        **respostas_padrao,
        "reserva_emerg": "não tenho",
        "despesas": "nenhuma",
        "despesas_essenciais_mensais": 0,
        "reserva_atual": 0,
        "renda": "sem renda",
        "patrim_pct": "alto",
        "conhecimento": "iniciante",
        "experiencia": ["nenhum"],
        "aporte": "único",
        "aporte_mensal": 0,
        "modo_meta": "rendendo",
    }

    analise = engine.criar_analise(
        respostas,
        mercado_valido,
        data_referencia=date(2026, 7, 29),
    )
    resultado = analise["resultado"]

    assert resultado["plano_reserva"]["deficit"] == 0
    assert resultado["portfolio"] != {RK.RF_RESERVA: 100.0}
    assert len(resultado["portfolio"]) > 1
    assert sum(resultado["portfolio"].values()) == pytest.approx(100)


def test_deficit_parcial_preserva_capital_excedente_diversificado(
    respostas_padrao,
    mercado_valido,
) -> None:
    respostas = {
        **respostas_padrao,
        "reserva_emerg": "não tenho",
        "despesas": "baixas",
        "despesas_essenciais_mensais": 500,
        "reserva_atual": 0,
        "renda": "sem renda",
        "cap_inicial": 6_000,
        "aporte": "único",
        "aporte_mensal": 0,
        "modo_meta": "rendendo",
    }

    analise = engine.criar_analise(
        respostas,
        mercado_valido,
        data_referencia=date(2026, 7, 29),
    )
    resultado = analise["resultado"]

    assert resultado["plano_reserva"]["valor_alvo"] == 3_000
    assert resultado["plano_reserva"]["deficit"] == 3_000
    assert resultado["plano_reserva"]["percentual_capital"] == 50
    assert resultado["portfolio"][RK.RF_RESERVA] >= 50
    assert len(resultado["portfolio"]) > 1
    assert sum(resultado["portfolio"].values()) == pytest.approx(100)


def test_exportacao_e_serializavel(
    respostas_padrao,
    mercado_valido,
) -> None:
    analise = engine.criar_analise(
        respostas_padrao,
        mercado_valido,
        data_referencia=date(2026, 7, 29),
    )
    payload = engine.montar_payload_exportacao(analise)

    serializado = json.dumps(
        payload,
        ensure_ascii=False,
        default=str,
    )

    assert "recomendacao" in serializado
    assert payload["portfolio"] == analise["resultado"]["portfolio"]
    assert payload["tributacao"]["data_referencia"]
    assert payload["tributacao"]["horizontes"]

    taxas = payload["taxas_utilizadas"]
    assert taxas["metodo_taxa_base"] == (
        "curva_selic_focus_composta"
    )
    assert taxas["focus_selic_por_ano_pct"]


def test_engine_ignora_campos_inativos(
    respostas_padrao,
    mercado_valido,
) -> None:
    respostas = {
        **respostas_padrao,
        "liquidez": "não",
        "liquidez_pct": 90,
        "aporte": "único",
        "aporte_mensal": 5_000,
        "modo_meta": "rendendo",
    }

    analise = engine.criar_analise(
        respostas,
        mercado_valido,
        data_referencia=date(2026, 7, 29),
    )

    assert analise["respostas"]["liquidez_pct"] == 0
    assert analise["respostas"]["aporte_mensal"] == 0
    assert analise["meta"] is None


def test_meta_exige_valor_e_prazo(
    respostas_padrao,
    mercado_valido,
) -> None:
    respostas = {
        **respostas_padrao,
        "meta_valor": None,
        "meta_prazo": None,
    }

    with pytest.raises(ValueError, match="meta_valor"):
        engine.criar_analise(
            respostas,
            mercado_valido,
            data_referencia=date(2026, 7, 29),
        )


def test_engine_nao_agrega_liquido_com_classe_indeterminada() -> None:
    projecao = engine.projetar_portfolio(
        10_000,
        0,
        {RK.RF_SELIC_CDB: 80, RK.RV_CRIPTO: 20},
        {1: 0.10, 2: 0.11, 3: 0.12},
        0.04,
        5,
        data_referencia=date(2026, 1, 1),
        contexto_fiscal={"pessoa_fisica": True},
    )

    assert projecao["bruto"] > 0
    assert projecao["liquido"] is None
    assert projecao["imposto_estimado"] is None
    assert projecao["bruto_indeterminado"] > 0


def test_engine_calcula_cripto_com_jurisdicao_explicita() -> None:
    projecao = engine.projetar_portfolio(
        10_000,
        0,
        {RK.RV_CRIPTO: 100},
        {1: 0.10, 2: 0.11, 3: 0.12},
        0.04,
        5,
        data_referencia=date(2026, 1, 1),
        contexto_fiscal={
            "pessoa_fisica": True,
            "jurisdicao_cripto": "brasil",
        },
    )

    assert projecao["liquido"] is not None
    assert projecao["imposto_estimado"] is not None
    assert projecao["precisao_tributaria"] == "estimada"


def test_engine_escolhe_pgbl_quando_beneficio_supera_vgbl(
    respostas_padrao,
    mercado_valido,
) -> None:
    respostas = {
        **respostas_padrao,
        "objetivo": "aposentadoria",
        "ir_tipo": "completo",
        "regime_previdencia": "regressivo",
        "elegibilidade_deducao_pgbl": True,
        "renda_tributavel_anual": 100_000,
        "valor_aportes_ano": 0,
    }

    analise = engine.criar_analise(
        respostas,
        mercado_valido,
        data_referencia=date(2026, 7, 29),
    )
    ranking = analise["resultado"]["ranking_previdencia_liquida"]

    assert ranking["aplicado"] is True
    assert ranking["produto_escolhido"] == "pgbl"
    assert RK.PREV_PGBL in analise["resultado"]["portfolio"]


def test_engine_prefere_vgbl_sem_beneficio_pgbl_confirmado(
    respostas_padrao,
    mercado_valido,
) -> None:
    respostas = {
        **respostas_padrao,
        "objetivo": "aposentadoria",
        "ir_tipo": "completo",
        "regime_previdencia": "regressivo",
        "elegibilidade_deducao_pgbl": None,
        "renda_tributavel_anual": 100_000,
    }

    analise = engine.criar_analise(
        respostas,
        mercado_valido,
        data_referencia=date(2026, 7, 29),
    )
    ranking = analise["resultado"]["ranking_previdencia_liquida"]

    assert ranking["produto_escolhido"] == "vgbl"
    assert RK.PREV_VGBL in analise["resultado"]["portfolio"]


def test_busca_de_fundos_recebe_taxa_cenario_do_engine(monkeypatch) -> None:
    recebidos = {}

    def recomendar(portfolio, perfil, **kwargs):
        recebidos.update(
            {
                "portfolio": portfolio,
                "perfil": perfil,
                **kwargs,
            }
        )
        return {"fundos": [], "_indisponiveis": {}}

    monkeypatch.setattr(engine, "recomendar_por_portfolio", recomendar)
    analise = {
        "resultado": {
            "portfolio_busca": {RK.FUNDOS: 100},
            "nivel_risco_perfil": 2,
            "prazo_taxa_meses": 60,
            "taxa_perfil": 0.11,
        },
        "market": {"selic": 0.10, "ipca": 0.04, "ibov_cagr": 0.12},
        "meta": None,
        "data_referencia": "2026-07-29",
    }

    engine.buscar_ativos_da_analise(analise, n=3)

    assert recebidos["retorno_esperado_fundos"] == pytest.approx(0.11)
    assert recebidos["prazo_anos"] == pytest.approx(5)
