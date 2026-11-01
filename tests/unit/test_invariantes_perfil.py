"""Invariantes da recomendação verificadas em perfis gerados aleatoriamente.

Os testes de cenário cobrem casos escolhidos a dedo; estes procuram
combinações que ninguém pensou em escrever. A semente é fixa para que uma
falha seja reproduzível.
"""

from __future__ import annotations

import json
import math
import random
from datetime import date

import pytest

engine = pytest.importorskip("engine")
_categorias = pytest.importorskip("core.categorias")
RK = _categorias.RK
_risco = _categorias._risco

QUANTIDADE_PERFIS = 250
SEMENTE = 20261101


def _perfil_aleatorio(rng: random.Random) -> dict:
    respostas = {
        campo: rng.choice(sorted(opcoes))
        for campo, opcoes in engine.RESPOSTAS_MAP.items()
    }
    experiencias = sorted(set(engine._EXPERIENCIAS.values()))
    respostas.update(
        {
            "liquidez_pct": rng.choice([0, 10, 50, 100]),
            "experiencia": rng.sample(experiencias, rng.randint(0, 3)),
            "cap_inicial": rng.choice([0, 1_000, 100_000, 5_000_000]),
            "aporte_mensal": rng.choice([0, 100, 5_000]),
            "despesas_essenciais_mensais": rng.choice([None, 0, 3_000]),
            "reserva_atual": rng.choice([None, 0, 50_000]),
        }
    )
    if engine.RESPOSTAS_MAP["modo_meta"][respostas["modo_meta"]] == 1:
        respostas["meta_valor"] = rng.choice([100_000, 10_000_000])
        respostas["meta_prazo"] = rng.choice([1, 5, 30])
    return respostas


def _analises(mercado):
    rng = random.Random(SEMENTE)
    for _ in range(QUANTIDADE_PERFIS):
        respostas = _perfil_aleatorio(rng)
        try:
            analise = engine.criar_analise(
                respostas,
                mercado,
                data_referencia=date(2026, 7, 29),
            )
        except (engine.DividaJurosAltosError, engine.RecomendacaoBloqueadaError):
            continue
        yield respostas, analise


@pytest.fixture(scope="module")
def analises(carregar_fixture):
    return list(_analises(carregar_fixture("mercado.json")))


def _mapa(campo: str, respostas: dict) -> int:
    return engine.RESPOSTAS_MAP[campo][respostas[campo]]


def test_amostra_relevante(analises) -> None:
    assert len(analises) > QUANTIDADE_PERFIS // 2


def test_carteira_soma_cem_sem_valores_negativos(analises) -> None:
    for respostas, analise in analises:
        portfolio = analise["resultado"]["portfolio"]
        assert sum(portfolio.values()) == pytest.approx(100), respostas
        assert all(valor >= 0 for valor in portfolio.values()), respostas


def test_objetivo_reserva_fica_em_renda_fixa(analises) -> None:
    for respostas, analise in analises:
        if _mapa("objetivo", respostas) != 1:
            continue
        portfolio = analise["resultado"]["portfolio"]
        assert all(_risco(chave) == 1 for chave in portfolio), respostas


def test_senior_nao_recebe_cripto_direta(analises) -> None:
    for respostas, analise in analises:
        if _mapa("idade", respostas) == 3:
            assert RK.RV_CRIPTO not in analise["resultado"]["portfolio"], respostas


def test_iniciante_sem_experiencia_nao_recebe_cripto_direta(analises) -> None:
    for respostas, analise in analises:
        sem_experiencia = set(respostas["experiencia"]) <= {"nenhum"}
        if _mapa("conhecimento", respostas) == 1 and sem_experiencia:
            assert RK.RV_CRIPTO not in analise["resultado"]["portfolio"], respostas


def test_sem_reserva_e_sem_dados_prioriza_reserva(analises) -> None:
    for respostas, analise in analises:
        sem_dados = respostas["despesas_essenciais_mensais"] is None
        if _mapa("reserva_emerg", respostas) == 1 and sem_dados:
            portfolio = analise["resultado"]["portfolio"]
            # Tudo precisa estar em renda fixa de liquidez diária.
            liquidez_diaria = {RK.RF_RESERVA, RK.RF_LIQUIDEZ, RK.RF_SELIC_CDB}
            assert set(portfolio) <= liquidez_diaria, respostas


def test_exportacao_serializavel_e_finita(analises) -> None:
    for respostas, analise in analises:
        texto = json.dumps(
            engine.montar_payload_exportacao(analise),
            ensure_ascii=False,
            default=str,
            allow_nan=False,
        )
        assert texto, respostas
        for linha in analise["projecoes"]:
            assert math.isfinite(linha["vf_bruto"]), respostas
            for chave in ("vf_liquido", "vf_real", "vf_pessimista_liquido"):
                valor = linha.get(chave)
                assert valor is None or math.isfinite(valor), respostas
