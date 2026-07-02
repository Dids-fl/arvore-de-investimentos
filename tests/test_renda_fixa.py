# tests/test_renda_fixa.py
"""
Testes para o módulo de Renda Fixa (apenas Tesouro Direto).
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from renda_fixa import rankear_rf
from renda_fixa.coletor import coletar_indicadores, coletar_tesouro
from renda_fixa.ranker import _calcular_prazo_dias, _calcular_score


# ──────────────────────────────────────────────────────────────
# 1. Testes do coletor
# ──────────────────────────────────────────────────────────────

def test_coletar_indicadores():
    selic, cdi = coletar_indicadores()
    if selic is not None and cdi is not None:
        assert isinstance(selic, float)
        assert isinstance(cdi, float)
        if cdi >= 0.01 and selic >= 0.01:
            assert 0.01 <= selic <= 0.20
            assert 0.01 <= cdi <= 0.20
            assert cdi <= selic * 1.01


def test_coletar_tesouro():
    titulos = coletar_tesouro()
    # Pode ser None se a API falhar, mas se retornar, deve ser lista com estrutura correta
    if titulos is not None:
        assert isinstance(titulos, list)
        if len(titulos) > 0:
            primeiro = titulos[0]
            assert "nome" in primeiro
            assert "taxa" in primeiro
            assert "vencimento" in primeiro
            assert isinstance(primeiro["taxa"], (int, float))


# ──────────────────────────────────────────────────────────────
# 2. Testes do ranker
# ──────────────────────────────────────────────────────────────

def test_rankear_rf_estrutura():
    recomendacoes = rankear_rf(perfil=2, limite=3)
    assert isinstance(recomendacoes, list)
    if len(recomendacoes) > 0:
        p = recomendacoes[0]
        campos_esperados = ["ticker", "nome", "emissor", "tipo", "taxa_bruta",
                            "vencimento", "garantia", "liquidez", "ir",
                            "isento_ir", "prazo_dias", "fonte", "score"]
        for campo in campos_esperados:
            assert campo in p, f"Campo '{campo}' ausente"
        assert p["emissor"] == "Tesouro Nacional"
        assert isinstance(p["score"], float)
        assert 0 <= p["score"] <= 10


def test_rankear_rf_limite():
    rec = rankear_rf(perfil=2, limite=10)
    assert isinstance(rec, list)
    if len(rec) > 0:
        assert len(rec) <= 10


def test_rankear_rf_perfis():
    # Verifica se diferentes perfis retornam listas (pode ser vazia)
    rec_cons = rankear_rf(perfil=1, limite=2)
    rec_mod = rankear_rf(perfil=2, limite=2)
    rec_agr = rankear_rf(perfil=3, limite=2)
    assert isinstance(rec_cons, list)
    assert isinstance(rec_mod, list)
    assert isinstance(rec_agr, list)


# ──────────────────────────────────────────────────────────────
# 3. Testes de funções auxiliares
# ──────────────────────────────────────────────────────────────

def test_calcular_prazo_dias():
    from datetime import datetime, timedelta
    agora = datetime.now()
    futuro = agora + timedelta(days=100)
    venc_str = futuro.strftime("%d/%m/%Y")
    dias = _calcular_prazo_dias(venc_str)
    assert 99 <= dias <= 101

    # Formato YYYY-MM-DD
    venc_str2 = futuro.strftime("%Y-%m-%d")
    dias2 = _calcular_prazo_dias(venc_str2)
    assert 99 <= dias2 <= 101


def test_calcular_score():
    # Teste para perfil conservador
    produto = {
        "taxa_bruta": 0.12,
        "garantia": "Governo Federal",
        "liquidez": "D+1",
        "prazo_dias": 365,
        "tipo": "Tesouro Prefixado"
    }
    score = _calcular_score(produto, perfil=2)  # moderado
    assert 0 <= score <= 10

    # Perfil conservador deve penalizar prazo longo
    produto_longo = {
        "taxa_bruta": 0.12,
        "garantia": "Governo Federal",
        "liquidez": "D+1",
        "prazo_dias": 1096,
        "tipo": "Tesouro Prefixado"
    }
    score_cons = _calcular_score(produto_longo, perfil=1)
    score_agr = _calcular_score(produto_longo, perfil=3)
    assert score_cons <= score_agr, "Conservador deve penalizar prazo longo mais que agressivo"


# ──────────────────────────────────────────────────────────────
# 4. Teste visual (impressão das recomendações)
# ──────────────────────────────────────────────────────────────

def test_mostrar_recomendacoes():
    print("\n" + "="*80)
    print("RECOMENDAÇÕES DE RENDA FIXA (APENAS TESOURO DIRETO)")
    print("="*80)

    selic, cdi = coletar_indicadores()
    print(f"\n📊 Selic: {selic:.2%} | CDI: {cdi:.2%}\n")

    for perfil_nome, perfil_id in [("Conservador", 1), ("Moderado", 2), ("Agressivo", 3)]:
        print(f"\n--- Perfil: {perfil_nome} ---")
        recomendacoes = rankear_rf(perfil=perfil_id, limite=3)
        if not recomendacoes:
            print("   Nenhuma recomendação disponível (API pode estar offline).")
            continue

        for i, item in enumerate(recomendacoes, 1):
            print(f"\n{i}️⃣ {item.get('nome', 'N/A')}")
            print(f"   Emissor   : {item.get('emissor', 'N/A')}")
            print(f"   Tipo      : {item.get('tipo', 'N/A')}")
            print(f"   Taxa bruta: {item.get('taxa_bruta', 0):.2%}")
            print(f"   Vencimento: {item.get('vencimento', 'N/A')}")
            print(f"   Prazo     : {item.get('prazo_dias', 0)} dias")
            print(f"   Garantia  : {item.get('garantia', 'N/A')}")
            print(f"   Liquidez  : {item.get('liquidez', 'N/A')}")
            print(f"   IR        : {item.get('ir', 'N/A')}")
            print(f"   Isento IR : {'Sim' if item.get('isento_ir', False) else 'Não'}")
            print(f"   Fonte     : {item.get('fonte', 'N/A')}")
            print(f"   ⭐ Score   : {item.get('score', 0):.2f} / 10")
            print("   " + "-"*40)

    print("\n" + "="*80)
    print("FIM DAS RECOMENDAÇÕES")
    print("="*80 + "\n")


# ──────────────────────────────────────────────────────────────
# Execução direta (para ver os prints)
# ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s", "--tb=short"])