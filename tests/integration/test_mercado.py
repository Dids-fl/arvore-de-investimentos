"""Integração do coletor usando respostas simuladas, sem internet."""

from __future__ import annotations

import datetime as dt
import os
import time

import pytest

mercado = pytest.importorskip("mercado")


def test_sgs_escolhe_valor_valido_mais_recente(
    monkeypatch,
) -> None:
    hoje = dt.date.today()
    ontem = hoje - dt.timedelta(days=1)
    futuro = hoje + dt.timedelta(days=1)

    monkeypatch.setattr(
        mercado,
        "_json_get",
        lambda *args, **kwargs: [
            {
                "data": ontem.strftime("%d/%m/%Y"),
                "valor": "10,00",
            },
            {
                "data": hoje.strftime("%d/%m/%Y"),
                "valor": "12,50",
            },
            {
                "data": futuro.strftime("%d/%m/%Y"),
                "valor": "99,00",
            },
        ],
    )

    valor, referencia = mercado._fetch_sgs_value(
        mercado.SGS_SELIC
    )

    assert valor == pytest.approx(0.125)
    assert referencia == hoje.strftime("%d/%m/%Y")


def test_cache_roundtrip(
    monkeypatch,
    tmp_path,
    mercado_valido,
) -> None:
    arquivo = tmp_path / "market.json"

    monkeypatch.setattr(
        mercado,
        "CACHE_FILE",
        arquivo,
    )

    mercado._save_market_cache(mercado_valido)
    carregado = mercado._load_market_cache(
        max_age_seconds=60
    )

    assert carregado == mercado_valido
    assert carregado["_schema_version"] == 4
    assert carregado["focus_selic_por_ano"]


def test_cache_expirado_nao_e_fresco(
    monkeypatch,
    tmp_path,
    mercado_valido,
) -> None:
    arquivo = tmp_path / "market.json"

    monkeypatch.setattr(
        mercado,
        "CACHE_FILE",
        arquivo,
    )

    mercado._save_market_cache(mercado_valido)

    antigo = time.time() - 120
    os.utime(
        arquivo,
        (antigo, antigo),
    )

    assert mercado._load_market_cache(
        max_age_seconds=60
    ) is None


def test_cache_com_schema_antigo_e_rejeitado(
    monkeypatch,
    tmp_path,
    mercado_valido,
) -> None:
    arquivo = tmp_path / "market.json"
    payload_antigo = {
        **mercado_valido,
        "_schema_version": 2,
    }

    monkeypatch.setattr(
        mercado,
        "CACHE_FILE",
        arquivo,
    )

    mercado._save_market_cache(payload_antigo)

    assert mercado._load_market_cache(
        max_age_seconds=60
    ) is None


def test_load_market_data_com_coletores_simulados(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(
        mercado,
        "CACHE_FILE",
        tmp_path / "market.json",
    )

    monkeypatch.setattr(
        mercado,
        "_fetch_sgs_value",
        lambda serie: (
            (0.10, "01/07/2026")
            if serie == mercado.SGS_SELIC
            else (0.04, "30/06/2026")
        ),
    )

    monkeypatch.setattr(
        mercado,
        "_fetch_focus_selic_por_ano",
        lambda: {
            2026: 0.09,
            2027: 0.08,
            2028: 0.075,
            2029: 0.07,
        },
    )

    monkeypatch.setattr(
        mercado,
        "_fetch_ibov_cagr_10a",
        lambda: 0.12,
    )

    resultado = mercado.load_market_data(
        force_refresh=True
    )

    assert resultado["selic"] == pytest.approx(0.10)
    assert resultado["ipca"] == pytest.approx(0.04)
    assert resultado["ibov_cagr"] == pytest.approx(0.12)

    assert resultado["focus_selic"] == pytest.approx(0.09)
    assert resultado["focus_selic_por_ano"] == {
        2026: pytest.approx(0.09),
        2027: pytest.approx(0.08),
        2028: pytest.approx(0.075),
        2029: pytest.approx(0.07),
    }

    assert resultado["_schema_version"] == 4
    assert resultado["cache_status"] == "fresh"
    assert resultado["avisos"] == []


def test_focus_indisponivel_nao_impede_carregamento(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(
        mercado,
        "CACHE_FILE",
        tmp_path / "market.json",
    )

    monkeypatch.setattr(
        mercado,
        "_fetch_sgs_value",
        lambda serie: (
            (0.10, "01/07/2026")
            if serie == mercado.SGS_SELIC
            else (0.04, "30/06/2026")
        ),
    )

    monkeypatch.setattr(
        mercado,
        "_fetch_focus_selic_por_ano",
        lambda: {},
    )

    monkeypatch.setattr(
        mercado,
        "_fetch_ibov_cagr_10a",
        lambda: 0.12,
    )

    resultado = mercado.load_market_data(
        force_refresh=True
    )

    assert resultado["focus_selic"] is None
    assert resultado["focus_selic_por_ano"] == {}
    assert resultado["selic"] == pytest.approx(0.10)
    assert resultado["avisos"]
    assert any(
        "Focus SELIC indisponível" in aviso
        for aviso in resultado["avisos"]
    )