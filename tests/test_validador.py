from validador import validar_universo

def test_validar_universo():
    universo = [
        {"ticker": "A", "dy": 10, "pl": 10, "pvp": 1, "roe": 20},
        {"ticker": "B", "dy": 35, "pl": 100, "pvp": 0.2, "roe": 250},
    ]
    validados, descartados = validar_universo(universo)
    assert len(validados) == 1
    assert len(descartados) == 1
    assert descartados[0]["ticker"] == "B"