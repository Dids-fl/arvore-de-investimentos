from calculos import _vf_bruto, _vf_liquido

def test_vf_bruto():
    res = _vf_bruto(1000, 100, 0.10, 5)
    assert round(res, 2) == 1610.51

def test_vf_liquido():
    res = _vf_liquido(10000, 0, 0.10, 2, 0.15)
    assert round(res, 2) == 11785.00