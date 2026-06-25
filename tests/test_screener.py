"""Testes básicos do screener de ações e FIIs."""
from acoes_fiis.screener import _score_acao, _score_fii

def test_score_acao_perfil_reage():
    """Score deve variar entre perfis."""
    empresa_div   = {"dy": 12.0, "pl": 8.0, "roe": 15.0, "pvp": 1.2, "liquidez": 5e6, "mktcap_proxy": 0}
    empresa_cresc = {"dy": 1.0,  "pl": 30.0,"roe": 35.0, "pvp": 5.0, "liquidez": 5e6, "mktcap_proxy": 0}
    s1d, _ = _score_acao(empresa_div,   1)
    s3d, _ = _score_acao(empresa_div,   3)
    s1c, _ = _score_acao(empresa_cresc, 1)
    s3c, _ = _score_acao(empresa_cresc, 3)
    assert s1d > s1c, "Conservador deve preferir dividendos"
    assert s3c > s3d, "Agressivo deve preferir crescimento"
    print("✅ test_score_acao_perfil_reage")

def test_score_fii_basico():
    fii = {"dy": 11.0, "pvp": 0.95, "liquidez": 2e6, "vacancia": 0}
    s1, m1 = _score_fii(fii, 1)
    s2, m2 = _score_fii(fii, 2)
    assert s1 > 0 and s2 > 0
    print("✅ test_score_fii_basico")

if __name__ == "__main__":
    test_score_acao_perfil_reage()
    test_score_fii_basico()
    print("Todos os testes passaram.")

# pytest tests/test_screener.py -v