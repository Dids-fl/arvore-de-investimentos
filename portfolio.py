"""Construção e classificação da carteira sugerida."""

from __future__ import annotations

import math
from collections.abc import MutableMapping
from typing import Optional

from core.categorias import _RK_DISPLAY, RK, _risco

Portfolio = dict[str, int | float]

_PORT_DISPLAY: dict[str, str] = {
    RK.RF: "Renda Fixa (Tesouro/CDB)",
    RK.RF_SELIC_CDB: "Tesouro Selic / CDB",
    RK.RF_LIQUIDEZ: "Reserva Líquida (Tesouro Selic)",
    RK.RF_IPCA: "Renda Fixa indexada ao IPCA",
    RK.FUNDOS_RF: "Fundos de Renda Fixa",
    RK.FUNDOS_RF_LIQ: "Fundos de Renda Fixa com liquidez",
    RK.FUNDOS: "Fundos de Investimento",
    RK.FUNDOS_MULTI: "Fundos Multimercado",
    RK.RV: "Renda Variável (Ações/ETFs)",
    RK.RV_DCA: "Renda Variável (aportes mensais)",
    RK.RV_CRIPTO: "Renda Variável / Cripto",
    RK.FUNDOS_ACOES_ETF: "Fundos de Ações / ETFs",
    RK.FUNDOS_ACOES_DCA: "Fundos de Ações (aportes mensais)",
    RK.FUNDOS_CRIPTO: "Fundos/ETFs de Cripto",
    RK.FIIS: "FIIs + ativos de renda",
    RK.FIIS_DEL: "FIIs / Renda Passiva com gestão delegada",
    RK.PREV_PGBL: "Previdência (PGBL)",
    RK.PREV_VGBL: "Previdência (VGBL)",
    RK.PREV_PGBL_RF: "Previdência conservadora (PGBL)",
    RK.PREV_VGBL_RF: "Previdência conservadora (VGBL)",
}

_RV_KEYS_PORT = (
    RK.RV,
    RK.RV_DCA,
    RK.RV_CRIPTO,
    RK.RV_COMPL,
    RK.FUNDOS_ACOES,
    RK.FUNDOS_ACOES_ETF,
    RK.FUNDOS_ACOES_DCA,
    RK.FUNDOS_CRIPTO,
)
_LIQUID_KEYS = {
    RK.RF_SELIC_CDB,
    RK.RF_LIQUIDEZ,
    RK.FUNDOS_RF_LIQ,
}


def _aviso(avisos: list[str] | None, mensagem: str) -> None:
    if avisos is not None and mensagem not in avisos:
        avisos.append(mensagem)


def _valor_valido(chave: str, valor: object) -> float:
    if isinstance(valor, bool):
        raise TypeError(f"A alocação de {chave!r} não pode ser booleana.")
    try:
        numero = float(valor)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"A alocação de {chave!r} deve ser numérica.") from exc
    if not math.isfinite(numero):
        raise ValueError(f"A alocação de {chave!r} deve ser finita.")
    return numero


def _norm(p: MutableMapping[str, int | float]) -> dict[str, int]:
    """
    Normaliza percentuais com o método das maiores sobras.

    O resultado contém apenas posições positivas, em inteiros, e soma
    exatamente 100. O método evita concentrar todo o erro de arredondamento
    na maior posição.
    """
    positivos: list[tuple[str, float, int]] = []
    for ordem, (chave, valor) in enumerate(p.items()):
        numero = _valor_valido(chave, valor)
        if numero < 0:
            raise ValueError(f"A alocação de {chave!r} não pode ser negativa.")
        if numero > 0:
            positivos.append((chave, numero, ordem))

    total = sum(valor for _, valor, _ in positivos)
    if total <= 0:
        return {RK.RF: 100}

    cotas = [
        (chave, valor * 100.0 / total, ordem)
        for chave, valor, ordem in positivos
    ]
    inteiros = {
        chave: math.floor(cota)
        for chave, cota, _ in cotas
    }
    faltantes = 100 - sum(inteiros.values())
    prioridade = sorted(
        cotas,
        key=lambda item: (-(item[1] - math.floor(item[1])), item[2]),
    )
    for chave, _, _ in prioridade[:faltantes]:
        inteiros[chave] += 1

    return {
        chave: percentual
        for chave, percentual in inteiros.items()
        if percentual > 0
    }


def _port_label(rk: str) -> str:
    return _PORT_DISPLAY.get(rk, _RK_DISPLAY.get(rk, rk))


def _retirar_proporcional(
    p: Portfolio,
    chaves: list[str],
    valor: float,
) -> float:
    """Retira até ``valor`` das chaves informadas, proporcionalmente."""
    elegiveis = [
        chave
        for chave in chaves
        if float(p.get(chave, 0)) > 0
    ]
    total = sum(float(p[chave]) for chave in elegiveis)
    retirar = min(max(0.0, float(valor)), total)
    if retirar <= 0 or total <= 0:
        return 0.0

    restante = retirar
    for indice, chave in enumerate(elegiveis):
        saldo = float(p[chave])
        if indice == len(elegiveis) - 1:
            parcela = min(saldo, restante)
        else:
            parcela = min(saldo, retirar * saldo / total)
        p[chave] = saldo - parcela
        restante -= parcela

    return retirar - max(0.0, restante)


def mover_rv_para_rf(
    p: Portfolio,
    delta: int | float,
    avisos: list[str] | None = None,
) -> bool:
    """Move até ``delta`` pontos percentuais de renda variável para RF."""
    delta = _valor_valido("delta", delta)
    if delta < 0:
        raise ValueError("delta não pode ser negativo.")

    movido = _retirar_proporcional(p, list(_RV_KEYS_PORT), delta)
    if movido > 0:
        p[RK.RF] = float(p.get(RK.RF, 0)) + movido

    if movido <= 0:
        _aviso(
            avisos,
            "⚠️ Rebalanceamento RV→RF não aplicado: não havia renda variável.",
        )
        return False
    if movido + 1e-9 < delta:
        _aviso(
            avisos,
            (
                "⚠️ Rebalanceamento RV→RF foi parcial: "
                f"pedido {delta:g}%, movido {movido:g}%."
            ),
        )
    return True


def _validar_opcao(nome: str, valor: object, minimo: int, maximo: int) -> int:
    if isinstance(valor, bool):
        raise TypeError(f"{nome} deve ser um inteiro.")
    try:
        inteiro = int(valor)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{nome} deve ser um inteiro.") from exc
    if inteiro != valor or not minimo <= inteiro <= maximo:
        raise ValueError(f"{nome} deve estar entre {minimo} e {maximo}.")
    return inteiro


def _base_portfolio(nivel_risco: int) -> Portfolio:
    if nivel_risco == 1:
        return {RK.RF: 80, RK.FUNDOS_RF: 20}
    if nivel_risco == 2:
        return {RK.RF: 50, RK.FUNDOS: 35, RK.RV: 15}
    return {RK.RF: 20, RK.FUNDOS: 30, RK.RV: 40, RK.RV_CRIPTO: 10}


def _adequar_ao_conhecimento(p: Portfolio, conhecimento: int) -> None:
    if conhecimento != 1:
        return
    direto = sum(float(p.pop(chave, 0)) for chave in (RK.RV, RK.RV_CRIPTO))
    if direto > 0:
        p[RK.FUNDOS_ACOES_ETF] = (
            float(p.get(RK.FUNDOS_ACOES_ETF, 0)) + direto
        )


def _portfolio_aposentadoria(
    nivel_risco: int,
    conhecimento: int,
    ir_tipo: int,
) -> Portfolio:
    if nivel_risco == 1:
        previdencia = (
            RK.PREV_PGBL_RF
            if ir_tipo == 1
            else RK.PREV_VGBL_RF
        )
        return {previdencia: 60, RK.RF: 40}

    previdencia = RK.PREV_PGBL if ir_tipo == 1 else RK.PREV_VGBL
    renda_variavel = (
        RK.FUNDOS_ACOES_ETF
        if conhecimento == 1
        else RK.RV
    )
    if nivel_risco == 2:
        return {previdencia: 50, RK.FUNDOS: 30, renda_variavel: 20}
    return {previdencia: 40, RK.FUNDOS: 30, renda_variavel: 30}


def _aplicar_renda_periodica(
    p: Portfolio,
    nivel_risco: int,
    avisos: list[str] | None,
) -> None:
    if nivel_risco == 1:
        deslocado = min(10.0, float(p.get(RK.RF, 0)))
        if deslocado:
            p[RK.RF] = float(p.get(RK.RF, 0)) - deslocado
            p[RK.RF_IPCA] = float(p.get(RK.RF_IPCA, 0)) + deslocado
        _aviso(
            avisos,
            "ℹ️ Fluxo periódico conservador não garante renda constante.",
        )
        return

    movido = _retirar_proporcional(p, list(_RV_KEYS_PORT), 15)
    if movido <= 0:
        movido = _retirar_proporcional(p, [RK.FUNDOS, RK.RF], 10)
    if movido > 0:
        p[RK.FIIS] = float(p.get(RK.FIIS, 0)) + movido


def _aplicar_aportes_mensais(p: Portfolio, aporte: int) -> None:
    if aporte != 2:
        return
    substituicoes = {
        RK.RV: RK.RV_DCA,
        RK.FUNDOS_ACOES_ETF: RK.FUNDOS_ACOES_DCA,
    }
    for origem, destino in substituicoes.items():
        valor = float(p.pop(origem, 0))
        if valor > 0:
            p[destino] = float(p.get(destino, 0)) + valor


def _garantir_liquidez(
    p: Portfolio,
    alvo_percentual: float,
    avisos: list[str] | None,
) -> None:
    # O portfólio final usa percentuais inteiros; arredondar para cima evita
    # entregar menos liquidez do que o usuário declarou precisar.
    alvo = min(100.0, math.ceil(max(0.0, alvo_percentual)))
    atual = sum(float(p.get(chave, 0)) for chave in _LIQUID_KEYS)
    necessario = max(0.0, alvo - atual)
    if necessario <= 0:
        return

    nao_liquidos = [
        chave
        for chave in p
        if chave not in _LIQUID_KEYS
    ]
    removido = _retirar_proporcional(p, nao_liquidos, necessario)
    p[RK.RF_LIQUIDEZ] = float(p.get(RK.RF_LIQUIDEZ, 0)) + removido
    if removido + 1e-9 < necessario:
        _aviso(
            avisos,
            "⚠️ Não foi possível atingir toda a liquidez solicitada.",
        )


def _build_portfolio(
    nr,
    conhec,
    fv,
    obj,
    rd,
    div,
    dep,
    ap,
    cart,
    ir_t,
    flx,
    pp,
    lp,
    desp,
    id_,
    avisos,
) -> dict[str, int]:
    """Monta a alocação final, aplicando risco, objetivo e proteções."""
    nr = _validar_opcao("nr", nr, 1, 3)
    conhec = _validar_opcao("conhec", conhec, 1, 3)
    fv = _validar_opcao("fv", fv, 1, 3)
    obj = _validar_opcao("obj", obj, 1, 3)
    rd = _validar_opcao("rd", rd, 1, 4)
    div = _validar_opcao("div", div, 1, 3)
    dep = _validar_opcao("dep", dep, 1, 3)
    ap = _validar_opcao("ap", ap, 1, 2)
    cart = _validar_opcao("cart", cart, 1, 4)
    ir_t = _validar_opcao("ir_t", ir_t, 1, 3)
    flx = _validar_opcao("flx", flx, 1, 2)
    pp = _validar_opcao("pp", pp, 1, 3)
    desp = _validar_opcao("desp", desp, 1, 3)
    id_ = _validar_opcao("id_", id_, 1, 3)
    lp = _valor_valido("lp", lp)
    if not 0 <= lp <= 100:
        raise ValueError("lp deve estar entre 0 e 100.")
    if avisos is not None and not isinstance(avisos, list):
        raise TypeError("avisos deve ser uma lista ou None.")

    if div == 1:
        _aviso(
            avisos,
            "🚨 Dívidas caras devem ser priorizadas antes dos investimentos.",
        )
        return {RK.RF_SELIC_CDB: 100}

    p = _base_portfolio(nr)
    _adequar_ao_conhecimento(p, conhec)

    if obj == 3:
        p = _portfolio_aposentadoria(nr, conhec, ir_t)
    elif fv == 1:
        p = {RK.RF_SELIC_CDB: 100}

    _aplicar_aportes_mensais(p, ap)

    if flx == 1 and obj != 1:
        _aplicar_renda_periodica(p, nr, avisos)

    if cart == 4:
        tem_estrutura = (
            rd in {1, 2}
            and dep < 3
            and conhec >= 2
            and desp <= 2
            and id_ != 3
        )
        if tem_estrutura:
            _aviso(
                avisos,
                (
                    "ℹ️ A carteira arrojada existente foi mantida; "
                    "revise o rebalanceamento periodicamente."
                ),
            )
        else:
            mover_rv_para_rf(p, 20, avisos)
            _aviso(
                avisos,
                "ℹ️ O risco foi reduzido por limitações financeiras atuais.",
            )

    if pp == 3 and not (desp == 1 and dep == 1 and id_ == 1):
        mover_rv_para_rf(p, 20, avisos)
    if dep == 2:
        mover_rv_para_rf(p, 10, avisos)
    elif dep == 3:
        mover_rv_para_rf(p, 20, avisos)
    if rd == 3:
        mover_rv_para_rf(p, 10, avisos)
    elif rd == 4:
        mover_rv_para_rf(p, 30, avisos)
    if div == 2:
        mover_rv_para_rf(p, 10, avisos)
    if desp == 3:
        mover_rv_para_rf(p, 10, avisos)
    if id_ == 3:
        mover_rv_para_rf(p, 15, avisos)

    _garantir_liquidez(p, lp, avisos)
    normalizado = _norm(p)
    return dict(sorted(normalizado.items(), key=lambda item: -item[1]))


def _classificar_portfolio_final(
    p: dict[str, int | float],
) -> tuple[str, int]:
    """Classifica pelo risco ponderado e escolhe um ativo presente na carteira."""
    positivos: dict[str, float] = {}
    for chave, valor in p.items():
        numero = _valor_valido(chave, valor)
        if numero < 0:
            raise ValueError(f"A alocação de {chave!r} não pode ser negativa.")
        if numero > 0:
            positivos[chave] = numero
    total = sum(positivos.values())
    if total <= 0:
        return RK.RF, 1

    score = sum(
        percentual * _risco(chave)
        for chave, percentual in positivos.items()
    ) / total
    if score < 1.30:
        risco = 1
    elif score < 2.20:
        risco = 2
    else:
        risco = 3

    mesmo_risco = [
        (chave, percentual)
        for chave, percentual in positivos.items()
        if _risco(chave) == risco
    ]
    candidatos = mesmo_risco or list(positivos.items())
    representante = max(
        candidatos,
        key=lambda item: (
            -abs(_risco(item[0]) - risco),
            item[1],
        ),
    )[0]
    return representante, risco