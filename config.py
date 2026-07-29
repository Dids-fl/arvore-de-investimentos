"""Configurações centrais do recomendador de investimentos."""

from __future__ import annotations

import math
import os
from typing import Final

try:
    from dotenv import load_dotenv
except ImportError:  # O projeto continua utilizável sem arquivo .env.
    load_dotenv = None


if load_dotenv is not None:
    load_dotenv()


def _env_texto(nome: str) -> str | None:
    valor = os.getenv(nome)
    if valor is None:
        return None
    valor = valor.strip()
    return valor or None


def _env_float(
    nome: str,
    padrao: float,
    *,
    minimo: float | None = None,
) -> float:
    bruto = _env_texto(nome)
    if bruto is None:
        return padrao
    try:
        valor = float(bruto.replace(",", "."))
    except ValueError as exc:
        raise ValueError(f"{nome} deve ser numérico, não {bruto!r}.") from exc
    if not math.isfinite(valor):
        raise ValueError(f"{nome} deve ser finito.")
    if minimo is not None and valor < minimo:
        raise ValueError(f"{nome} deve ser maior ou igual a {minimo}.")
    return valor


def _env_int(
    nome: str,
    padrao: int,
    *,
    minimo: int | None = None,
) -> int:
    bruto = _env_texto(nome)
    if bruto is None:
        return padrao
    try:
        valor = int(bruto)
    except ValueError as exc:
        raise ValueError(f"{nome} deve ser inteiro, não {bruto!r}.") from exc
    if minimo is not None and valor < minimo:
        raise ValueError(f"{nome} deve ser maior ou igual a {minimo}.")
    return valor


def _env_bool(nome: str, padrao: bool) -> bool:
    bruto = _env_texto(nome)
    if bruto is None:
        return padrao
    normalizado = bruto.casefold()
    if normalizado in {"1", "true", "sim", "yes", "on"}:
        return True
    if normalizado in {"0", "false", "não", "nao", "no", "off"}:
        return False
    raise ValueError(
        f"{nome} deve ser um booleano: true/false, sim/não ou 1/0."
    )


def _env_lista(nome: str) -> list[str]:
    bruto = _env_texto(nome)
    if bruto is None:
        return []
    return [
        item.strip()
        for item in bruto.split(",")
        if item.strip()
    ]


# ── Tributação usada nas simulações ─────────────────────────────────────────
# As constantes abaixo representam as alíquotas finais de longo prazo. Regras
# regressivas por prazo são tratadas em core/catalogo.py.
IR_RF: Final = 0.15
IR_ACOES: Final = 0.15
IR_VGBL: Final = 0.10
IR_PGBL: Final = 0.10
IR_LCI: Final = 0.00
IR_FII: Final = 0.20
IR_CRIPTO: Final = 0.15

# Limite em dias, alíquota. None representa prazo acima do último limite.
IR_RF_REGRESSIVO: Final = (
    (180, 0.225),
    (360, 0.20),
    (720, 0.175),
    (None, 0.15),
)

# Na previdência regressiva, cada aporte possui seu próprio tempo de
# permanência. O cálculo por lote é feito em calculos.py.
IR_PREVIDENCIA_REGRESSIVO: Final = (
    (2.0, 0.35),
    (4.0, 0.30),
    (6.0, 0.25),
    (8.0, 0.20),
    (10.0, 0.15),
    (None, 0.10),
)


# ── HTTP, tentativas e paralelismo ───────────────────────────────────────────
REQUEST_CONNECT_TIMEOUT: Final = _env_float(
    "REQUEST_CONNECT_TIMEOUT",
    5.0,
    minimo=0.1,
)
REQUEST_READ_TIMEOUT: Final = _env_float(
    "REQUEST_READ_TIMEOUT",
    15.0,
    minimo=0.1,
)
REQUEST_TIMEOUT: Final = (
    REQUEST_CONNECT_TIMEOUT,
    REQUEST_READ_TIMEOUT,
)
MAX_RETRIES: Final = _env_int("MAX_RETRIES", 3, minimo=0)
RETRY_BACKOFF: Final = _env_float("RETRY_BACKOFF", 0.5, minimo=0.0)
MAX_WORKERS_ATIVOS: Final = _env_int(
    "MAX_WORKERS_ATIVOS",
    4,
    minimo=1,
)


# ── Credenciais opcionais ────────────────────────────────────────────────────
BRAPI_TOKEN: Final = _env_texto("BRAPI_TOKEN")
FMP_API_KEY: Final = _env_texto("FMP_API_KEY")


# ── Filtros dos rankings de ações ────────────────────────────────────────────
USE_FUNDAMENTUS: Final = _env_bool("USE_FUNDAMENTUS", True)
FILTRO_SETORES: list[str] = _env_lista("FILTRO_SETORES")
FILTRO_GOVERNANCA: list[str] = _env_lista("FILTRO_GOVERNANCA")

LIMITE_MKTCAP: Final = {
    1: _env_float("MKTCAP_CONSERVADOR", 2_000_000_000.0, minimo=0.0),
    2: _env_float("MKTCAP_MODERADO", 1_000_000_000.0, minimo=0.0),
    3: _env_float("MKTCAP_AGRESSIVO", 500_000_000.0, minimo=0.0),
}