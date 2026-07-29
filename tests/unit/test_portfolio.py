"""Invariantes da construção e classificação de carteiras."""

from __future__ import annotations

import pytest

portfolio = pytest.importorskip("portfolio")
categorias = pytest.importorskip("core.categorias")
RK = categorias.RK


def test_norm_soma_exatamente_cem() -> None:
    resultado = portfolio._norm({"a": 1, "b": 1, "c": 1})
    assert sum(resultado.values()) == 100
    assert max(resultado.values()) - min(resultado.values()) <= 1


def test_norm_remove_posicoes_zeradas() -> None:
    resultado = portfolio._norm({RK.RF: 70, RK.RV: 30, "zero": 0})
    assert resultado == {RK.RF: 70, RK.RV: 30}


def test_norm_rejeita_percentual_negativo() -> None:
    with pytest.raises(ValueError):
        portfolio._norm({RK.RF: 110, RK.RV: -10})


def test_mover_rv_para_rf_preserva_total() -> None:
    carteira = {RK.RF: 40, RK.RV: 60}
    assert portfolio.mover_rv_para_rf(carteira, 20)
    assert carteira[RK.RF] == pytest.approx(60)
    assert carteira[RK.RV] == pytest.approx(40)
    assert sum(carteira.values()) == pytest.approx(100)


def test_classificacao_conservadora() -> None:
    categoria, risco = portfolio._classificar_portfolio_final({RK.RF: 100})
    assert categoria == RK.RF
    assert risco == 1
