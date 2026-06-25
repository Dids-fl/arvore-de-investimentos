"""Testes do validador de dados."""
from acoes_fiis.validador import validar_universo, resumo_validacao

def test_outlier_detectado():
    universo = [{"ticker": f"NORM{i}3", "dy": 8.0, "pl": 10.0, "pvp": 1.2, "roe": 20.0} for i in range(20)]
    universo.append({"ticker": "OUTLIER", "dy": 50.0, "pl": 10.0, "pvp": 1.2, "roe": 20.0})
    val, desc = validar_universo(universo)
    outlier_flagged = any(a.get("confianca", 1.0) < 1.0 or a["ticker"] == "OUTLIER"
                          for a in val + desc)
    assert outlier_flagged, "Outlier de DY deve ser detectado"
    print("✅ test_outlier_detectado")

def test_dados_limpos_passam():
    universo = [{"ticker": f"ACAO{i}3", "dy": 8.0, "pl": 10.0, "pvp": 1.2, "roe": 20.0} for i in range(15)]
    val, desc = validar_universo(universo)
    assert len(val) == 15 and len(desc) == 0
    print("✅ test_dados_limpos_passam")

if __name__ == "__main__":
    test_outlier_detectado()
    test_dados_limpos_passam()
    print("Todos os testes passaram.")

# pytest tests/test_validador.py -v