"""Lista pública da BRAPI usada para ETFs e nomes de FIIs."""

from __future__ import annotations

import pytest

brapi = pytest.importorskip("acoes_fiis.apis.brapi_tickers")


class _Resposta:
    def __init__(self, dados):
        self._dados = dados

    def raise_for_status(self):
        return None

    def json(self):
        return self._dados


def test_lista_pagina_e_guarda_cache(monkeypatch) -> None:
    paginas = {
        1: {
            "results": [{"symbol": "BOVA11", "name": "ISHARES BOVA", "subType": "etf"}],
            "pagination": {"hasNextPage": True},
        },
        2: {
            "results": [{"symbol": "HGLG11", "name": "CSHG LOGÍSTICA FII", "subType": "fii"}],
            "pagination": {"hasNextPage": False},
        },
    }
    chamadas = []

    def falso_get(url, params, **kwargs):
        chamadas.append(params["page"])
        return _Resposta(paginas[params["page"]])

    monkeypatch.setattr(brapi.requests, "get", falso_get)
    monkeypatch.setattr(brapi.time, "sleep", lambda s: None)
    monkeypatch.setattr(brapi, "_cache", {"ts": 0.0, "dados": None})

    ativos = brapi.listar_tickers()
    brapi.listar_tickers()

    assert set(ativos) == {"BOVA11", "HGLG11"}
    assert chamadas == [1, 2]
    assert brapi.nome_do_ativo("hglg11", ativos) == "CSHG LOGÍSTICA FII"
    assert brapi.nome_do_ativo("XPTO11", ativos) == ""
