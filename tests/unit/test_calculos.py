"""Propriedades básicas da matemática financeira."""

from __future__ import annotations

import math
from datetime import date

import pytest

from calculos import (
    _vf_bruto,
    _vf_liquido,
    _vf_liquido_tributado,
    _vf_real,
)


def test_valor_futuro_sem_aportes() -> None:
    assert _vf_bruto(1_000, 0, 0.10, 5) == pytest.approx(1_610.51)


def test_taxa_zero_soma_aportes_mensais() -> None:
    assert _vf_bruto(1_000, 100, 0.0, 2) == pytest.approx(3_400)


def test_imposto_comum_incide_somente_sobre_ganho() -> None:
    bruto = _vf_bruto(10_000, 0, 0.10, 2)
    liquido = _vf_liquido(10_000, 0, 0.10, 2, 0.15)
    ganho = bruto - 10_000
    assert liquido == pytest.approx(bruto - ganho * 0.15)


def test_pgbl_incide_sobre_saldo_total() -> None:
    bruto = _vf_bruto(10_000, 0, 0.10, 2)
    liquido = _vf_liquido(10_000, 0, 0.10, 2, 0.10, pgbl=True)
    assert liquido == pytest.approx(bruto * 0.90)


def test_valor_real_remove_inflacao_composta() -> None:
    nominal = 10_000 * (1.04**10)
    assert _vf_real(nominal, 0.04, 10) == pytest.approx(10_000)


@pytest.mark.parametrize(
    ("funcao", "argumentos"),
    [
        (_vf_bruto, (-1, 0, 0.1, 1)),
        (_vf_bruto, (1, -1, 0.1, 1)),
        (_vf_bruto, (1, 0, -1.0, 1)),
        (_vf_real, (1, -1.0, 1)),
        (_vf_real, (1, 0.1, -1)),
    ],
)
def test_entradas_invalidas_sao_rejeitadas(funcao, argumentos) -> None:
    with pytest.raises((TypeError, ValueError)):
        funcao(*argumentos)


def test_resultados_sao_finitos() -> None:
    resultado = _vf_bruto(1_000, 100, 0.12, 30)
    assert math.isfinite(resultado)
    assert resultado > 1_000 + 100 * 360


def test_motor_tributario_liquida_cada_aporte_de_cdb() -> None:
    resultado = _vf_liquido_tributado(
        1_000,
        100,
        0.10,
        3,
        "cdb",
        data_referencia=date(2026, 1, 1),
    )
    assert resultado["quantidade_lotes"] == 37
    assert resultado["imposto_estimado"] is not None
    assert resultado["liquido"] < resultado["bruto"]
    assert resultado["lotes_indeterminados"] == 0


def test_motor_nao_inventa_tributacao_para_cripto_sem_jurisdicao() -> None:
    resultado = _vf_liquido_tributado(
        10_000,
        0,
        0.10,
        2,
        "cripto",
        data_referencia=date(2026, 1, 1),
    )
    assert resultado["imposto_estimado"] is None
    assert resultado["liquido"] is None
    assert resultado["bruto_indeterminado"] == pytest.approx(
        resultado["bruto"]
    )