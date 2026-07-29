"""Funções puras de matemática financeira usadas nas projeções."""

from __future__ import annotations

import math
from collections.abc import Callable


TaxRule = Callable[[float], float]


def _numero_finito(nome: str, valor: float) -> float:
    if isinstance(valor, bool):
        raise TypeError(f"{nome} deve ser numérico, não booleano.")
    try:
        convertido = float(valor)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{nome} deve ser numérico.") from exc
    if not math.isfinite(convertido):
        raise ValueError(f"{nome} deve ser finito.")
    return convertido


def _validar_fluxo(
    cap: float,
    ap: float,
    taxa_a: float,
    anos: float,
) -> tuple[float, float, float, float]:
    cap = _numero_finito("cap", cap)
    ap = _numero_finito("ap", ap)
    taxa_a = _numero_finito("taxa_a", taxa_a)
    anos = _numero_finito("anos", anos)

    if cap < 0:
        raise ValueError("cap não pode ser negativo.")
    if ap < 0:
        raise ValueError("ap não pode ser negativo.")
    if taxa_a <= -1:
        raise ValueError("taxa_a deve ser maior que -100%.")
    if anos < 0:
        raise ValueError("anos não pode ser negativo.")
    return cap, ap, taxa_a, anos


def _meses(anos: float) -> int:
    """Converte anos em meses, aceitando pequenas imprecisões de ponto flutuante."""
    anos = _numero_finito("anos", anos)
    if anos < 0:
        raise ValueError("anos não pode ser negativo.")
    return int(round(anos * 12.0))


def _taxa_mensal(taxa_a: float) -> float:
    taxa_a = _numero_finito("taxa_a", taxa_a)
    if taxa_a <= -1:
        raise ValueError("taxa_a deve ser maior que -100%.")
    return math.expm1(math.log1p(taxa_a) / 12.0)


def _fator_mensal(taxa_m: float, meses: int) -> float:
    if meses == 0:
        return 1.0
    return math.exp(math.log1p(taxa_m) * meses)


def _vf_bruto(
    cap: float,
    ap: float,
    taxa_a: float,
    anos: float,
) -> float:
    """
    Valor futuro bruto.

    Os aportes são considerados no fim de cada mês (anuidade postecipada).
    """
    cap, ap, taxa_a, anos = _validar_fluxo(cap, ap, taxa_a, anos)
    meses = _meses(anos)
    taxa_m = _taxa_mensal(taxa_a)
    fator = _fator_mensal(taxa_m, meses)
    valor_capital = cap * fator

    if ap == 0 or meses == 0:
        return valor_capital
    if abs(taxa_m) <= 1e-12:
        return valor_capital + ap * meses
    valor_aportes = ap * (fator - 1.0) / taxa_m
    return valor_capital + valor_aportes


def _aliquota_valida(aliquota: float) -> float:
    aliquota = _numero_finito("aliq", aliquota)
    if not 0 <= aliquota <= 1:
        raise ValueError("aliq deve estar entre 0 e 1.")
    return aliquota


def _regra_dinamica(aliq: object) -> TaxRule | None:
    regra = getattr(aliq, "para_prazo", None)
    return regra if callable(regra) else None


def _liquidar_lote(
    principal: float,
    meses_aplicado: int,
    taxa_m: float,
    regra: TaxRule,
    pgbl: bool,
) -> float:
    bruto = principal * _fator_mensal(taxa_m, meses_aplicado)
    aliquota = _aliquota_valida(regra(meses_aplicado / 12.0))
    if pgbl:
        return bruto * (1.0 - aliquota)
    ganho = max(0.0, bruto - principal)
    return bruto - ganho * aliquota


def _vf_liquido_por_fluxos(
    cap: float,
    ap: float,
    taxa_a: float,
    anos: float,
    regra: TaxRule,
    pgbl: bool = False,
) -> float:
    """
    Liquida cada aporte conforme seu próprio tempo de permanência.

    Isso é necessário para tabelas regressivas: um aporte feito no último ano
    não pode receber a mesma alíquota de outro mantido por dez anos.
    """
    cap, ap, taxa_a, anos = _validar_fluxo(cap, ap, taxa_a, anos)
    meses = _meses(anos)
    taxa_m = _taxa_mensal(taxa_a)

    liquido = _liquidar_lote(cap, meses, taxa_m, regra, pgbl)
    for meses_aplicado in range(meses):
        liquido += _liquidar_lote(
            ap,
            meses_aplicado,
            taxa_m,
            regra,
            pgbl,
        )
    return liquido


def _vf_liquido(
    cap: float,
    ap: float,
    taxa_a: float,
    anos: float,
    aliq: float,
    pgbl: bool = False,
) -> float:
    """
    Valor futuro líquido.

    Para uma alíquota numérica simples, o imposto incide no resgate final:
    sobre os ganhos nos produtos comuns e sobre o saldo total no PGBL.
    Objetos de alíquota com ``para_prazo`` ativam a liquidação por aporte.
    """
    regra = _regra_dinamica(aliq)
    if regra is not None:
        return _vf_liquido_por_fluxos(
            cap,
            ap,
            taxa_a,
            anos,
            regra,
            pgbl,
        )

    cap, ap, taxa_a, anos = _validar_fluxo(cap, ap, taxa_a, anos)
    aliquota = _aliquota_valida(aliq)
    bruto = _vf_bruto(cap, ap, taxa_a, anos)
    principal = cap + ap * _meses(anos)

    if pgbl:
        return bruto * (1.0 - aliquota)
    imposto = max(0.0, bruto - principal) * aliquota
    return bruto - imposto


def _vf_real(valor: float, infl: float, anos: float) -> float:
    """Converte um valor nominal futuro para poder de compra de hoje."""
    valor = _numero_finito("valor", valor)
    infl = _numero_finito("infl", infl)
    anos = _numero_finito("anos", anos)
    if valor < 0:
        raise ValueError("valor não pode ser negativo.")
    if infl <= -1:
        raise ValueError("infl deve ser maior que -100%.")
    if anos < 0:
        raise ValueError("anos não pode ser negativo.")
    return valor / ((1.0 + infl) ** anos)