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
