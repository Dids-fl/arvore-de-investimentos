"""
Testes das funções de projeção financeira (calculos.py).

Verificações matemáticas manuais:
  _vf_bruto(1000, 0, 0.10, 5):
    1000 × (1.10)^5 = 1000 × 1.61051 = 1610.51 ✓

  _vf_liquido(10000, 0, 0.10, 2, 0.15):
    VF bruto = 10000 × 1.10^2 = 12100
    Ganho    = 12100 - 10000 = 2100
    IR       = 2100 × 0.15  = 315
    VF líq.  = 12100 - 315  = 11785.00 ✓

  _vf_liquido(1000, 0, 0.10, 5, 0.15):
    VF bruto = 1610.51
    Ganho    = 610.51
    IR       = 91.58
    VF líq.  = 1518.93 ✓
"""
from calculos import _vf_bruto, _vf_liquido


def test_vf_bruto_sem_aporte():
    """Capital cresce sozinho por 5 anos a 10% a.a."""
    res = _vf_bruto(1000, 0, 0.10, 5)
    assert round(res, 2) == 1610.51


def test_vf_bruto_com_aporte():
    """Com aportes mensais o valor final deve ser maior."""
    sem_aporte = _vf_bruto(1000, 0,   0.10, 5)
    com_aporte = _vf_bruto(1000, 100, 0.10, 5)
    assert com_aporte > sem_aporte


def test_vf_liquido_desconta_ir():
    """IR de 15% sobre ganhos deve reduzir o valor bruto."""
    res = _vf_liquido(10000, 0, 0.10, 2, 0.15)
    assert round(res, 2) == 11785.00


def test_vf_liquido_cinco_anos():
    res = _vf_liquido(1000, 0, 0.10, 5, 0.15)
    assert round(res, 2) == 1518.93


def test_vf_liquido_menor_que_bruto():
    """Valor líquido deve ser sempre menor ou igual ao bruto."""
    bruto  = _vf_bruto(5000, 0, 0.12, 10)
    liquido = _vf_liquido(5000, 0, 0.12, 10, 0.15)
    assert liquido < bruto

# pytest tests/test_calculos.py -v