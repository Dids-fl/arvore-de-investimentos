"""
Construção de uma curva mensal projetada para a SELIC.

O módulo não consulta APIs. Ele recebe:

* a meta SELIC atual, em formato decimal;
* as medianas anuais do Focus, também em formato decimal;
* o prazo da projeção, em meses.

As expectativas anuais do Focus representam taxas esperadas para o fim de
cada ano. Por isso, elas são tratadas como pontos da curva em dezembro, e não
como rentabilidades médias válidas para o ano inteiro.
"""

from __future__ import annotations

import calendar
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Final


_LIMITE_TAXA_ANUAL: Final = 2.0


@dataclass(frozen=True, slots=True)
class PontoCurvaSelic:
    """Taxa aplicável a um mês da curva projetada."""

    data: date
    taxa_anual: float
    taxa_mensal: float
    origem: str
    extrapolado: bool = False


@dataclass(frozen=True, slots=True)
class ProjecaoSelic:
    """Resumo da projeção composta ao longo do prazo solicitado."""

    data_base: date
    prazo_meses: int
    taxa_acumulada: float
    taxa_anual_equivalente: float
    meses_extrapolados: int
    curva_mensal: tuple[PontoCurvaSelic, ...]
    avisos: tuple[str, ...] = ()


def _validar_taxa(taxa: object, nome: str) -> float:
    try:
        valor = float(taxa)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{nome} deve ser uma taxa numérica.") from exc

    if not math.isfinite(valor):
        raise ValueError(f"{nome} deve ser finita.")
    if valor <= -1:
        raise ValueError(f"{nome} deve ser maior que -100%.")
    if valor > _LIMITE_TAXA_ANUAL:
        raise ValueError(
            f"{nome}={valor!r} parece estar em percentual. "
            "Informe taxas em decimal; por exemplo, 14% deve ser 0.14."
        )
    return valor


def _normalizar_focus(
    focus_por_ano: Mapping[int | str, float] | None,
    *,
    data_base: date,
) -> dict[int, float]:
    if focus_por_ano is None:
        return {}
    if not isinstance(focus_por_ano, Mapping):
        raise TypeError("focus_por_ano deve ser um mapeamento ano -> taxa.")

    resultado: dict[int, float] = {}

    for ano_bruto, taxa_bruta in focus_por_ano.items():
        try:
            ano = int(ano_bruto)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Ano Focus inválido: {ano_bruto!r}.") from exc

        if ano < 1900 or ano > 9999:
            raise ValueError(f"Ano Focus fora do intervalo válido: {ano}.")

        taxa = _validar_taxa(taxa_bruta, f"Focus SELIC {ano}")

        # Uma expectativa de dezembro anterior à data-base não pode afetar
        # uma projeção iniciada hoje.
        if ano < data_base.year:
            continue

        resultado[ano] = taxa

    return dict(sorted(resultado.items()))


def _indice_mes(ano: int, mes: int) -> int:
    return ano * 12 + mes


def _somar_meses(data_base: date, quantidade: int) -> date:
    indice = data_base.year * 12 + (data_base.month - 1) + quantidade
    ano, mes_zero = divmod(indice, 12)
    mes = mes_zero + 1
    dia = min(data_base.day, calendar.monthrange(ano, mes)[1])
    return date(ano, mes, dia)


def _interpolar(
    indice: int,
    indice_inicial: int,
    taxa_inicial: float,
    indice_final: int,
    taxa_final: float,
) -> float:
    if indice_final <= indice_inicial:
        return taxa_final

    peso = (indice - indice_inicial) / (indice_final - indice_inicial)
    peso = min(max(peso, 0.0), 1.0)
    return taxa_inicial + peso * (taxa_final - taxa_inicial)


def _taxa_mensal_equivalente(taxa_anual: float) -> float:
    return (1.0 + taxa_anual) ** (1.0 / 12.0) - 1.0


def construir_curva_selic_mensal(
    *,
    selic_atual: float,
    focus_por_ano: Mapping[int | str, float] | None,
    prazo_meses: int,
    data_base: date | None = None,
) -> tuple[PontoCurvaSelic, ...]:
    """
    Constrói a curva mensal entre a SELIC atual e os pontos anuais do Focus.

    Entre a data-base e cada dezembro é usada interpolação linear sobre as
    taxas anuais. Depois do último ano disponível, a última taxa Focus é
    mantida constante e o ponto é marcado como extrapolado.

    Se o Focus não estiver disponível, a SELIC atual é mantida constante,
    também com marcação de extrapolação.
    """
    base = data_base or date.today()
    if not isinstance(base, date):
        raise TypeError("data_base deve ser datetime.date.")
    if isinstance(prazo_meses, bool) or not isinstance(prazo_meses, int):
        raise TypeError("prazo_meses deve ser um número inteiro.")
    if prazo_meses <= 0:
        raise ValueError("prazo_meses deve ser maior que zero.")

    taxa_atual = _validar_taxa(selic_atual, "SELIC atual")
    focus = _normalizar_focus(focus_por_ano, data_base=base)

    indice_base = _indice_mes(base.year, base.month)
    nos: list[tuple[int, float, str]] = [
        (indice_base, taxa_atual, "selic_atual")
    ]

    for ano, taxa in focus.items():
        indice_dezembro = _indice_mes(ano, 12)
        if indice_dezembro > indice_base:
            nos.append(
                (
                    indice_dezembro,
                    taxa,
                    f"focus_fim_{ano}",
                )
            )

    nos.sort(key=lambda item: item[0])
    tem_focus_util = len(nos) > 1
    ultimo_indice_observado = nos[-1][0]
    curva: list[PontoCurvaSelic] = []

    for deslocamento in range(1, prazo_meses + 1):
        data_mes = _somar_meses(base, deslocamento)
        indice = _indice_mes(data_mes.year, data_mes.month)

        no_anterior = nos[0]
        no_posterior: tuple[int, float, str] | None = None

        for no in nos[1:]:
            if indice <= no[0]:
                no_posterior = no
                break
            no_anterior = no

        if no_posterior is not None:
            taxa_anual = _interpolar(
                indice,
                no_anterior[0],
                no_anterior[1],
                no_posterior[0],
                no_posterior[1],
            )
            origem = (
                no_posterior[2]
                if indice == no_posterior[0]
                else f"interpolacao_ate_{no_posterior[2]}"
            )
            extrapolado = False
        else:
            taxa_anual = nos[-1][1]
            origem = (
                f"extrapolacao_{nos[-1][2]}"
                if tem_focus_util
                else "selic_atual_constante_sem_focus"
            )
            extrapolado = indice > ultimo_indice_observado

        curva.append(
            PontoCurvaSelic(
                data=data_mes,
                taxa_anual=taxa_anual,
                taxa_mensal=_taxa_mensal_equivalente(taxa_anual),
                origem=origem,
                extrapolado=extrapolado,
            )
        )

    return tuple(curva)


def projetar_selic(
    *,
    selic_atual: float,
    focus_por_ano: Mapping[int | str, float] | None,
    prazo_meses: int,
    data_base: date | None = None,
) -> ProjecaoSelic:
    """Constrói a curva e calcula o retorno composto do período."""
    base = data_base or date.today()
    curva = construir_curva_selic_mensal(
        selic_atual=selic_atual,
        focus_por_ano=focus_por_ano,
        prazo_meses=prazo_meses,
        data_base=base,
    )

    fator = math.prod(1.0 + ponto.taxa_mensal for ponto in curva)
    taxa_acumulada = fator - 1.0
    taxa_anual_equivalente = fator ** (12.0 / prazo_meses) - 1.0
    meses_extrapolados = sum(ponto.extrapolado for ponto in curva)
    tem_focus_util = any(
        "focus" in ponto.origem
        for ponto in curva
    )

    avisos: list[str] = []
    if not tem_focus_util:
        avisos.append(
            "Focus SELIC indisponível; a SELIC atual foi mantida constante."
        )
    if meses_extrapolados:
        avisos.append(
            f"{meses_extrapolados} mês(es) ficaram além do último ponto "
            "Focus e usam a última taxa disponível como hipótese terminal."
        )

    return ProjecaoSelic(
        data_base=base,
        prazo_meses=prazo_meses,
        taxa_acumulada=taxa_acumulada,
        taxa_anual_equivalente=taxa_anual_equivalente,
        meses_extrapolados=meses_extrapolados,
        curva_mensal=curva,
        avisos=tuple(avisos),
    )


def calcular_taxa_selic_equivalente(
    *,
    selic_atual: float,
    focus_por_ano: Mapping[int | str, float] | None,
    prazo_meses: int,
    data_base: date | None = None,
) -> float:
    """Atalho para obter somente a taxa anual equivalente da projeção."""
    return projetar_selic(
        selic_atual=selic_atual,
        focus_por_ano=focus_por_ano,
        prazo_meses=prazo_meses,
        data_base=data_base,
    ).taxa_anual_equivalente
