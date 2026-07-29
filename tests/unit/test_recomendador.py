"""Regras de segurança expostas pelo recomendador."""

from __future__ import annotations

import pytest

engine = pytest.importorskip("engine")


def test_divida_cara_bloqueia(
    respostas_padrao,
    mercado_valido,
) -> None:
    respostas = {**respostas_padrao, "dividas": "juros altos"}
    with pytest.raises(engine.DividaJurosAltosError):
        engine.criar_analise(respostas, mercado_valido)


def test_experiencia_remove_contradicao() -> None:
    assert engine.normalizar_experiencia(
        ["nenhum", "ações", "AÇÕES"]
    ) == ["ações"]


def test_formulario_rejeita_opcao_desconhecida() -> None:
    with pytest.raises(ValueError, match="Opção inválida"):
        engine.mapear_respostas_formulario({"prazo": "eterno"})


def test_dados_de_mercado_obrigatorios() -> None:
    with pytest.raises(ValueError, match="ibov_cagr"):
        engine.taxas_por_risco(
            {
                "selic": 0.10,
                "focus_selic": None,
                "ipca": 0.04,
            }
        )
