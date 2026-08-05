"""Funções puras de matemática financeira usadas nas projeções."""

from __future__ import annotations

import calendar
import math
from collections.abc import Callable, Mapping
from datetime import date
from typing import Any

from tributacao import (
    FUNDOS_COM_COME_COTAS,
    ContextoTributario,
    PrecisaoTributaria,
    ResultadoTributario,
    calcular_tributacao,
    projetar_come_cotas,
)
from tributacao.regras import (
    FONTE_B3_CALENDARIO_2026,
    FONTE_RECEITA_FUNDOS,
    VIGENCIA_BASE,
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
    return round(anos * 12.0)


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


def _data_iso(nome: str, valor: object) -> date:
    if isinstance(valor, date):
        return valor
    if isinstance(valor, str):
        try:
            return date.fromisoformat(valor)
        except ValueError as exc:
            raise ValueError(f"{nome} deve estar no formato AAAA-MM-DD.") from exc
    raise TypeError(f"{nome} deve ser datetime.date ou texto ISO.")


def _lotes_previdencia_importados(
    lotes_brutos: object,
    *,
    capital_atual: float,
    taxa_mensal: float,
    meses: int,
    data_referencia: date,
) -> list[tuple[float, float, date]]:
    if lotes_brutos is None:
        return []
    if isinstance(lotes_brutos, (str, bytes)):
        raise TypeError("lotes_previdencia_existentes deve ser uma lista.")
    try:
        itens = list(lotes_brutos)
    except TypeError as exc:
        raise TypeError(
            "lotes_previdencia_existentes deve ser uma lista."
        ) from exc
    if not itens:
        return []

    lotes: list[tuple[float, float, date]] = []
    saldo_total = 0.0
    for indice, item in enumerate(itens):
        if not isinstance(item, Mapping):
            raise TypeError(
                "Cada lote previdenciário existente deve ser um mapeamento."
            )
        principal = _numero_finito(
            f"lote[{indice}].principal",
            item.get("principal"),
        )
        saldo_atual = _numero_finito(
            f"lote[{indice}].saldo_atual",
            item.get("saldo_atual"),
        )
        if principal < 0 or saldo_atual < 0:
            raise ValueError("Principal e saldo do lote não podem ser negativos.")
        data_aplicacao = _data_iso(
            f"lote[{indice}].data_aplicacao",
            item.get("data_aplicacao"),
        )
        if data_aplicacao > data_referencia:
            raise ValueError(
                "Lote previdenciário existente não pode começar no futuro."
            )
        saldo_total += saldo_atual
        lotes.append(
            (
                principal,
                saldo_atual * _fator_mensal(taxa_mensal, meses),
                data_aplicacao,
            )
        )

    tolerancia = max(0.01, capital_atual * 1e-6)
    if abs(saldo_total - capital_atual) > tolerancia:
        raise ValueError(
            "A soma de saldo_atual dos lotes previdenciários deve ser igual "
            "ao capital inicial destinado à previdência."
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
    tipo_normalizado = tipo_produto.strip().casefold()
    dados_extras = dict(metadados or {})
    lotes_importados = []
    if tipo_normalizado in {"pgbl", "vgbl"}:
        lotes_importados = _lotes_previdencia_importados(
            dados_extras.pop("lotes_previdencia_existentes", None),
            capital_atual=cap,
            taxa_mensal=taxa_m,
            meses=meses,
            data_referencia=data_base,
        )
    if lotes_importados:
        lotes_novos = _lotes_projetados(0.0, ap, taxa_m, meses, data_base)
        lotes = [*lotes_importados, *lotes_novos]
        principal_total = sum(lote[0] for lote in lotes)
        bruto_total = sum(lote[1] for lote in lotes)
    else:
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

    simular_come_cotas = dados_extras.pop(
        "simular_come_cotas_futuro",
        True,
    )
    if not isinstance(simular_come_cotas, bool):
        raise TypeError("simular_come_cotas_futuro deve ser booleano.")
    if (
        tipo_normalizado in FUNDOS_COM_COME_COTAS
        and simular_come_cotas
        and (
            "come_cotas_pago" not in dados_extras
            or "lotes_fundo_existentes" in dados_extras
        )
    ):
        lotes_fundo_existentes = dados_extras.pop(
            "lotes_fundo_existentes",
            None,
        )
        if (
            lotes_fundo_existentes is not None
            and "come_cotas_pago" in dados_extras
        ):
            raise ValueError(
                "Com lotes_fundo_existentes, informe o histórico em cada "
                "lote por come_cotas_pago_historico."
            )
        feriados_adicionais = dados_extras.pop(
            "feriados_mercado",
            None,
        )
        anos_calendario_confirmados = dados_extras.pop(
            "anos_calendario_mercado_confirmados",
            None,
        )
        projecao = projetar_come_cotas(
            cap,
            ap,
            taxa_a,
            meses,
            data_referencia=data_base,
            tipo_produto=tipo_normalizado,
            lotes_existentes=lotes_fundo_existentes,
            feriados_adicionais=feriados_adicionais,
            anos_calendario_confirmados=anos_calendario_confirmados,
        )
        return {
            "tipo_produto": tipo_normalizado,
            "principal": projecao.principal,
            "bruto": projecao.bruto_sem_tributos,
            "imposto_estimado": projecao.imposto_total,
            "imposto_calculado_parcial": projecao.imposto_total,
            "liquido": projecao.valor_liquido,
            "liquido_calculado_parcial": projecao.valor_liquido,
            "bruto_indeterminado": 0.0,
            "precisao": PrecisaoTributaria.ESTIMADA.value,
            "premissas": list(projecao.premissas),
            "fontes": [
                {
                    "url": FONTE_RECEITA_FUNDOS,
                    "vigencia": VIGENCIA_BASE.isoformat(),
                },
                {
                    "url": FONTE_B3_CALENDARIO_2026,
                    "vigencia": "2026-01-09",
                },
            ],
            "regras": [f"{tipo_normalizado}_come_cotas_prospectivo_2026"],
            "quantidade_lotes": projecao.quantidade_lotes,
            "lotes_indeterminados": 0,
            "data_referencia": data_base.isoformat(),
            "data_resgate": projecao.data_resgate.isoformat(),
            "metodo_tributacao": "come_cotas_prospectivo_por_lote",
            "eventos_come_cotas": projecao.eventos_come_cotas,
            "datas_eventos_come_cotas": list(
                projecao.datas_eventos_come_cotas
            ),
            "come_cotas_estimado": projecao.come_cotas_pago,
            "come_cotas_historico_informado": (
                projecao.come_cotas_historico_informado
            ),
            "ir_no_resgate": projecao.ir_no_resgate,
            "iof_no_resgate": projecao.iof_no_resgate,
            "saldo_apos_come_cotas": projecao.saldo_antes_resgate,
            "custo_oportunidade_come_cotas": (
                projecao.custo_oportunidade_come_cotas
            ),
            "feriados_considerados": projecao.feriados_considerados,
            "anos_sem_calendario_confirmado": list(
                projecao.anos_sem_calendario_confirmado
            ),
        }
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
            if (
                tipo_normalizado in {"pgbl", "vgbl"}
                and str(regime or "").casefold() == "regressivo"
            ):
                metadados_lote["lote_individual_projetado"] = True
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
        "quantidade_lotes_importados": len(lotes_importados),
        "capital_atual_inicio": cap,
        "lotes_indeterminados": len(pares) - len(determinados),
        "data_referencia": data_base.isoformat(),
        "data_resgate": data_resgate.isoformat(),
        "metodo_tributacao": (
            "agregado" if tributacao_agregada else "lotes_individuais"
        ),
        "aliquotas_efetivas": _unicos(
            resultado.aliquota_efetiva
            for resultado in resultados
            if resultado.aliquota_efetiva is not None
        ),
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
