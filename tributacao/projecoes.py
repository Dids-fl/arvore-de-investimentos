"""Projeções tributárias prospectivas que dependem da ordem dos fluxos."""

from __future__ import annotations

import calendar
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta

from calendarios.mercado import carregar_intervalo
from tributacao.regras import (
    COME_COTAS_ALIQUOTAS,
    FUNDO_CURTO_PRAZO_DIAS,
    IOF_RENDA_FIXA_DIAS,
    aliquota_por_limite,
    aliquota_rf,
)

FUNDOS_COM_COME_COTAS = {
    "fundo_curto_prazo",
    "fundo_longo_prazo",
    "fundo_rf",
}

@dataclass
class _LoteFundo:
    principal: float
    saldo: float
    base_pos_come_cotas: float
    data_aplicacao: date
    ganho_antecipado: float = 0.0
    come_cotas_pago: float = 0.0


@dataclass(frozen=True)
class ProjecaoComeCotas:
    """Resultado auditável da simulação prospectiva de come-cotas."""

    principal: float
    bruto_sem_tributos: float
    saldo_antes_resgate: float
    come_cotas_pago: float
    come_cotas_historico_informado: float
    ir_no_resgate: float
    iof_no_resgate: float
    imposto_total: float
    valor_liquido: float
    custo_oportunidade_come_cotas: float
    eventos_come_cotas: int
    datas_eventos_come_cotas: tuple[str, ...]
    feriados_considerados: int
    anos_sem_calendario_confirmado: tuple[int, ...]
    quantidade_lotes: int
    data_resgate: date
    premissas: tuple[str, ...]


def _numero_finito(
    nome: str,
    valor: object,
    *,
    minimo: float | None = None,
) -> float:
    if isinstance(valor, bool):
        raise TypeError(f"{nome} não pode ser booleano.")
    try:
        numero = float(valor)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{nome} deve ser numérico.") from exc
    if not math.isfinite(numero):
        raise ValueError(f"{nome} deve ser finito.")
    if minimo is not None and numero < minimo:
        raise ValueError(f"{nome} deve ser >= {minimo}.")
    return numero


def _somar_meses(data_base: date, quantidade: int) -> date:
    indice = data_base.year * 12 + data_base.month - 1 + quantidade
    ano, mes_zero = divmod(indice, 12)
    mes = mes_zero + 1
    dia = min(data_base.day, calendar.monthrange(ano, mes)[1])
    return date(ano, mes, dia)


def _ultimo_dia_util(
    ano: int,
    mes: int,
    feriados: frozenset[date],
) -> date:
    ultimo = date(ano, mes, calendar.monthrange(ano, mes)[1])
    while ultimo.weekday() >= 5 or ultimo in feriados:
        ultimo -= timedelta(days=1)
    return ultimo


def _eventos_entre(
    inicio: date,
    fim: date,
    feriados: frozenset[date],
) -> list[date]:
    eventos = []
    for ano in range(inicio.year, fim.year + 1):
        for mes in (5, 11):
            evento = _ultimo_dia_util(ano, mes, feriados)
            if inicio < evento <= fim:
                eventos.append(evento)
    return eventos


def _data_informada(nome: str, valor: object) -> date:
    if isinstance(valor, date):
        return valor
    if isinstance(valor, str):
        try:
            return date.fromisoformat(valor)
        except ValueError as exc:
            raise ValueError(f"{nome} deve estar no formato AAAA-MM-DD.") from exc
    raise TypeError(f"{nome} deve ser datetime.date ou texto ISO.")


def _lotes_existentes_normalizados(
    lotes_existentes: Iterable[Mapping[str, object]] | None,
    *,
    capital_atual: float,
    data_referencia: date,
) -> tuple[list[_LoteFundo], float]:
    if lotes_existentes is None:
        return [], 0.0
    if isinstance(lotes_existentes, (str, bytes)):
        raise TypeError("lotes_fundo_existentes deve ser uma lista.")
    itens = list(lotes_existentes)
    if not itens:
        return [], 0.0

    lotes: list[_LoteFundo] = []
    saldo_total = 0.0
    historico_total = 0.0
    for indice, item in enumerate(itens):
        if not isinstance(item, Mapping):
            raise TypeError("Cada lote de fundo existente deve ser um mapeamento.")
        principal = _numero_finito(
            f"lote[{indice}].principal",
            item.get("principal"),
            minimo=0.0,
        )
        saldo = _numero_finito(
            f"lote[{indice}].saldo_atual",
            item.get("saldo_atual"),
            minimo=0.0,
        )
        base = _numero_finito(
            f"lote[{indice}].base_tributaria_atual",
            item.get("base_tributaria_atual"),
            minimo=0.0,
        )
        ganho_antecipado = _numero_finito(
            f"lote[{indice}].ganho_antecipado",
            item.get("ganho_antecipado", 0.0),
            minimo=0.0,
        )
        historico = _numero_finito(
            f"lote[{indice}].come_cotas_pago_historico",
            item.get("come_cotas_pago_historico", 0.0),
            minimo=0.0,
        )
        data_aplicacao = _data_informada(
            f"lote[{indice}].data_aplicacao",
            item.get("data_aplicacao"),
        )
        if data_aplicacao > data_referencia:
            raise ValueError("Lote de fundo existente não pode começar no futuro.")
        lotes.append(
            _LoteFundo(
                principal=principal,
                saldo=saldo,
                base_pos_come_cotas=base,
                data_aplicacao=data_aplicacao,
                ganho_antecipado=ganho_antecipado,
                come_cotas_pago=0.0,
            )
        )
        saldo_total += saldo
        historico_total += historico

    tolerancia = max(0.01, capital_atual * 1e-6)
    if abs(saldo_total - capital_atual) > tolerancia:
        raise ValueError(
            "A soma de saldo_atual dos lotes do fundo deve ser igual ao "
            "capital inicial projetado."
        )
    return lotes, historico_total


def _aliquota_final(tipo_produto: str, prazo_dias: int) -> float:
    if tipo_produto == "fundo_curto_prazo":
        return aliquota_por_limite(
            float(max(0, prazo_dias)),
            FUNDO_CURTO_PRAZO_DIAS,
        )
    return aliquota_rf(prazo_dias)


def _aplicar_come_cotas(
    lotes: list[_LoteFundo],
    aliquota: float,
) -> float:
    pago = 0.0
    for lote in lotes:
        ganho = max(0.0, lote.saldo - lote.base_pos_come_cotas)
        imposto = ganho * aliquota
        lote.saldo -= imposto
        lote.base_pos_come_cotas = lote.saldo
        lote.ganho_antecipado += ganho
        lote.come_cotas_pago += imposto
        pago += imposto
    return pago


def projetar_come_cotas(
    cap: float,
    aporte_mensal: float,
    taxa_anual: float,
    meses: int,
    *,
    data_referencia: date,
    tipo_produto: str,
    lotes_existentes: Iterable[Mapping[str, object]] | None = None,
    feriados_adicionais: Iterable[date | str] | None = None,
    anos_calendario_confirmados: Iterable[int] | None = None,
) -> ProjecaoComeCotas:
    """
    Simula somente eventos futuros de come-cotas, por lote de aporte.

    A capitalização permanece mensal para ser coerente com as demais
    projeções do recomendador. O evento é reconhecido quando o último dia útil
    de maio ou novembro cai no intervalo mensal simulado.
    """
    capital = _numero_finito("cap", cap, minimo=0.0)
    aporte = _numero_finito(
        "aporte_mensal",
        aporte_mensal,
        minimo=0.0,
    )
    taxa = _numero_finito("taxa_anual", taxa_anual)
    if taxa <= -1:
        raise ValueError("taxa_anual deve ser maior que -100%.")
    if isinstance(meses, bool) or not isinstance(meses, int):
        raise TypeError("meses deve ser inteiro.")
    if meses < 0:
        raise ValueError("meses não pode ser negativo.")
    if not isinstance(data_referencia, date):
        raise TypeError("data_referencia deve ser datetime.date.")

    tipo = str(tipo_produto).strip().casefold()
    if tipo not in FUNDOS_COM_COME_COTAS:
        raise ValueError(
            "tipo_produto deve ser fundo_curto_prazo, "
            "fundo_longo_prazo ou fundo_rf."
        )

    taxa_mensal = math.expm1(math.log1p(taxa) / 12.0)
    fator_mensal = 1.0 + taxa_mensal
    aliquota_come_cotas = COME_COTAS_ALIQUOTAS[tipo]
    data_resgate = _somar_meses(data_referencia, meses)
    calendario_mercado = carregar_intervalo(
        data_referencia.year,
        data_resgate.year,
        feriados_adicionais=feriados_adicionais,
        anos_confirmados_manualmente=anos_calendario_confirmados,
    )
    feriados = calendario_mercado.feriados
    eventos = _eventos_entre(data_referencia, data_resgate, feriados)
    eventos_pendentes = iter(eventos)
    proximo_evento = next(eventos_pendentes, None)

    lotes, come_cotas_historico = _lotes_existentes_normalizados(
        lotes_existentes,
        capital_atual=capital,
        data_referencia=data_referencia,
    )
    if capital > 0 and not lotes:
        lotes.append(
            _LoteFundo(
                principal=capital,
                saldo=capital,
                base_pos_come_cotas=capital,
                data_aplicacao=data_referencia,
            )
        )

    saldo_bruto = capital
    come_cotas_pago = 0.0
    for numero_mes in range(1, meses + 1):
        data_anterior = _somar_meses(data_referencia, numero_mes - 1)
        data_atual = _somar_meses(data_referencia, numero_mes)

        saldo_bruto *= fator_mensal
        for lote in lotes:
            lote.saldo *= fator_mensal

        while (
            proximo_evento is not None
            and data_anterior < proximo_evento <= data_atual
        ):
            come_cotas_pago += _aplicar_come_cotas(
                lotes,
                aliquota_come_cotas,
            )
            proximo_evento = next(eventos_pendentes, None)

        if aporte > 0:
            saldo_bruto += aporte
            lotes.append(
                _LoteFundo(
                    principal=aporte,
                    saldo=aporte,
                    base_pos_come_cotas=aporte,
                    data_aplicacao=data_atual,
                )
            )

    ir_no_resgate = 0.0
    iof_no_resgate = 0.0
    valor_liquido = 0.0
    for lote in lotes:
        prazo_dias = (data_resgate - lote.data_aplicacao).days
        aliquota_final = _aliquota_final(tipo, prazo_dias)
        ganho_posterior = max(
            0.0,
            lote.saldo - lote.base_pos_come_cotas,
        )
        aliquota_iof = IOF_RENDA_FIXA_DIAS.get(prazo_dias, 0.0)
        iof = ganho_posterior * aliquota_iof
        ir_periodo_final = max(0.0, ganho_posterior - iof) * aliquota_final
        complemento = (
            lote.ganho_antecipado
            * max(0.0, aliquota_final - aliquota_come_cotas)
        )
        imposto_resgate_lote = iof + ir_periodo_final + complemento

        iof_no_resgate += iof
        ir_no_resgate += ir_periodo_final + complemento
        valor_liquido += max(0.0, lote.saldo - imposto_resgate_lote)

    saldo_antes_resgate = sum(lote.saldo for lote in lotes)
    imposto_total = come_cotas_pago + ir_no_resgate + iof_no_resgate
    custo_oportunidade = max(
        0.0,
        saldo_bruto - imposto_total - valor_liquido,
    )
    principal_total = capital + aporte * meses
    anos_projetados = {evento.year for evento in eventos}
    anos_sem_calendario = tuple(
        sorted(anos_projetados - calendario_mercado.anos_confirmados)
    )

    premissas = [
        "Foram simulados apenas eventos futuros de come-cotas.",
        (
            "O capital inicial foi tratado como nova aplicação na data "
            "de referência; nenhum histórico anterior foi reconstruído."
        ),
        "Os aportes mensais foram considerados no fim de cada mês.",
        (
            "Come-cotas no último dia útil de maio e novembro, usando "
            "calendários B3 versionados e feriados adicionais informados."
        ),
        (
            "A rentabilidade foi capitalizada mensalmente e a legislação "
            "da data de referência foi mantida até o resgate."
        ),
    ]
    premissas.extend(calendario_mercado.avisos)

    return ProjecaoComeCotas(
        principal=principal_total,
        bruto_sem_tributos=saldo_bruto,
        saldo_antes_resgate=saldo_antes_resgate,
        come_cotas_pago=come_cotas_pago,
        come_cotas_historico_informado=come_cotas_historico,
        ir_no_resgate=ir_no_resgate,
        iof_no_resgate=iof_no_resgate,
        imposto_total=imposto_total,
        valor_liquido=valor_liquido,
        custo_oportunidade_come_cotas=custo_oportunidade,
        eventos_come_cotas=len(eventos),
        datas_eventos_come_cotas=tuple(
            evento.isoformat() for evento in eventos
        ),
        feriados_considerados=len(feriados),
        anos_sem_calendario_confirmado=anos_sem_calendario,
        quantidade_lotes=len(lotes),
        data_resgate=data_resgate,
        premissas=tuple(premissas),
    )
