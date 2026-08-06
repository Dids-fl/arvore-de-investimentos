"""Garante que ações e units não contaminem o universo de FIIs."""

from __future__ import annotations

from acoes_fiis import screener
from acoes_fiis.apis import fundamentus_scraper
from cli import DEMO_PADRAO


def test_demo_usa_zero_nos_novos_campos() -> None:
    assert DEMO_PADRAO["despesas_essenciais_mensais"] == 0.0
    assert DEMO_PADRAO["reserva_atual"] == 0.0


def test_universo_fii_vem_da_pagina_dedicada(monkeypatch) -> None:
    html = b"""
    <table id="resultado">
      <thead><tr>
        <th>Papel</th><th>Segmento</th><th>Cotacao</th>
        <th>Dividend Yield</th><th>P/VP</th><th>Liquidez</th>
      </tr></thead>
      <tbody><tr>
        <td>HGLG11</td><td>Logistica</td><td>160,00</td>
        <td>8,50%</td><td>0,95</td><td>2500000</td>
      </tr></tbody>
    </table>
    """.replace(b"Cotacao", "Cotação".encode()).replace(
        b"Logistica",
        "Logística".encode(),
    )

    def obter(url: str) -> bytes:
        assert url.endswith("/fii_resultado.php")
        return html

    monkeypatch.setattr(fundamentus_scraper, "get_raw_data", obter)

    resultado = fundamentus_scraper.get_fiis_bulk()

    assert set(resultado) == {"HGLG11"}
    assert resultado["HGLG11"]["tipo_ativo"] == "fii"
    assert resultado["HGLG11"]["fonte_classificacao"] == (
        "Fundamentus/FIIs"
    )


def test_validador_rejeita_unit_mesmo_terminando_em_11() -> None:
    ativos = [
        {
            "ticker": "SANB11",
            "tipo_ativo": "unit",
            "dy": 7.8,
            "pvp": 1.12,
        },
        {
            "ticker": "HGLG11",
            "tipo_ativo": "fii",
            "dy": 8.5,
            "pvp": 0.95,
        },
    ]

    resultado = screener._validar_fiis(ativos)

    assert [item["ticker"] for item in resultado] == ["HGLG11"]
