"""Fixtures compartilhadas pela suíte nova."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def carregar_fixture(fixtures_dir):
    def carregar(nome: str):
        with (fixtures_dir / nome).open("r", encoding="utf-8") as arquivo:
            return json.load(arquivo)

    return carregar


@pytest.fixture
def mercado_valido(carregar_fixture) -> dict:
    return carregar_fixture("mercado.json")


@pytest.fixture
def respostas_padrao() -> dict:
    return {
        "prazo": "longo",
        "risco": "médio",
        "objetivo": "crescimento",
        "fluxo": "acúmulo",
        "controle": "gerir",
        "liquidez": "sim",
        "liquidez_pct": 20,
        "reserva_emerg": "sim",
        "despesas_essenciais_mensais": 1_000,
        "reserva_atual": 6_000,
        "idade": "adulto",
        "despesas": "baixas",
        "faixa_valor": "médio",
        "patrim_pct": "baixo",
        "renda": "clt",
        "dividas": "não tenho",
        "conhecimento": "intermediário",
        "experiencia": ["ações"],
        "dependentes": "nenhum",
        "aporte": "mensal",
        "emocional": "esperaria recuperar",
        "ir_tipo": "simplificado",
        "carteira_atual": "não tenho",
        "modo_meta": "sim",
        "meta_valor": 200_000,
        "meta_prazo": 10,
        "cap_inicial": 10_000,
        "aporte_mensal": 500,
    }


class _RedeBloqueadaError(OSError):
    """Levantada quando um teste comum tenta acessar a internet."""


@pytest.fixture(autouse=True)
def _bloquear_rede(request, monkeypatch):
    """Testes sem a marca `slow` não podem depender de internet.

    Sem isso, um teste "determinístico" passa ou falha conforme a API
    externa esteja no ar. A exceção herda de OSError, então os coletores a
    tratam como uma falha de rede comum.
    """
    if request.node.get_closest_marker("slow"):
        return
    import socket

    def _negar(*args, **kwargs):
        raise _RedeBloqueadaError(
            "Acesso à rede bloqueado em testes sem @pytest.mark.slow."
        )

    monkeypatch.setattr(socket.socket, "connect", _negar)
    monkeypatch.setattr(socket, "create_connection", _negar)


@pytest.fixture(autouse=True)
def _sem_cache_de_ranking(monkeypatch):
    """Rankings de fundos são calculados nos testes, sem ler o cache do usuário."""
    try:
        import fundos.cache_ranking as cache_ranking
    except ImportError:
        return
    monkeypatch.setattr(cache_ranking, "_ultima_data_informe", lambda: None)


@pytest.fixture(autouse=True)
def _cache_do_tesouro_isolado(monkeypatch, tmp_path):
    """Cada teste usa um cache do Tesouro vazio e próprio."""
    try:
        import renda_fixa.coletor as coletor
    except ImportError:
        return
    monkeypatch.setattr(coletor, "_CACHE_TESOURO", tmp_path / "tesouro_titulos.json")
