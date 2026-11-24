"""Selic, CDI e IPCA: a BrasilAPI é a reserva quando o SGS do BCB falha."""

from __future__ import annotations

import pytest

import mercado


def test_usa_brasilapi_quando_sgs_falha(monkeypatch) -> None:
    def sgs_fora(serie):
        raise RuntimeError("SGS fora do ar")

    monkeypatch.setattr(mercado, "_fetch_sgs_value", sgs_fora)
    monkeypatch.setattr(
        mercado,
        "_json_get",
        lambda url, **_: [
            {"nome": "Selic", "valor": 13.75},
            {"nome": "CDI", "valor": 13.65},
            {"nome": "IPCA", "valor": 4.58},
        ],
    )
    valor, referencia = mercado._fetch_taxa_bcb(mercado.SGS_SELIC)
    assert valor == pytest.approx(0.1375)
    assert "BrasilAPI" in referencia
    assert mercado._fetch_taxa_bcb(mercado.SGS_IPCA_12M)[0] == pytest.approx(0.0458)


def test_sgs_tem_prioridade(monkeypatch) -> None:
    monkeypatch.setattr(mercado, "_fetch_sgs_value", lambda serie: (0.10, "01/11/2026"))
    monkeypatch.setattr(mercado, "_json_get", lambda *a, **k: pytest.fail("não devia consultar"))
    assert mercado._fetch_taxa_bcb(mercado.SGS_SELIC) == (0.10, "01/11/2026")


def test_se_as_duas_falham_mantem_o_erro_do_sgs(monkeypatch) -> None:
    def falha(*_a, **_k):
        raise RuntimeError("fora")

    monkeypatch.setattr(mercado, "_fetch_sgs_value", lambda serie: (_ for _ in ()).throw(RuntimeError("SGS")))
    monkeypatch.setattr(mercado, "_json_get", falha)
    with pytest.raises(RuntimeError, match="SGS"):
        mercado._fetch_taxa_bcb(mercado.SGS_CDI_ANUAL)
