"""Testes das projeções tributárias que dependem da ordem dos fluxos."""

from __future__ import annotations

from datetime import date

import pytest

from calculos import _vf_bruto, _vf_liquido_tributado
from core.categorias import RK
from engine import projetar_portfolio
from tributacao.projecoes import projetar_come_cotas


def test_come_cotas_sem_rendimento_nao_reduz_saldo() -> None:
    projecao = projetar_come_cotas(
        10_000,
        100,
        0.0,
        24,
        data_referencia=date(2026, 1, 15),
        tipo_produto="fundo_longo_prazo",
    )

    assert projecao.come_cotas_pago == 0
    assert projecao.imposto_total == 0
    assert projecao.valor_liquido == pytest.approx(12_400)
    assert projecao.custo_oportunidade_come_cotas == 0


def test_come_cotas_conta_eventos_futuros_de_maio_e_novembro() -> None:
    projecao = projetar_come_cotas(
        10_000,
        500,
        0.10,
        36,
        data_referencia=date(2026, 1, 15),
        tipo_produto="fundo_longo_prazo",
    )

    assert projecao.eventos_come_cotas == 6
    assert projecao.quantidade_lotes == 37
    assert projecao.come_cotas_pago > 0
    assert projecao.imposto_total > projecao.come_cotas_pago
    assert projecao.valor_liquido < projecao.bruto_sem_tributos
    assert projecao.custo_oportunidade_come_cotas > 0


def test_sem_evento_futuro_nao_gera_custo_de_antecipacao() -> None:
    projecao = projetar_come_cotas(
        10_000,
        0,
        0.10,
        3,
        data_referencia=date(2026, 1, 15),
        tipo_produto="fundo_longo_prazo",
    )

    assert projecao.eventos_come_cotas == 0
    assert projecao.come_cotas_pago == 0
    assert projecao.custo_oportunidade_come_cotas == 0
    assert projecao.valor_liquido == pytest.approx(
        projecao.bruto_sem_tributos - projecao.imposto_total
    )


def test_come_cotas_rejeita_fundo_sem_tributacao_periodica() -> None:
    with pytest.raises(ValueError, match="tipo_produto"):
        projetar_come_cotas(
            10_000,
            0,
            0.10,
            12,
            data_referencia=date(2026, 1, 15),
            tipo_produto="fundo_acoes",
        )


def test_projecao_liquida_de_fundo_usa_come_cotas_prospectivo() -> None:
    resultado = _vf_liquido_tributado(
        10_000,
        500,
        0.10,
        3,
        "fundo_longo_prazo",
        data_referencia=date(2026, 1, 15),
    )

    assert resultado["metodo_tributacao"] == (
        "come_cotas_prospectivo_por_lote"
    )
    assert resultado["eventos_come_cotas"] == 6
    assert resultado["come_cotas_estimado"] > 0
    assert resultado["custo_oportunidade_come_cotas"] > 0
    assert resultado["bruto"] == pytest.approx(
        _vf_bruto(10_000, 500, 0.10, 3)
    )


def test_come_cotas_historico_explicito_preserva_motor_de_resgate() -> None:
    resultado = _vf_liquido_tributado(
        10_000,
        0,
        0.10,
        3,
        "fundo_longo_prazo",
        data_referencia=date(2026, 1, 15),
        metadados={"come_cotas_pago": 100.0},
    )

    assert resultado["metodo_tributacao"] == "lotes_individuais"
    assert "eventos_come_cotas" not in resultado


def test_previdencia_regressiva_liquida_cada_aporte_por_idade() -> None:
    resultado = _vf_liquido_tributado(
        10_000,
        500,
        0.08,
        12,
        "pgbl",
        data_referencia=date(2026, 1, 15),
        regime="regressivo",
    )

    assert resultado["quantidade_lotes"] == 145
    assert resultado["metodo_tributacao"] == "lotes_individuais"
    assert resultado["aliquotas_efetivas"] == [
        0.10,
        0.15,
        0.20,
        0.25,
        0.30,
        0.35,
    ]
    assert any(
        "lote individual" in premissa
        for premissa in resultado["premissas"]
    )
    assert not any(
        "Todo o saldo" in premissa
        for premissa in resultado["premissas"]
    )


def test_pgbl_tributa_mais_que_vgbl_nos_mesmos_lotes() -> None:
    argumentos = {
        "cap": 10_000,
        "ap": 500,
        "taxa_a": 0.08,
        "anos": 12,
        "data_referencia": date(2026, 1, 15),
        "regime": "regressivo",
    }
    pgbl = _vf_liquido_tributado(
        tipo_produto="pgbl",
        **argumentos,
    )
    vgbl = _vf_liquido_tributado(
        tipo_produto="vgbl",
        **argumentos,
    )

    assert pgbl["imposto_estimado"] > vgbl["imposto_estimado"]
    assert pgbl["liquido"] < vgbl["liquido"]


def test_engine_integra_come_cotas_na_classe_de_fundos() -> None:
    projecao = projetar_portfolio(
        10_000,
        500,
        {RK.FUNDOS_RF: 100},
        {1: 0.10, 2: 0.11, 3: 0.12},
        0.04,
        3,
        data_referencia=date(2026, 1, 15),
        contexto_fiscal={"pessoa_fisica": True},
    )
    detalhe = projecao["tributacao_por_classe"][RK.FUNDOS_RF]

    assert projecao["liquido"] is not None
    assert detalhe["metodo_tributacao"] == (
        "come_cotas_prospectivo_por_lote"
    )
    assert detalhe["eventos_come_cotas"] == 6
    assert detalhe["come_cotas_estimado"] > 0


def test_previdencia_importa_idade_e_custo_dos_lotes_existentes() -> None:
    resultado = _vf_liquido_tributado(
        10_000,
        0,
        0.08,
        2,
        "vgbl",
        data_referencia=date(2026, 7, 1),
        regime="regressivo",
        metadados={
            "lotes_previdencia_existentes": [
                {
                    "principal": 6_000,
                    "saldo_atual": 10_000,
                    "data_aplicacao": "2017-07-01",
                }
            ]
        },
    )

    assert resultado["quantidade_lotes_importados"] == 1
    assert resultado["capital_atual_inicio"] == pytest.approx(10_000)
    assert resultado["principal"] == pytest.approx(6_000)
    assert resultado["aliquotas_efetivas"] == [0.10]


def test_lotes_previdencia_exigem_soma_igual_ao_capital_atual() -> None:
    with pytest.raises(ValueError, match="soma de saldo_atual"):
        _vf_liquido_tributado(
            10_000,
            0,
            0.08,
            2,
            "pgbl",
            data_referencia=date(2026, 7, 1),
            regime="regressivo",
            metadados={
                "lotes_previdencia_existentes": [
                    {
                        "principal": 5_000,
                        "saldo_atual": 9_000,
                        "data_aplicacao": "2020-07-01",
                    }
                ]
            },
        )


def test_come_cotas_continua_do_estado_tributario_importado() -> None:
    resultado = _vf_liquido_tributado(
        10_000,
        0,
        0.10,
        2,
        "fundo_longo_prazo",
        data_referencia=date(2026, 7, 1),
        metadados={
            "lotes_fundo_existentes": [
                {
                    "principal": 8_000,
                    "saldo_atual": 10_000,
                    "base_tributaria_atual": 9_800,
                    "ganho_antecipado": 1_800,
                    "come_cotas_pago_historico": 270,
                    "data_aplicacao": "2024-01-10",
                }
            ]
        },
    )

    assert resultado["come_cotas_historico_informado"] == pytest.approx(270)
    assert resultado["come_cotas_estimado"] > 0
    assert resultado["eventos_come_cotas"] == 4
    assert resultado["quantidade_lotes"] == 1


def test_come_cotas_respeita_feriado_adicional_informado() -> None:
    projecao = projetar_come_cotas(
        10_000,
        0,
        0.10,
        12,
        data_referencia=date(2027, 1, 1),
        tipo_produto="fundo_longo_prazo",
        feriados_adicionais=["2027-05-31"],
        anos_calendario_confirmados=[2027],
    )

    assert "2027-05-28" in projecao.datas_eventos_come_cotas
    assert projecao.anos_sem_calendario_confirmado == ()
