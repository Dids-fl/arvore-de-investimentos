"""Contratos do motor de tributação estimada."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Any


class PrecisaoTributaria(StrEnum):
    EXATA_PARA_PREMISSAS = "exata_para_premissas"
    ESTIMADA = "estimada"
    INDETERMINADA = "indeterminada"


def _numero(
    nome: str,
    valor: object,
    *,
    minimo: float = 0.0,
) -> float:
    if isinstance(valor, bool):
        raise TypeError(f"{nome} não pode ser booleano.")
    try:
        numero = float(valor)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{nome} deve ser numérico.") from exc
    if not math.isfinite(numero) or numero < minimo:
        raise ValueError(f"{nome} deve ser finito e >= {minimo}.")
    return numero


@dataclass(frozen=True)
class ContextoTributario:
    principal: float
    valor_bruto: float
    data_aplicacao: date
    data_resgate: date
    tipo_produto: str
    regime: str | None = None
    renda_tributavel: float | None = None
    valor_vendas_mes: float | None = None
    valor_aportes_ano: float | None = None
    day_trade: bool = False
    pessoa_fisica: bool = True
    metadados: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "principal", _numero("principal", self.principal))
        object.__setattr__(
            self,
            "valor_bruto",
            _numero("valor_bruto", self.valor_bruto),
        )
        if not isinstance(self.data_aplicacao, date):
            raise TypeError("data_aplicacao deve ser datetime.date.")
        if not isinstance(self.data_resgate, date):
            raise TypeError("data_resgate deve ser datetime.date.")
        if self.data_resgate < self.data_aplicacao:
            raise ValueError("data_resgate não pode anteceder data_aplicacao.")
        if not isinstance(self.tipo_produto, str) or not self.tipo_produto.strip():
            raise ValueError("tipo_produto deve ser um texto não vazio.")
        object.__setattr__(
            self,
            "tipo_produto",
            self.tipo_produto.strip().casefold(),
        )
        if self.regime is not None:
            if not isinstance(self.regime, str):
                raise TypeError("regime deve ser texto ou None.")
            object.__setattr__(self, "regime", self.regime.strip().casefold())
        for campo in (
            "renda_tributavel",
            "valor_vendas_mes",
            "valor_aportes_ano",
        ):
            valor = getattr(self, campo)
            if valor is not None:
                object.__setattr__(self, campo, _numero(campo, valor))
        if not isinstance(self.metadados, Mapping):
            raise TypeError("metadados deve ser um mapeamento.")

    @property
    def ganho(self) -> float:
        return max(0.0, self.valor_bruto - self.principal)

    @property
    def prazo_dias(self) -> int:
        return (self.data_resgate - self.data_aplicacao).days

    @property
    def prazo_anos(self) -> float:
        return self.prazo_dias / 365.2425


@dataclass(frozen=True)
class ResultadoTributario:
    imposto_estimado: float | None
    valor_liquido: float | None
    aliquota_efetiva: float | None
    precisao: PrecisaoTributaria
    premissas: tuple[str, ...]
    fonte: str
    vigencia: date
    regra_id: str

    def __post_init__(self) -> None:
        for campo in (
            "imposto_estimado",
            "valor_liquido",
            "aliquota_efetiva",
        ):
            valor = getattr(self, campo)
            if valor is not None:
                object.__setattr__(self, campo, _numero(campo, valor))
        if self.aliquota_efetiva is not None and self.aliquota_efetiva > 1:
            raise ValueError("aliquota_efetiva não pode superar 100%.")


def resultado_calculado(
    contexto: ContextoTributario,
    *,
    imposto: float,
    aliquota: float,
    precisao: PrecisaoTributaria,
    premissas: tuple[str, ...],
    fonte: str,
    vigencia: date,
    regra_id: str,
) -> ResultadoTributario:
    imposto_valido = min(
        _numero("imposto", imposto),
        contexto.valor_bruto,
    )
    return ResultadoTributario(
        imposto_estimado=imposto_valido,
        valor_liquido=contexto.valor_bruto - imposto_valido,
        aliquota_efetiva=_numero("aliquota", aliquota),
        precisao=precisao,
        premissas=premissas,
        fonte=fonte,
        vigencia=vigencia,
        regra_id=regra_id,
    )


def resultado_indeterminado(
    contexto: ContextoTributario,
    *,
    motivo: str,
    fonte: str,
    vigencia: date,
    regra_id: str,
) -> ResultadoTributario:
    del contexto
    return ResultadoTributario(
        imposto_estimado=None,
        valor_liquido=None,
        aliquota_efetiva=None,
        precisao=PrecisaoTributaria.INDETERMINADA,
        premissas=(motivo,),
        fonte=fonte,
        vigencia=vigencia,
        regra_id=regra_id,
    )
