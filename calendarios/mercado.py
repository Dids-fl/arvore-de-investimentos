"""Carrega calendários B3 confirmados e gera fallback provisório."""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

from calendarios.validacao import (
    CalendarioExtraido,
    fonte_b3_oficial,
    validar_calendario_extraido,
)

try:
    import holidays
except ImportError:  # pragma: no cover - dependência declarada no projeto
    holidays = None

_DIRETORIO_B3 = Path(__file__).with_name("b3")


def _diretorio_cache_b3() -> Path:
    personalizado = os.getenv("RECOMENDADOR_CALENDARIOS_CACHE_DIR")
    if personalizado:
        return Path(personalizado).expanduser()
    return (
        Path.home()
        / ".cache"
        / "recomendador_investimentos"
        / "calendarios"
        / "b3"
    )


def _arquivos_calendario(ano: int) -> tuple[Path, ...]:
    cache = _diretorio_cache_b3() / f"{ano}.json"
    versionado = _DIRETORIO_B3 / f"{ano}.json"
    return tuple(
        arquivo
        for arquivo in (cache, versionado)
        if arquivo.exists()
    )


@dataclass(frozen=True)
class CalendarioMercado:
    """Calendário consolidado com rastreabilidade da confirmação anual."""

    feriados: frozenset[date]
    anos_confirmados: frozenset[int]
    anos_provisorios: frozenset[int]
    fontes: tuple[str, ...]
    avisos: tuple[str, ...]


def _data_iso(valor: object, *, contexto: str) -> date:
    if not isinstance(valor, str):
        raise TypeError(f"{contexto} deve ser texto ISO AAAA-MM-DD.")
    try:
        return date.fromisoformat(valor)
    except ValueError as exc:
        raise ValueError(f"{contexto} deve usar AAAA-MM-DD.") from exc


@lru_cache(maxsize=64)
def carregar_ano(ano: int) -> CalendarioMercado:
    """Carrega um ano confirmado; sem arquivo, usa feriados BR provisórios."""
    if isinstance(ano, bool) or not isinstance(ano, int):
        raise TypeError("ano deve ser inteiro.")
    if ano < 2000 or ano > 2200:
        raise ValueError("ano deve estar entre 2000 e 2200.")

    falhas: list[str] = []
    for arquivo in _arquivos_calendario(ano):
        try:
            dados = json.loads(arquivo.read_text(encoding="utf-8"))
            if dados.get("ano") != ano:
                raise ValueError(f"Ano inconsistente em {arquivo}.")
            if dados.get("status") != "confirmado":
                raise ValueError(
                    f"Arquivo {arquivo} não pode ser tratado como confirmado."
                )
            fonte = dados.get("fonte")
            if not fonte_b3_oficial(fonte):
                raise ValueError(f"Fonte oficial ausente em {arquivo}.")
            valores = dados.get("dias_sem_negociacao")
            if not isinstance(valores, list):
                raise TypeError(f"dias_sem_negociacao inválido em {arquivo}.")
            datas = tuple(
                _data_iso(valor, contexto=f"calendário B3 {ano}")
                for valor in valores
            )
            validar_calendario_extraido(
                CalendarioExtraido(
                    ano=ano,
                    datas=datas,
                    hash_conteudo=str(dados.get("hash_fonte", "")),
                ),
                anos_permitidos=(ano,),
            )
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            falhas.append(f"{arquivo}: {exc}")
            continue

        avisos = (
            ("Calendário inválido descartado: " + " | ".join(falhas),)
            if falhas
            else ()
        )
        return CalendarioMercado(
            feriados=frozenset(datas),
            anos_confirmados=frozenset({ano}),
            anos_provisorios=frozenset(),
            fontes=(fonte,),
            avisos=avisos,
        )

    if holidays is None:
        return CalendarioMercado(
            feriados=frozenset(),
            anos_confirmados=frozenset(),
            anos_provisorios=frozenset({ano}),
            fontes=(),
            avisos=tuple(falhas)
            + (
                (
                    f"Calendário B3 {ano} ausente e biblioteca holidays não "
                    "instalada; apenas fins de semana serão considerados."
                ),
            ),
        )

    nacionais = holidays.country_holidays("BR", years=[ano])
    return CalendarioMercado(
        feriados=frozenset(nacionais),
        anos_confirmados=frozenset(),
        anos_provisorios=frozenset({ano}),
        fontes=("https://pypi.org/project/holidays/",),
        avisos=tuple(falhas)
        + (
            (
                f"Calendário B3 {ano} ainda não foi confirmado. Foram usados "
                "somente feriados nacionais calculados; fechamentos especiais "
                "da B3 podem estar ausentes."
            ),
        ),
    )


def carregar_intervalo(
    ano_inicial: int,
    ano_final: int,
    *,
    feriados_adicionais: Iterable[date | str] | None = None,
    anos_confirmados_manualmente: Iterable[int] | None = None,
) -> CalendarioMercado:
    """Consolida anos e permite complementos explicitamente informados."""
    if ano_final < ano_inicial:
        raise ValueError("ano_final deve ser maior ou igual a ano_inicial.")

    feriados: set[date] = set()
    confirmados: set[int] = set()
    provisorios: set[int] = set()
    fontes: list[str] = []
    avisos: list[str] = []
    for ano in range(ano_inicial, ano_final + 1):
        calendario = carregar_ano(ano)
        feriados.update(calendario.feriados)
        confirmados.update(calendario.anos_confirmados)
        provisorios.update(calendario.anos_provisorios)
        fontes.extend(calendario.fontes)
        avisos.extend(calendario.avisos)

    if feriados_adicionais is not None:
        if isinstance(feriados_adicionais, (str, bytes)):
            raise TypeError("feriados_adicionais deve ser uma coleção.")
        for indice, valor in enumerate(feriados_adicionais):
            if isinstance(valor, date):
                feriados.add(valor)
            else:
                feriados.add(
                    _data_iso(valor, contexto=f"feriado adicional {indice}")
                )

    if anos_confirmados_manualmente is not None:
        for valor in anos_confirmados_manualmente:
            ano = int(valor)
            confirmados.add(ano)
            provisorios.discard(ano)

    return CalendarioMercado(
        feriados=frozenset(feriados),
        anos_confirmados=frozenset(confirmados),
        anos_provisorios=frozenset(provisorios),
        fontes=tuple(dict.fromkeys(fontes)),
        avisos=tuple(dict.fromkeys(avisos)),
    )
