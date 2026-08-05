"""Testes do critério secundário de eficiência líquida."""

from __future__ import annotations

from datetime import date

import pytest

from core.ranking_liquido import (
    avaliar_fundo_liquido,
    beneficios_fiscais_pgbl,
    combinar_scores,
    comparar_pgbl_vgbl,
)


def test_beneficio_pgbl_respeita_limite_e_valor_ja_utilizado() -> None:
    beneficios = beneficios_fiscais_pgbl(
        50_000,
        0,
        1,
        data_referencia=date(2026, 7, 1),
        renda_tributavel_anual=100_000,
        elegibilidade_confirmada=True,
        deducao_ja_utilizada_primeiro_ano=2_000,
    )

    assert len(beneficios) == 1
    assert beneficios[0]["deducao_utilizada"] == pytest.approx(10_000)
    assert beneficios[0]["beneficio_fiscal"] == pytest.approx(2_750)


def test_beneficio_pgbl_nao_e_inferido_sem_confirmacao() -> None:
    assert beneficios_fiscais_pgbl(
        10_000,
        500,
        10,
        data_referencia=date(2026, 1, 1),
        renda_tributavel_anual=100_000,
        elegibilidade_confirmada=False,
    ) == []


def test_comparacao_pgbl_inclui_beneficio_confirmado() -> None:
    comparacao = comparar_pgbl_vgbl(
        6_000,
        500,
        0.10,
        10,
        data_referencia=date(2026, 1, 1),
        regime="regressivo",
        renda_tributavel_anual=100_000,
        declaracao_completa=True,
        elegibilidade_deducao_pgbl=True,
    )

    assert comparacao["aplicado"] is True
    assert comparacao["produto_escolhido"] == "pgbl"
    pgbl = comparacao["alternativas"]["pgbl"]
    vgbl = comparacao["alternativas"]["vgbl"]
    assert pgbl["beneficio_fiscal_total"] > 0
    assert pgbl["tir_liquida_anual"] > vgbl["tir_liquida_anual"]
    assert comparacao["adequacao_pre_filtrada"] is True
    assert comparacao["criterio_desempate"] == "maior_tir_liquida_anual"


def test_comparacao_nao_credita_beneficio_nao_confirmado() -> None:
    comparacao = comparar_pgbl_vgbl(
        6_000,
        500,
        0.10,
        10,
        data_referencia=date(2026, 1, 1),
        regime="regressivo",
        renda_tributavel_anual=100_000,
        declaracao_completa=True,
        elegibilidade_deducao_pgbl=None,
    )

    assert comparacao["aplicado"] is True
    assert comparacao["alternativas"]["pgbl"][
        "beneficio_fiscal_total"
    ] == 0
    assert comparacao["produto_escolhido"] == "vgbl"


def test_beneficio_pgbl_separa_aportes_por_ano_calendario() -> None:
    beneficios = beneficios_fiscais_pgbl(
        1_000,
        1_000,
        1,
        data_referencia=date(2026, 7, 1),
        renda_tributavel_anual=200_000,
        elegibilidade_confirmada=True,
    )

    por_ano = {int(item["ano"]): item for item in beneficios}
    assert por_ano[2026]["contribuicao_pgbl"] == pytest.approx(6_000)
    assert por_ano[2027]["contribuicao_pgbl"] == pytest.approx(7_000)
    assert por_ano[2026]["mes_recebimento"] == 6
    assert por_ano[2027]["mes_recebimento"] == 12


def test_beneficio_pgbl_aceita_renda_especifica_por_ano() -> None:
    beneficios = beneficios_fiscais_pgbl(
        0,
        2_000,
        1,
        data_referencia=date(2026, 7, 1),
        renda_tributavel_anual=100_000,
        renda_tributavel_por_ano={2027: 200_000},
        elegibilidade_confirmada=True,
    )

    por_ano = {int(item["ano"]): item for item in beneficios}
    assert por_ano[2026]["deducao_utilizada"] == pytest.approx(10_000)
    assert por_ano[2027]["deducao_utilizada"] == pytest.approx(14_000)


def test_fundo_de_longo_prazo_supera_curto_com_mesmo_retorno() -> None:
    dados = {"cagr": 0.10}
    longo = avaliar_fundo_liquido(
        {**dados, "classe": "Renda Fixa"},
        prazo_anos=5,
        data_referencia=date(2026, 1, 1),
        retorno_esperado_anual=0.10,
    )
    curto = avaliar_fundo_liquido(
        {**dados, "classe": "Curto Prazo"},
        prazo_anos=5,
        data_referencia=date(2026, 1, 1),
        retorno_esperado_anual=0.10,
    )

    assert longo["aplicado"] is True
    assert curto["aplicado"] is True
    assert longo["retorno_liquido_anual"] > curto["retorno_liquido_anual"]


def test_fundo_nao_transforma_historico_em_previsao() -> None:
    resultado = avaliar_fundo_liquido(
        {
            "classe": "Renda Fixa",
            "cagr": 0.30,
            "retorno_12m": 0.40,
        },
        prazo_anos=5,
        data_referencia=date(2026, 1, 1),
        retorno_esperado_anual=None,
    )

    assert resultado["aplicado"] is False
    assert "não foi usado como previsão" in resultado["motivo"]


def test_fundo_nao_desconta_novamente_despesa_ja_refletida_na_cota() -> None:
    base = {
        "classe": "Renda Fixa",
        "cagr": 0.10,
    }
    sem_taxa = avaliar_fundo_liquido(
        base,
        prazo_anos=5,
        data_referencia=date(2026, 1, 1),
        retorno_esperado_anual=0.10,
    )
    com_metadado_de_taxa = avaliar_fundo_liquido(
        {
            **base,
            "taxa_administracao": 0.02,
            "taxa_performance": 0.20,
        },
        prazo_anos=5,
        data_referencia=date(2026, 1, 1),
        retorno_esperado_anual=0.10,
    )

    assert com_metadado_de_taxa == sem_taxa
    assert sem_taxa["retorno_cota_liquido_despesas_fundo"] is True


def test_score_liquido_nao_domina_adequacao() -> None:
    assert combinar_scores(9.0, 1.0) == pytest.approx(7.8)
    assert combinar_scores(1.0, 9.0) == pytest.approx(2.2)
