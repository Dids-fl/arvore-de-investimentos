"""Formatação de valores no padrão brasileiro."""

from __future__ import annotations

import math
import re


def formatar_brl(valor: float | int | None, casas: int = 2) -> str:
    """Formata ``1234.5`` como ``R$ 1.234,50``; ``None`` vira "indeterminado"."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return "indeterminado"
    if not math.isfinite(valor):
        return "indeterminado"
    texto = f"{abs(valor):,.{casas}f}"
    texto = texto.replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    sinal = "-" if valor < 0 and round(abs(valor), casas) != 0 else ""
    return f"{sinal}R$ {texto}"


_MILHAR_BR = re.compile(r"^-?\d{1,3}(\.\d{3})+$")


def interpretar_numero(texto: str) -> float:
    """Lê números digitados no padrão brasileiro ou internacional.

    Exemplos: ``"1.000"`` → 1000, ``"1.000,50"`` → 1000.5,
    ``"1500,5"`` → 1500.5, ``"1500.5"`` → 1500.5, ``"R$ 2.000"`` → 2000.
    Levanta ``ValueError`` para texto inválido.
    """
    limpo = texto.strip().replace("R$", "").replace(" ", "")
    if not limpo:
        raise ValueError("número vazio")
    if "," in limpo:
        limpo = limpo.replace(".", "").replace(",", ".")
    elif _MILHAR_BR.match(limpo):
        limpo = limpo.replace(".", "")
    return float(limpo)
