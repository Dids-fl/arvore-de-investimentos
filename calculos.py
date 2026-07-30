"""Funções puras de matemática financeira usadas nas projeções."""

from __future__ import annotations

import calendar
import math
from collections.abc import Callable, Mapping
from datetime import date
from typing import Any

from tributacao import (
    ContextoTributario,
    PrecisaoTributaria,
    ResultadoTributario,
    calcular_tributacao,
)

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


_ORDEM_PRECISAO = {
    PrecisaoTributaria.EXATA_PARA_PREMISSAS: 0,
    PrecisaoTributaria.ESTIMADA: 1,
    PrecisaoTributaria.INDETERMINADA: 2,
}

_TIPOS_TRIBUTACAO_AGREGADA = {
    "acao",
    "acoes",
    "etf",
    "fii",
    "cripto",
    "bitcoin",
    "ethereum",
}


def _data_valida(nome: str, valor: date) -> date:
    if not isinstance(valor, date):
        raise TypeError(f"{nome} deve ser datetime.date.")
    return valor


def _somar_meses(data_base: date, quantidade: int) -> date:
    """Soma meses preservando o dia quando ele existe no mês de destino."""
    if isinstance(quantidade, bool) or not isinstance(quantidade, int):
        raise TypeError("quantidade deve ser um inteiro.")
    indice = data_base.year * 12 + data_base.month - 1 + quantidade
    ano, mes_zero = divmod(indice, 12)
    mes = mes_zero + 1
    dia = min(data_base.day, calendar.monthrange(ano, mes)[1])
    return date(ano, mes, dia)


def _lotes_projetados(
    cap: float,
    ap: float,
    taxa_m: float,
    meses: int,
    data_referencia: date,
) -> list[tuple[float, float, date]]:
    """
    Gera os lotes coerentes com ``_vf_bruto``.

    O capital inicial é aplicado na data de referência. Cada aporte mensal é
    feito no fim do mês, inclusive o último, que não acumula rendimento.
    """
    lotes: list[tuple[float, float, date]] = []
    if cap > 0:
        lotes.append(
            (
                cap,
                cap * _fator_mensal(taxa_m, meses),
                data_referencia,
            )
        )
    if ap > 0:
        for numero_aporte in range(1, meses + 1):
            meses_aplicado = meses - numero_aporte
            lotes.append(
                (
                    ap,
                    ap * _fator_mensal(taxa_m, meses_aplicado),
                    _somar_meses(data_referencia, numero_aporte),
                )
            )
    return lotes


def _precisao_pior(
    resultados: list[ResultadoTributario],
) -> PrecisaoTributaria:
    return max(
        (resultado.precisao for resultado in resultados),
        key=_ORDEM_PRECISAO.__getitem__,
    )


def _unicos(valores) -> list:
    return list(dict.fromkeys(valores))


def _contexto_tributario(
    *,
    principal: float,
    valor_bruto: float,
    data_aplicacao: date,
    data_resgate: date,
    tipo_produto: str,
    regime: str | None,
    renda_tributavel: float | None,
    valor_vendas_mes: float | None,
    valor_aportes_ano: float | None,
    day_trade: bool,
    pessoa_fisica: bool,
    metadados: Mapping[str, Any],
) -> ContextoTributario:
    return ContextoTributario(
        principal=principal,
        valor_bruto=valor_bruto,
        data_aplicacao=data_aplicacao,
        data_resgate=data_resgate,
        tipo_produto=tipo_produto,
        regime=regime,
        renda_tributavel=renda_tributavel,
        valor_vendas_mes=valor_vendas_mes,
        valor_aportes_ano=valor_aportes_ano,
        day_trade=day_trade,
        pessoa_fisica=pessoa_fisica,
        metadados=dict(metadados),
    )


def _vf_liquido_tributado(
    cap: float,
    ap: float,
    taxa_a: float,
    anos: float,
    tipo_produto: str,
    *,
    data_referencia: date,
    regime: str | None = None,
    renda_tributavel: float | None = None,
    valor_vendas_mes: float | None = None,
    valor_aportes_ano: float | None = None,
    day_trade: bool = False,
    pessoa_fisica: bool = True,
    metadados: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Projeta os fluxos e delega a tributação de cada lote ao motor tributário.

    O retorno é estruturado porque nem todo produto pode ser liquidado com os
    dados disponíveis. Quando qualquer parcela relevante for indeterminada,
    ``imposto_estimado`` e ``liquido`` serão ``None``; nenhum fallback de
    alíquota é aplicado.
    """
    cap, ap, taxa_a, anos = _validar_fluxo(cap, ap, taxa_a, anos)
    data_base = _data_valida("data_referencia", data_referencia)
    if not isinstance(tipo_produto, str) or not tipo_produto.strip():
        raise ValueError("tipo_produto deve ser um texto não vazio.")
    if not isinstance(day_trade, bool):
        raise TypeError("day_trade deve ser booleano.")
    if not isinstance(pessoa_fisica, bool):
        raise TypeError("pessoa_fisica deve ser booleano.")
    if metadados is not None and not isinstance(metadados, Mapping):
        raise TypeError("metadados deve ser um mapeamento ou None.")

    meses = _meses(anos)
    taxa_m = _taxa_mensal(taxa_a)
    data_resgate = _somar_meses(data_base, meses)
    lotes = _lotes_projetados(cap, ap, taxa_m, meses, data_base)
    principal_total = cap + ap * meses
    bruto_total = _vf_bruto(cap, ap, taxa_a, anos)

    if not lotes:
        return {
            "tipo_produto": tipo_produto.strip().casefold(),
            "principal": 0.0,
            "bruto": 0.0,
            "imposto_estimado": 0.0,
            "imposto_calculado_parcial": 0.0,
            "liquido": 0.0,
            "liquido_calculado_parcial": 0.0,
            "bruto_indeterminado": 0.0,
            "precisao": PrecisaoTributaria.EXATA_PARA_PREMISSAS.value,
            "premissas": ["Não há capital nem aportes para tributar."],
            "fontes": [],
            "regras": [],
            "quantidade_lotes": 0,
            "lotes_indeterminados": 0,
            "data_referencia": data_base.isoformat(),
            "data_resgate": data_resgate.isoformat(),
        }

    tipo_normalizado = tipo_produto.strip().casefold()
    dados_extras = dict(metadados or {})
    tributacao_agregada = (
        tipo_normalizado in _TIPOS_TRIBUTACAO_AGREGADA
        or (
            tipo_normalizado in {"pgbl", "vgbl"}
            and str(regime or "").casefold() == "progressivo"
        )
    )

    contextos: list[ContextoTributario] = []
    if tributacao_agregada:
        contextos.append(
            _contexto_tributario(
                principal=principal_total,
                valor_bruto=bruto_total,
                data_aplicacao=min(lote[2] for lote in lotes),
                data_resgate=data_resgate,
                tipo_produto=tipo_normalizado,
                regime=regime,
                renda_tributavel=renda_tributavel,
                valor_vendas_mes=valor_vendas_mes,
                valor_aportes_ano=valor_aportes_ano,
                day_trade=day_trade,
                pessoa_fisica=pessoa_fisica,
                metadados=dados_extras,
            )
        )
    else:
        come_cotas_total = dados_extras.get("come_cotas_pago")
        for principal_lote, bruto_lote, data_aplicacao in lotes:
            metadados_lote = dict(dados_extras)
            if come_cotas_total is not None and bruto_total > 0:
                metadados_lote["come_cotas_pago"] = (
                    float(come_cotas_total) * bruto_lote / bruto_total
                )
            contextos.append(
                _contexto_tributario(
                    principal=principal_lote,
                    valor_bruto=bruto_lote,
                    data_aplicacao=data_aplicacao,
                    data_resgate=data_resgate,
                    tipo_produto=tipo_normalizado,
                    regime=regime,
                    renda_tributavel=renda_tributavel,
                    valor_vendas_mes=valor_vendas_mes,
                    valor_aportes_ano=valor_aportes_ano,
                    day_trade=day_trade,
                    pessoa_fisica=pessoa_fisica,
                    metadados=metadados_lote,
                )
            )

    pares = [
        (contexto, calcular_tributacao(contexto))
        for contexto in contextos
    ]
    resultados = [resultado for _, resultado in pares]
    determinados = [
        (contexto, resultado)
        for contexto, resultado in pares
        if (
            resultado.imposto_estimado is not None
            and resultado.valor_liquido is not None
        )
    ]
    todos_determinados = len(determinados) == len(pares)
    imposto_parcial = sum(
        float(resultado.imposto_estimado)
        for _, resultado in determinados
    )
    liquido_parcial = sum(
        float(resultado.valor_liquido)
        for _, resultado in determinados
    )
    bruto_indeterminado = sum(
        contexto.valor_bruto
        for contexto, resultado in pares
        if resultado.valor_liquido is None
    )
    precisao = _precisao_pior(resultados)
    premissas = _unicos(
        premissa
        for resultado in resultados
        for premissa in resultado.premissas
    )
    if data_resgate.year > data_base.year:
        premissas.append(
            
                "A legislação vigente na data de referência foi mantida "
                "constante até o resgate projetado."
            
        )
        if precisao == PrecisaoTributaria.EXATA_PARA_PREMISSAS:
            precisao = PrecisaoTributaria.ESTIMADA

    fontes = _unicos(
        (
            resultado.fonte,
            resultado.vigencia.isoformat(),
        )
        for resultado in resultados
    )
    return {
        "tipo_produto": tipo_normalizado,
        "principal": principal_total,
        "bruto": bruto_total,
        "imposto_estimado": (
            imposto_parcial if todos_determinados else None
        ),
        "imposto_calculado_parcial": imposto_parcial,
        "liquido": liquido_parcial if todos_determinados else None,
        "liquido_calculado_parcial": liquido_parcial,
        "bruto_indeterminado": bruto_indeterminado,
        "precisao": precisao.value,
        "premissas": premissas,
        "fontes": [
            {"url": fonte, "vigencia": vigencia}
            for fonte, vigencia in fontes
        ],
        "regras": _unicos(
            resultado.regra_id for resultado in resultados
        ),
        "quantidade_lotes": len(lotes),
        "lotes_indeterminados": len(pares) - len(determinados),
        "data_referencia": data_base.isoformat(),
        "data_resgate": data_resgate.isoformat(),
    }


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
