"""Regra de FIIs validada historicamente: liquidez, sem DY extremo nem P/VP baixo."""

from __future__ import annotations

import pytest

screener = pytest.importorskip("acoes_fiis.screener")


def _fii(**valores):
    return {"tipo_ativo": "fii", "dy": 10.0, "pvp": 0.95, "liquidez": 5_000_000, **valores}


def test_mais_liquido_vence() -> None:
    grande, _ = screener._score_fii(_fii(liquidez=15_000_000), 2, dy_mediana=10.0)
    pequeno, _ = screener._score_fii(_fii(liquidez=400_000), 2, dy_mediana=10.0)
    assert grande > pequeno


def test_dy_muito_acima_dos_pares_e_excluido() -> None:
    score, motivos = screener._score_fii(_fii(dy=16.0, liquidez=20_000_000), 2, dy_mediana=10.0)
    assert score == 0
    assert "mediana" in motivos[0]


def test_desconto_forte_sobre_patrimonio_e_excluido() -> None:
    score, motivos = screener._score_fii(_fii(pvp=0.7), 1, dy_mediana=10.0)
    assert score == 0
    assert "P/VP" in motivos[0]


def test_perfis_usam_a_mesma_regra() -> None:
    fii = _fii()
    assert len({screener._score_fii(fii, p, 10.0)[0] for p in (1, 2, 3)}) == 1


def test_top_fiis_aplica_mediana_do_universo(monkeypatch) -> None:
    universo = {
        "AAAA11": _fii(ticker="AAAA11", dy=9.0, liquidez=10_000_000),
        "BBBB11": _fii(ticker="BBBB11", dy=10.0, liquidez=3_000_000),
        "CCCC11": _fii(ticker="CCCC11", dy=11.0, liquidez=2_000_000),
        "DDDD11": _fii(ticker="DDDD11", dy=18.0, liquidez=30_000_000),  # DY extremo
    }
    monkeypatch.setattr(screener, "get_fiis_bulk", lambda: universo)
    monkeypatch.setattr(screener, "listar_tickers", lambda: {})

    resultado = screener.top_fiis(2, n=4)

    assert [f["ticker"] for f in resultado][:3] == ["AAAA11", "BBBB11", "CCCC11"]
    assert resultado[-1]["ticker"] == "DDDD11" and resultado[-1]["score"] == 0
