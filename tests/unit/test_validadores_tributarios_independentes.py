"""Testes dos validadores que não reutilizam as fórmulas de produção."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from validacao.tributacao import (
    validar_cripto_independente,
    validar_estruturados_independente,
    validar_fundos_independente,
    validar_previdencia_independente,
    validar_renda_fixa_independente,
    validar_renda_variavel_independente,
)
from validacao.tributacao.comum import (
    DIVERGENTE,
    FORA_ESCOPO,
    PENDENTE_EVIDENCIA,
    STATUS_VALIDACAO,
    VALIDADO_CALCULO,
    VALIDADO_GUARDRAIL,
    codigo_saida,
)
from validacao.tributacao.validar_tudo import executar

MODULOS = (
    validar_renda_fixa_independente,
    validar_fundos_independente,
    validar_previdencia_independente,
    validar_renda_variavel_independente,
    validar_estruturados_independente,
    validar_cripto_independente,
)


@pytest.mark.parametrize("modulo", MODULOS)
def test_validador_nao_importa_tabelas_do_motor(modulo) -> None:
    caminho = Path(modulo.__file__)
    codigo = caminho.read_text(encoding="utf-8")
    assert "tributacao.regras" not in codigo


@pytest.mark.parametrize("modulo", MODULOS)
def test_validador_nao_encontra_divergencia(
    modulo,
    tmp_path: Path,
) -> None:
    relatorio = modulo.validar(tmp_path)
    resumo = relatorio["resumo"]
    assert resumo[DIVERGENTE] == 0
    assert resumo["total"] == sum(resumo[status] for status in STATUS_VALIDACAO)
    destino = Path(relatorio["arquivo"])
    assert destino.exists()
    carregado = json.loads(destino.read_text(encoding="utf-8"))
    assert carregado["categoria"] == relatorio["categoria"]


def test_consolidado_cobre_seis_categorias(tmp_path: Path) -> None:
    consolidado = executar(tmp_path)
    assert consolidado["resumo"]["total"] == 63
    assert consolidado["resumo"][DIVERGENTE] == 0
    assert set(consolidado["categorias"]) == {
        "renda_fixa",
        "fundos",
        "previdencia",
        "renda_variavel",
        "estruturados",
        "cripto",
    }


def test_consolidado_separa_guardrail_de_fora_do_escopo(
    tmp_path: Path,
) -> None:
    resumo = executar(tmp_path)["resumo"]
    assert resumo[VALIDADO_CALCULO] > 0
    assert resumo[VALIDADO_GUARDRAIL] > 0
    assert resumo[PENDENTE_EVIDENCIA] > 0
    assert resumo[FORA_ESCOPO] == 3


def test_codigo_saida_falha_quando_existe_divergencia() -> None:
    relatorio = {"resumo": {DIVERGENTE: 1}}
    assert codigo_saida(relatorio) == 1


def test_codigo_saida_aceita_pendencias() -> None:
    relatorio = {"resumo": {DIVERGENTE: 0}}
    assert codigo_saida(relatorio) == 0


def _entrada_por_prazo(
    dias: int,
    tipo_produto: str = "cdb",
) -> dict:
    inicio = date(2026, 1, 1)
    return {
        "principal": 10_000.0,
        "valor_bruto": 11_000.0,
        "data_aplicacao": inicio.isoformat(),
        "data_resgate": (inicio + timedelta(days=dias)).isoformat(),
        "tipo_produto": tipo_produto,
    }


@pytest.mark.parametrize(
    ("dias", "imposto"),
    (
        (1, 969.0),
        (29, 248.25),
        (30, 225.0),
        (180, 225.0),
        (181, 200.0),
        (360, 200.0),
        (361, 175.0),
        (720, 175.0),
        (721, 150.0),
    ),
)
def test_renda_fixa_cobre_limites_de_iof_e_ir(
    dias: int,
    imposto: float,
) -> None:
    resultado = validar_renda_fixa_independente.calcular_independente(
        _entrada_por_prazo(dias)
    )
    assert resultado["imposto_estimado"] == pytest.approx(imposto)


@pytest.mark.parametrize(
    ("tipo", "dias", "imposto"),
    (
        ("fundo_curto_prazo", 180, 225.0),
        ("fundo_curto_prazo", 181, 200.0),
        ("fundo_longo_prazo", 360, 200.0),
        ("fundo_longo_prazo", 361, 175.0),
        ("fundo_longo_prazo", 720, 175.0),
        ("fundo_longo_prazo", 721, 150.0),
    ),
)
def test_fundos_cobrem_limites_de_prazo(
    tipo: str,
    dias: int,
    imposto: float,
) -> None:
    resultado = validar_fundos_independente.calcular_independente(
        _entrada_por_prazo(dias, tipo)
    )
    assert resultado["imposto_estimado"] == pytest.approx(imposto)


def test_renda_variavel_respeita_limite_mensal_de_acoes() -> None:
    entrada = _entrada_por_prazo(181, "acao")
    entrada["valor_vendas_mes"] = 20_000.0
    isento = validar_renda_variavel_independente.calcular_independente(entrada)
    entrada["valor_vendas_mes"] = 20_000.01
    tributado = validar_renda_variavel_independente.calcular_independente(entrada)
    assert isento["imposto_estimado"] == 0.0
    assert tributado["imposto_estimado"] == pytest.approx(150.0)


def test_estruturado_exige_elegibilidade_para_isencao() -> None:
    entrada = _entrada_por_prazo(721, "cri")
    indeterminado = validar_estruturados_independente.calcular_independente(entrada)
    entrada["metadados"] = {"elegibilidade_isencao_confirmada": True}
    isento = validar_estruturados_independente.calcular_independente(entrada)
    assert indeterminado["precisao"] == "indeterminada"
    assert isento["imposto_estimado"] == 0.0
