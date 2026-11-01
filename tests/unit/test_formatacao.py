"""Formatação e leitura de valores no padrão brasileiro."""

from __future__ import annotations

import pytest

from utils.formatacao import formatar_brl, interpretar_numero


@pytest.mark.parametrize(
    ("valor", "casas", "esperado"),
    [
        (1234.5, 2, "R$ 1.234,50"),
        (0, 2, "R$ 0,00"),
        (1_000_000, 0, "R$ 1.000.000"),
        (-2500.75, 2, "-R$ 2.500,75"),
        (-0.001, 2, "R$ 0,00"),
    ],
)
def test_formatar_brl(valor, casas, esperado) -> None:
    assert formatar_brl(valor, casas) == esperado


@pytest.mark.parametrize("valor", [None, "10", True, float("nan"), float("inf")])
def test_formatar_brl_valor_invalido(valor) -> None:
    assert formatar_brl(valor) == "indeterminado"


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("1.000", 1000.0),
        ("1.000,50", 1000.5),
        ("1500,5", 1500.5),
        ("1500.5", 1500.5),
        ("R$ 2.000", 2000.0),
        ("12.345.678", 12_345_678.0),
        ("0,1", 0.1),
        ("-3,5", -3.5),
    ],
)
def test_interpretar_numero(texto, esperado) -> None:
    assert interpretar_numero(texto) == pytest.approx(esperado)


@pytest.mark.parametrize("texto", ["", "   ", "abc", "1,2,3"])
def test_interpretar_numero_invalido(texto) -> None:
    with pytest.raises(ValueError):
        interpretar_numero(texto)
