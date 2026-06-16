def _meses(anos: float) -> int:
    return int(anos * 12)


def _vf_bruto(cap: float, ap: float, taxa_a: float, anos: float) -> float:
    tm  = (1 + taxa_a) ** (1.0 / 12) - 1
    m   = _meses(anos)
    vfc = cap * ((1 + taxa_a) ** anos)
    vfa = ap * (((1 + tm) ** m - 1) / tm) if (ap > 0 and tm > 1e-12) else ap * m
    return vfc + vfa


def _vf_liquido(cap: float, ap: float, taxa_a: float, anos: float,
                aliq: float, pgbl: bool = False) -> float:
    """
    IR incide apenas no resgate final, sobre os GANHOS (não sobre o principal).
    Verificação: cap=10000, ap=0, taxa=10%, anos=2, aliq=15%
      VF=12100  Ganho=2100  IR=315  VF_líq=11785 ✓
    """
    vfb       = _vf_bruto(cap, ap, taxa_a, anos)
    principal = cap + ap * _meses(anos)
    if pgbl:
        return vfb * (1 - aliq)
    ganho = max(0.0, vfb - principal)
    return principal + ganho * (1 - aliq)


def _vf_real(valor: float, infl: float, anos: float) -> float:
    return valor / ((1 + infl) ** anos)