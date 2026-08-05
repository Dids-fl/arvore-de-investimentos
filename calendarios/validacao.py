"""Validações compartilhadas dos calendários oficiais da B3."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from urllib.parse import urlparse

try:
    import holidays
except ImportError:  # pragma: no cover - dependência declarada no projeto
    holidays = None


@dataclass(frozen=True)
class CalendarioExtraido:
    """Representa datas extraídas antes de sua promoção a calendário oficial."""

    ano: int
    datas: tuple[date, ...]
    hash_conteudo: str = ""


def fonte_b3_oficial(url: str) -> bool:
    """Confirma HTTPS e domínio exato da B3, inclusive subdomínios."""
    if not isinstance(url, str):
        return False
    parsed = urlparse(url)
    hostname = parsed.hostname
    return (
        parsed.scheme == "https"
        and hostname is not None
        and (hostname == "b3.com.br" or hostname.endswith(".b3.com.br"))
    )


def _pascoa(ano: int) -> date:
    """Calcula a Páscoa pelo algoritmo gregoriano de Meeus/Jones/Butcher."""
    a = ano % 19
    b, c = divmod(ano, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = (h + l - 7 * m + 114) % 31 + 1
    return date(ano, mes, dia)


def fechamentos_minimos(ano: int) -> frozenset[date]:
    """Retorna o piso mecânico esperado, sem se declarar calendário B3."""
    esperados: set[date] = set()
    if holidays is not None:
        for feriado in holidays.country_holidays("BR", years=[ano]):
            if feriado.weekday() < 5:
                esperados.add(feriado)

    pascoa = _pascoa(ano)
    esperados.update(
        {
            pascoa - timedelta(days=48),
            pascoa - timedelta(days=47),
            pascoa - timedelta(days=2),
            pascoa + timedelta(days=60),
        }
    )
    return frozenset(esperados)


def validar_calendario_extraido(
    calendario: CalendarioExtraido,
    *,
    anos_permitidos: Iterable[int],
) -> None:
    """Rejeita ano incorreto, extração parcial ou calendário incoerente."""
    permitidos = {int(ano) for ano in anos_permitidos}
    if calendario.ano not in permitidos:
        raise ValueError("O calendário não pertence a um ano permitido.")
    if len(calendario.datas) < 8 or len(calendario.datas) > 30:
        raise ValueError("Quantidade anormal de fechamentos no calendário B3.")
    if len(calendario.datas) != len(set(calendario.datas)):
        raise ValueError("O calendário B3 contém datas duplicadas.")
    if any(item.year != calendario.ano for item in calendario.datas):
        raise ValueError("O calendário B3 contém data de outro ano.")

    ausentes = fechamentos_minimos(calendario.ano) - set(calendario.datas)
    if ausentes:
        datas = ", ".join(item.isoformat() for item in sorted(ausentes))
        raise ValueError(
            "O calendário não contém fechamentos mínimos esperados: " + datas
        )
