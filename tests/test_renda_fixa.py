"""
Testes para o módulo de Renda Fixa (renda_fixa).
Verifica a integridade dos dados, cálculos e fallbacks.
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from renda_fixa import rankear_rf
from renda_fixa.coletor import coletar_indicadores, coletar_tesouro
from renda_fixa.fallback import get_fallback
from renda_fixa.ranker import _calcular_prazo_dias, _calcular_score

try:
    from renda_fixa.scraper_yubb import scraper_yubb
    SCRAPER_DISPONIVEL = True
except ImportError:
    SCRAPER_DISPONIVEL = False


# ──────────────────────────────────────────────────────────────
# 1. Testes do coletor (APIs oficiais)
# ──────────────────────────────────────────────────────────────

def test_coletar_indicadores():
    """Verifica se os indicadores (Selic e CDI) são retornados corretamente."""
    selic, cdi = coletar_indicadores()
    if selic is not None and cdi is not None:
        assert isinstance(selic, float), "Selic deve ser float"
        assert isinstance(cdi, float), "CDI deve ser float"
        if cdi >= 0.01 and selic >= 0.01:
            assert 0.01 <= selic <= 0.20, "Selic deve estar entre 1% e 20%"
            assert 0.01 <= cdi <= 0.20, "CDI deve estar entre 1% e 20%"
            assert cdi <= selic * 1.01, "CDI não deve ser muito maior que Selic"


def test_coletar_tesouro():
    """Verifica se a lista de títulos do Tesouro é retornada."""
    titulos = coletar_tesouro()
    if titulos is not None:
        assert isinstance(titulos, list), "Tesouro deve retornar lista"
        if len(titulos) > 0:
            primeiro = titulos[0]
            assert "nome" in primeiro, "Cada título deve ter 'nome'"
            assert "taxa" in primeiro, "Cada título deve ter 'taxa'"
            assert "vencimento" in primeiro, "Cada título deve ter 'vencimento'"
            assert isinstance(primeiro["taxa"], (int, float)), "Taxa deve ser número"


# ──────────────────────────────────────────────────────────────
# 2. Testes do scraper Yubb (se disponível)
# ──────────────────────────────────────────────────────────────

@pytest.mark.skipif(not SCRAPER_DISPONIVEL, reason="scraper_yubb não disponível")
def test_scraper_yubb():
    produtos = scraper_yubb()
    if produtos is not None:
        assert isinstance(produtos, list), "Produtos deve ser lista"
        if len(produtos) > 0:
            p = produtos[0]
            campos_esperados = ["ticker", "nome", "emissor", "tipo", "taxa_bruta",
                                "vencimento", "garantia", "liquidez", "ir",
                                "isento_ir", "prazo_dias", "fonte"]
            for campo in campos_esperados:
                assert campo in p, f"Campo '{campo}' ausente no produto"
            assert isinstance(p["taxa_bruta"], float), "taxa_bruta deve ser float"
            assert isinstance(p["isento_ir"], bool), "isento_ir deve ser bool"
            assert p["fonte"] == "Yubb", "Fonte deve ser 'Yubb'"


# ──────────────────────────────────────────────────────────────
# 3. Testes do fallback
# ──────────────────────────────────────────────────────────────

def test_fallback_estrutura():
    fallback = get_fallback()
    assert isinstance(fallback, list), "Fallback deve ser lista"
    if len(fallback) > 0:
        p = fallback[0]
        campos_esperados = ["ticker", "nome", "tipo", "taxa_bruta", "vencimento",
                            "garantia", "liquidez", "ir", "isento_ir", "prazo_dias"]
        for campo in campos_esperados:
            assert campo in p, f"Campo '{campo}' ausente no fallback"


# ──────────────────────────────────────────────────────────────
# 4. Testes do ranker (função principal)
# ──────────────────────────────────────────────────────────────

def test_rankear_rf_sem_scraper():
    recomendacoes = rankear_rf(perfil=2, limite=3, usar_yubb=False)
    assert isinstance(recomendacoes, list), "Ranker deve retornar lista"
    assert len(recomendacoes) <= 3, "Limite deve ser respeitado"
    if len(recomendacoes) > 0:
        p = recomendacoes[0]
        campos_esperados = ["ticker", "nome", "tipo", "taxa_bruta", "vencimento",
                            "garantia", "liquidez", "ir", "isento_ir", "prazo_dias", "score"]
        for campo in campos_esperados:
            assert campo in p, f"Campo '{campo}' ausente na recomendação"
        assert isinstance(p["score"], (int, float)), "Score deve ser número"


def test_rankear_rf_com_scraper():
    recomendacoes = rankear_rf(perfil=1, limite=5, usar_yubb=True)
    assert isinstance(recomendacoes, list), "Ranker deve retornar lista"
    assert len(recomendacoes) <= 5, "Limite deve ser respeitado"
    if len(recomendacoes) > 0:
        p = recomendacoes[0]
        assert "nome" in p
        assert "taxa_bruta" in p
        assert "score" in p


def test_rankear_rf_perfis():
    rec_conservador = rankear_rf(perfil=1, limite=5, usar_yubb=False)
    rec_agressivo = rankear_rf(perfil=3, limite=5, usar_yubb=False)
    if rec_conservador and rec_agressivo:
        assert "score" in rec_conservador[0]
        assert "score" in rec_agressivo[0]


# ──────────────────────────────────────────────────────────────
# 5. Testes de funções auxiliares
# ──────────────────────────────────────────────────────────────

def test_calcular_prazo_dias():
    from datetime import datetime, timedelta
    agora = datetime.now()
    futuro = agora + timedelta(days=100)
    venc_str = futuro.strftime("%Y-%m-%d")
    dias = _calcular_prazo_dias(venc_str)
    assert 99 <= dias <= 101, f"Prazo deve ser cerca de 100, obtido {dias}"


def test_calcular_score():
    produto = {
        "taxa_bruta": 0.12,
        "isento_ir": True,
        "garantia": "FGC",
        "liquidez": "Diária",
        "prazo_dias": 365,
        "tipo": "LCI"
    }
    cdi = 0.105
    score_cons = _calcular_score(produto, perfil=1, cdi_atual=cdi)
    score_agr = _calcular_score(produto, perfil=3, cdi_atual=cdi)
    assert score_cons >= score_agr, "Conservador deve preferir isenção"
    
    produto2 = {
        "taxa_bruta": 0.15,
        "isento_ir": False,
        "garantia": "FGC",
        "liquidez": "Baixa",
        "prazo_dias": 1096,
        "tipo": "CDB"
    }
    score_agr2 = _calcular_score(produto2, perfil=3, cdi_atual=cdi)
    score_cons2 = _calcular_score(produto2, perfil=1, cdi_atual=cdi)
    assert score_agr2 >= score_cons2, "Agressivo deve preferir taxas altas e prazos longos"


def test_imports():
    import renda_fixa
    import renda_fixa.coletor
    import renda_fixa.ranker
    import renda_fixa.fallback
    try:
        import renda_fixa.scraper_yubb
    except ImportError:
        pass
    assert True


def test_rankear_rf_fallback_force():
    rec = rankear_rf(perfil=2, limite=3, usar_yubb=False)
    assert isinstance(rec, list)
    if rec:
        assert "nome" in rec[0]
        assert "score" in rec[0]


# ──────────────────────────────────────────────────────────────
# 6. Teste visual com impressão das recomendações
# ──────────────────────────────────────────────────────────────

def test_mostrar_recomendacoes():
    """
    Este teste não faz asserts, apenas imprime 3 recomendações
    com todos os campos relevantes para classificação.
    Execute com: pytest tests/test_renda_fixa.py -s -k mostrar
    """
    print("\n" + "="*80)
    print("RECOMENDAÇÕES DE RENDA FIXA")
    print("="*80)

    # Mostra o CDI atual
    selic, cdi = coletar_indicadores()
    print(f"\n📊 Selic: {selic:.2%} | CDI: {cdi:.2%}\n")

    for perfil_nome, perfil_id in [("Conservador (1)", 1), 
                                   ("Moderado (2)", 2), 
                                   ("Agressivo (3)", 3)]:
        print(f"\n--- Perfil: {perfil_nome} ---")
        recomendacoes = rankear_rf(perfil=perfil_id, limite=3, usar_yubb=True)
        
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
# Execução direta (para rodar e ver os prints)
# ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Roda todos os testes com prints habilitados
    pytest.main([__file__, "-v", "-s", "--tb=short"])