# Monta a carteira de alocação (ex: 50% RF, 30% Fundos, 20% RV), 
# aplica ajustes por dependentes, dívidas, liquidez etc. 
# e classifica o perfil final da carteira.

from typing import Dict, List, Optional

from categorias import RK, _risco, _RK_DISPLAY

# ── Normalização de portfólio (soma = 100, sem negativos) ─────────────────────

def _norm(p: dict) -> dict:
    p = {k: max(0, v) for k, v in p.items() if v > 0}
    s = sum(p.values())
    if s <= 0:
        return {RK.RF: 100}
    if s == 100:
        return p
    factor   = 100.0 / s
    adjusted = {k: int(v * factor) for k, v in p.items()}
    diff     = 100 - sum(adjusted.values())
    if diff != 0 and adjusted:
        adjusted[max(adjusted, key=adjusted.get)] += diff
    return {k: v for k, v in adjusted.items() if v > 0}


# ── Mapeamentos auxiliares de portfólio ───────────────────────────────────────

_PORT_DISPLAY: Dict[str, str] = {
    RK.RF:               "Renda Fixa (Tesouro/CDB)",
    RK.RF_SELIC_CDB:     "Tesouro Selic / CDB",
    RK.FUNDOS_RF:        "Fundos de Renda Fixa",
    RK.FUNDOS:           "Fundos de Investimento",
    RK.RV:               "Renda Variável (Ações/ETFs)",
    RK.RV_DCA:           "Renda Variável (com aportes mensais — DCA)",
    RK.RV_CRIPTO:        "Renda Variável / Cripto",
    RK.FUNDOS_ACOES_ETF: "Fundos de Ações / ETFs",
    RK.FUNDOS_ACOES_DCA: "Fundos de Ações (aportes mensais — DCA)",
    RK.FUNDOS_CRIPTO:    "Fundos/ETFs de Cripto",
    RK.FIIS:             "FIIs + Ações de Dividendos",
    RK.FIIS_DEL:         "FIIs / Fundos de Renda Passiva (gestão delegada)",
    RK.PREV_PGBL:        "Previdência (PGBL)",
    RK.PREV_VGBL:        "Previdência (VGBL)",
    RK.RF_LIQUIDEZ:      "Reserva Líquida (Tesouro Selic)",
}

_RV_KEYS_PORT = [
    RK.RV, RK.RV_DCA, RK.RV_CRIPTO,
    RK.FUNDOS_ACOES_ETF, RK.FUNDOS_ACOES_DCA, RK.FUNDOS_CRIPTO, RK.FIIS,
]

_LIQUID_KEYS = {RK.RF_SELIC_CDB, RK.RF_LIQUIDEZ}


def _port_label(rk: str) -> str:
    return _PORT_DISPLAY.get(rk, _RK_DISPLAY.get(rk, rk))


# ── Rebalanceamento RV → RF ───────────────────────────────────────────────────

def mover_rv_para_rf(p: dict, delta: int, avisos: Optional[List[str]] = None) -> bool:
    """
    Move `delta`% de RV para RF.
    Retorna True se moveu algo.
    Se não conseguir mover tudo, registra aviso.
    """
    total_rv = sum(p.get(k, 0) for k in _RV_KEYS_PORT)
    if total_rv <= 0:
        if avisos is not None:
            avisos.append("⚠️  Rebalanceamento RV→RF não aplicado: não havia parcela em renda variável.")
        return False

    moved = 0
    for rv_k in _RV_KEYS_PORT:
        saldo = p.get(rv_k, 0)
        if saldo <= 0:
            continue
        transfer = min(saldo, delta - moved)
        if transfer > 0:
            p[rv_k]  = saldo - transfer
            p[RK.RF] = p.get(RK.RF, 0) + transfer
            moved   += transfer
        if moved >= delta:
            break

    if avisos is not None and moved < delta:
        avisos.append(f"⚠️  Rebalanceamento RV→RF parcial: pedido {delta}%, movido {moved}%.")

    return moved > 0


# ── Construção do portfólio ───────────────────────────────────────────────────

def _build_portfolio(nr, conhec, fv, obj, rd, div, dep, ap, cart, ir_t,
                     flx, pp, lp, desp, id_, avisos) -> dict:

    if nr == 1:
        p = {RK.RF: 80, RK.FUNDOS_RF: 20}
    elif nr == 2:
        p = {RK.RF: 50, RK.FUNDOS: 35, RK.RV: 15}
    else:
        p = {RK.RF: 20, RK.FUNDOS: 30, RK.RV: 40, RK.RV_CRIPTO: 10}

    if conhec == 1:
        rv = p.pop(RK.RV, 0)
        cr = p.pop(RK.RV_CRIPTO, 0)
        if rv + cr > 0:
            p[RK.FUNDOS_ACOES_ETF] = p.get(RK.FUNDOS_ACOES_ETF, 0) + rv + cr

    if fv == 1:
        p = {RK.RF_SELIC_CDB: 100}

    if obj == 3:
        prev_k = RK.PREV_PGBL if ir_t == 1 else RK.PREV_VGBL
        rv_key = RK.FUNDOS_ACOES_ETF if conhec == 1 else RK.RV
        if nr == 1:   p = {prev_k: 60, RK.RF: 40}
        elif nr == 2: p = {prev_k: 50, RK.FUNDOS: 30, rv_key: 20}
        else:         p = {prev_k: 40, RK.FUNDOS: 30, rv_key: 30}

    if flx == 1:
        rv_para_fiis = [
            RK.RV, RK.RV_DCA, RK.RV_CRIPTO,
            RK.FUNDOS_ACOES_ETF, RK.FUNDOS_ACOES_DCA,
            RK.FUNDOS_CRIPTO
        ]
        moved_any = False
        for rv_k in rv_para_fiis:
            if rv_k in p and p[rv_k] > 0:
                p[RK.FIIS] = p.get(RK.FIIS, 0) + p.pop(rv_k)
                moved_any = True

        if not moved_any and p.get(RK.RF, 0) > 0:
            shift      = min(10, p[RK.RF])
            p[RK.RF]  -= shift
            p[RK.FIIS] = p.get(RK.FIIS, 0) + shift

    if ap == 2:
        if p.get(RK.RF, 0) >= 10:
            for rv_k in _RV_KEYS_PORT:
                if rv_k in p:
                    p[RK.RF] -= 10
                    p[rv_k]   = p.get(rv_k, 0) + 10
                    break

    if pp == 3 and not (desp == 1 and dep == 1 and id_ == 1):
        for rv_k in _RV_KEYS_PORT:
            if rv_k in p and p.get(rv_k, 0) >= 20:
                p[rv_k] -= 20
                p[RK.RF] = p.get(RK.RF, 0) + 20
                break

    def _aplicar_liquidez_parcial(pct: int) -> None:
        if pct <= 0:
            return

        nao_liquidos = [k for k in p if k not in _LIQUID_KEYS]
        base_total   = sum(p[k] for k in nao_liquidos)

        if base_total <= 0:
            return

        reducoes = {k: int(p[k] * pct / base_total) for k in nao_liquidos}
        sobra    = pct - sum(reducoes.values())

        for k in sorted(nao_liquidos, key=lambda x: p[x] - reducoes[x], reverse=True):
            if sobra <= 0:
                break
            cap = p[k] - reducoes[k]
            if cap <= 0:
                continue
            add         = min(cap, sobra)
            reducoes[k] += add
            sobra       -= add

        total_removido = 0
        for k, red in reducoes.items():
            antes          = p[k]
            p[k]           = max(0, p[k] - red)
            total_removido += antes - p[k]

        p[RK.RF_LIQUIDEZ] = p.get(RK.RF_LIQUIDEZ, 0) + total_removido

    if lp >= 50:
        return _norm({RK.RF_SELIC_CDB: 100})

    if 0 < lp < 50:
        _aplicar_liquidez_parcial(int(round(lp)))

    if dep == 2:   mover_rv_para_rf(p, 10)
    elif dep == 3: mover_rv_para_rf(p, 20)
    if rd >= 3:    mover_rv_para_rf(p, 10, avisos)
    if div == 2:   mover_rv_para_rf(p, 10)

    if cart == 4:
        p = {RK.RF: 60, RK.FUNDOS: 40}

    return _norm(dict(sorted(p.items(), key=lambda x: -x[1])))


# ── Classificação final do portfólio ─────────────────────────────────────────

def _classificar_portfolio_final(p: Dict[str, int]) -> tuple:
    """
    Classificação contínua baseada no risco médio da carteira.
    """
    score = sum(pct * _risco(k) for k, pct in p.items()) / 100.0

    if score < 1.75:
        risco = 1
    elif score < 2.50:
        risco = 2
    else:
        risco = 3

    if risco == 3:
        if p.get(RK.RV_CRIPTO, 0) > 0 or p.get(RK.FUNDOS_CRIPTO, 0) > 0:
            return RK.RV_CRIPTO, 3
        if p.get(RK.RV, 0) > 0:
            return RK.RV, 3
        return RK.FUNDOS_ACOES_ETF, 3

    if risco == 2:
        if p.get(RK.FUNDOS_MULTI, 0) > 0:
            return RK.FUNDOS_MULTI, 2
        if p.get(RK.FUNDOS_DIVERSIF, 0) > 0:
            return RK.FUNDOS_DIVERSIF, 2
        return RK.FUNDOS, 2

    if p.get(RK.RF_SELIC_CDB, 0) > 0:
        return RK.RF_SELIC_CDB, 1
    if p.get(RK.RF_LIQUIDEZ, 0) > 0:
        return RK.RF_LIQUIDEZ, 1
    if p.get(RK.RF_RESERVA, 0) > 0:
        return RK.RF_RESERVA, 1
    return RK.RF, 1