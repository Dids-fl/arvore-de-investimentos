"""Testes determinísticos do cache e contenção de falhas do CDI."""

from __future__ import annotations

import json
import time

import pytest

from macroeconomia import cdi


@pytest.fixture(autouse=True)
def cache_isolado(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(cdi, "_CACHE_FILE", tmp_path / "cdi.json")
    cdi.limpar_cache_memoria()


def test_periodo_consulta_online_uma_vez_e_reutiliza(monkeypatch) -> None:
    chamadas = 0

    def buscar(inicio: str, fim: str) -> float:
        nonlocal chamadas
        chamadas += 1
        assert inicio == "2025-01-01"
        assert fim == "2025-12-31"
        return 0.142

    monkeypatch.setattr(cdi, "_buscar_cdi_online", buscar)

    primeiro = cdi.obter_cdi_periodo("2025-01-01", "2025-12-31")
    segundo = cdi.obter_cdi_periodo("2025-01-01", "2025-12-31")

    assert primeiro == pytest.approx(0.142)
    assert segundo == pytest.approx(0.142)
    assert chamadas == 1


def test_periodo_reaproveita_cache_persistente(monkeypatch) -> None:
    chave = "2024-01-01:2024-12-31"
    cdi._CACHE_FILE.write_text(
        json.dumps(
            {
                "periodos": {
                    chave: {
                        "valor": 0.108,
                        "armazenado_em": time.time(),
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        cdi,
        "_buscar_cdi_online",
        lambda *args: pytest.fail("não deveria consultar a rede"),
    )

    valor = cdi.obter_cdi_periodo("2024-01-01", "2024-12-31")

    assert valor == pytest.approx(0.108)


def test_falha_abre_circuito_e_evitar_repeticao(monkeypatch) -> None:
    chamadas = 0

    def falhar(*args) -> None:
        nonlocal chamadas
        chamadas += 1

    monkeypatch.setattr(cdi, "_buscar_cdi_online", falhar)

    primeiro = cdi.obter_cdi_periodo("2025-01-01", "2025-12-31")
    segundo = cdi.obter_cdi_periodo("2025-02-01", "2025-11-30")

    assert primeiro is None
    assert segundo is None
    assert chamadas == 1


def test_periodo_invalido_nao_consulta_fonte(monkeypatch) -> None:
    monkeypatch.setattr(
        cdi,
        "_buscar_cdi_online",
        lambda *args: pytest.fail("não deveria consultar a rede"),
    )

    assert cdi.obter_cdi_periodo("2025-12-31", "2025-01-01") is None
