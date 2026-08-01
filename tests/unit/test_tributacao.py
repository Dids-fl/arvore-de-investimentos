"""Casos dourados do novo motor tributário."""

from __future__ import annotations

from datetime import date

import pytest

from tributacao import (
    ContextoTributario,
    PrecisaoTributaria,
    calcular_tributacao,
)
from tributacao.regras import imposto_ganho_capital


def contexto(**alteracoes) -> ContextoTributario:
    dados = {
        "principal": 10_000,
        "valor_bruto": 12_000,
        "data_aplicacao": date(2023, 1, 1),
        "data_resgate": date(2026, 1, 2),
        "tipo_produto": "cdb",
    }
    dados.update(alteracoes)
    return ContextoTributario(**dados)


def test_cdb_longo_prazo() -> None:
    resultado = calcular_tributacao(contexto())
    assert resultado.imposto_estimado == pytest.approx(300)
    assert resultado.valor_liquido == pytest.approx(11_700)


def test_lci_pessoa_fisica_isenta() -> None:
    resultado = calcular_tributacao(contexto(tipo_produto="lci"))
    assert resultado.imposto_estimado == 0


@pytest.mark.parametrize(
    ("produto", "imposto"),
    [("pgbl", 1_200), ("vgbl", 200)],
)
def test_previdencia_regressiva_acima_de_dez_anos(
    produto,
    imposto,
) -> None:
    resultado = calcular_tributacao(
        contexto(
            tipo_produto=produto,
            regime="regressivo",
            data_aplicacao=date(2014, 1, 1),
        )
    )
    assert resultado.imposto_estimado == pytest.approx(imposto)


def test_previdencia_progressiva_sem_renda_e_indeterminada() -> None:
    resultado = calcular_tributacao(
        contexto(tipo_produto="vgbl", regime="progressivo")
    )
    assert resultado.precisao == PrecisaoTributaria.INDETERMINADA


def test_previdencia_progressiva_com_renda_e_estimada() -> None:
    resultado = calcular_tributacao(
        contexto(
            tipo_produto="vgbl",
            regime="progressivo",
            renda_tributavel=80_000,
        )
    )
    assert resultado.precisao == PrecisaoTributaria.ESTIMADA
    assert resultado.imposto_estimado is not None


def test_fundo_longo_prazo_informa_aproximacao_de_come_cotas() -> None:
    resultado = calcular_tributacao(
        contexto(
            tipo_produto="fundo_longo_prazo",
            metadados={"come_cotas_pago": 100},
        )
    )
    assert resultado.imposto_estimado == pytest.approx(200)
    assert resultado.precisao == PrecisaoTributaria.ESTIMADA


def test_acao_com_vendas_abaixo_de_vinte_mil() -> None:
    resultado = calcular_tributacao(
        contexto(tipo_produto="acao", valor_vendas_mes=19_999)
    )
    assert resultado.imposto_estimado == 0


def test_fii_usa_aliquota_de_vinte_por_cento_na_venda() -> None:
    resultado = calcular_tributacao(contexto(tipo_produto="fii"))
    assert resultado.imposto_estimado == pytest.approx(400)


def test_cripto_exige_jurisdicao() -> None:
    resultado = calcular_tributacao(contexto(tipo_produto="cripto"))
    assert resultado.precisao == PrecisaoTributaria.INDETERMINADA


def test_cripto_com_custodia_informada_calcula_estimativa() -> None:
    resultado = calcular_tributacao(
        contexto(
            tipo_produto="cripto",
            metadados={"jurisdicao_custodia": "brasil"},
        )
    )
    assert resultado.imposto_estimado == pytest.approx(300)
    assert resultado.precisao == PrecisaoTributaria.ESTIMADA


def test_cripto_exterior_sem_enquadramento_e_indeterminado() -> None:
    resultado = calcular_tributacao(
        contexto(
            tipo_produto="cripto",
            metadados={"jurisdicao_custodia": "exterior"},
        )
    )
    assert resultado.precisao == PrecisaoTributaria.INDETERMINADA
    assert resultado.regra_id == "cripto_exterior_enquadramento_indeterminado"


def test_cripto_exterior_confirmado_usa_aliquota_fixa() -> None:
    resultado = calcular_tributacao(
        contexto(
            principal=1_000_000,
            valor_bruto=13_000_000,
            tipo_produto="cripto",
            metadados={
                "jurisdicao_custodia": "exterior",
                "enquadramento_aplicacao_financeira_exterior_confirmado": (
                    True
                ),
            },
        )
    )
    assert resultado.imposto_estimado == pytest.approx(1_800_000)
    assert resultado.aliquota_efetiva == pytest.approx(0.15)
    assert resultado.regra_id == (
        "cripto_aplicacao_financeira_exterior_2026"
    )


def test_cripto_acumulado_sem_premissa_e_indeterminado() -> None:
    resultado = calcular_tributacao(
        contexto(
            principal=10_000_000,
            valor_bruto=12_000_000,
            tipo_produto="cripto",
            metadados={
                "jurisdicao_custodia": "brasil",
                "ganho_acumulado_ano": 6_000_000,
            },
        )
    )
    assert resultado.precisao == PrecisaoTributaria.INDETERMINADA
    assert resultado.regra_id == "cripto_acumulacao_indeterminada"


def test_cripto_acumulado_com_premissa_calcula_incremento() -> None:
    resultado = calcular_tributacao(
        contexto(
            principal=10_000_000,
            valor_bruto=12_000_000,
            tipo_produto="cripto",
            metadados={
                "jurisdicao_custodia": "brasil",
                "ganho_acumulado_ano": 6_000_000,
                "alienacoes_parciais_mesmo_bem_confirmadas": True,
            },
        )
    )
    assert resultado.imposto_estimado == pytest.approx(325_000)
    assert resultado.aliquota_efetiva == pytest.approx(0.1625)
    assert resultado.regra_id == "cripto_ganho_capital_brasil_2026"


def test_cripto_rejeita_confirmacao_textual() -> None:
    with pytest.raises(TypeError, match="deve ser booleano"):
        calcular_tributacao(
            contexto(
                tipo_produto="cripto",
                metadados={
                    "jurisdicao_custodia": "exterior",
                    "enquadramento_aplicacao_financeira_exterior_confirmado": (
                        "sim"
                    ),
                },
            )
        )


def test_cri_estruturado_e_isento_para_pessoa_fisica() -> None:
    resultado = calcular_tributacao(contexto(tipo_produto="cri"))
    assert resultado.imposto_estimado == 0


def test_estruturado_sem_subtipo_nao_recebe_fallback() -> None:
    resultado = calcular_tributacao(contexto(tipo_produto="estruturado"))
    assert resultado.precisao == PrecisaoTributaria.INDETERMINADA


def test_produto_desconhecido_nao_recebe_aliquota_inventada() -> None:
    resultado = calcular_tributacao(contexto(tipo_produto="produto_x"))
    assert resultado.imposto_estimado is None
    assert resultado.valor_liquido is None


def test_ganho_de_capital_usa_faixas_progressivas() -> None:
    esperado = 5_000_000 * 0.15 + 1_000_000 * 0.175
    assert imposto_ganho_capital(6_000_000) == pytest.approx(esperado)