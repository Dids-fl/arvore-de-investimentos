"""Cache dos rankings de fundos: reaproveita até a CVM publicar dado novo."""

from __future__ import annotations

import pytest

cache = pytest.importorskip("fundos.cache_ranking")


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    estado = {"data": "2026-10-30"}
    monkeypatch.setattr(cache, "_ultima_data_informe", lambda: estado["data"])
    return estado


def test_reaproveita_ate_chegar_informe_novo(ambiente):
    chamadas = []

    def calcular():
        chamadas.append(1)
        return [{"cnpj": "1", "score": 9.0}]

    assert cache.com_cache("fundos", {"perfil": 2}, calcular) == [{"cnpj": "1", "score": 9.0}]
    cache.com_cache("fundos", {"perfil": 2}, calcular)
    assert len(chamadas) == 1

    cache.com_cache("fundos", {"perfil": 3}, calcular)  # outros parâmetros
    assert len(chamadas) == 2

    ambiente["data"] = "2026-10-31"  # CVM publicou um novo dia
    cache.com_cache("fundos", {"perfil": 2}, calcular)
    assert len(chamadas) == 3


def test_ranking_vazio_nao_vai_para_o_cache(ambiente):
    chamadas = []

    def calcular():
        chamadas.append(1)
        return []

    cache.com_cache("fundos", {"perfil": 2}, calcular)
    cache.com_cache("fundos", {"perfil": 2}, calcular)
    assert len(chamadas) == 2


def test_sem_banco_calcula_sem_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(cache, "_ultima_data_informe", lambda: None)
    assert cache.com_cache("fundos", {}, lambda: [{"a": 1}]) == [{"a": 1}]
    assert not list(tmp_path.iterdir())
