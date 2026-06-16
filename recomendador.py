import sys
from typing import List, Tuple

from categorias import RK, _ARRISCADAS, _risco
from cli import _sep


def _pode_assumir_volatilidade(prazo: int, objetivo: int, emocional: int,
                                reserva_emerg: int, renda: int) -> bool:
    return (
        prazo == 3 and
        objetivo == 2 and
        emocional >= 2 and
        reserva_emerg in (2, 3) and
        renda != 4
    )


def calcular_recomendacao(
    prazo: int,
    risco: int,
    objetivo: int,
    fluxo: int,
    controle: int,
    liquidez: int,
    liquidez_pct: float,
    reserva_emerg: int,
    idade: int,
    despesas: int,
    faixa_valor: int,
    patrim_pct: int,
    renda: int,
    dividas: int,
    conhecimento: int,
    experiencia: List[str],
    dependentes: int,
    aporte: int,
    emocional: int,
    ir_tipo: int,
    carteira_atual: int,
    TAXAS: dict,
) -> Tuple[str, int, int, List[str], int]:
    """
    Aplica todas as regras de negócio e retorna:
        (rec_key, nivel_risco_perfil, meses_res, avisos, conhecimento_ajustado)

    Pode chamar sys.exit(0) se dívidas de juros altos forem detectadas.
    """
    avisos: List[str] = []

    # ── Dívidas ───────────────────────────────────────────────────────────────
    if dividas == 1:
        _sep()
        print("\n🚨 ATENÇÃO — DÍVIDAS DE JUROS ALTOS DETECTADAS")
        _sep()
        print("\n   Você possui dívidas com juros altos (cartão de crédito, cheque especial).")
        print("   Esses juros (>15% a.m.) superam qualquer retorno disponível no mercado.")
        print(f"\n   Melhor retorno estimado: ~{TAXAS[3]*100:.1f}% a.a.")
        print(f"   Juros do cartão:         ~350%+ a.a.")
        print("\n   ✅ Recomendação: Quite suas dívidas PRIMEIRO.")
        print("   Após quitar, volte e refaça este questionário.\n")
        sys.exit(0)
    elif dividas == 2:
        avisos.append("⚠️  Dívidas com juros baixos: possível investir em paralelo, "
                      "mas evite concentrar em ativos de alto risco.")

    # ── Prazo curto com risco alto ────────────────────────────────────────────
    risco_limit_prazo = False
    if prazo == 1 and risco == 3:
        avisos.append("⚠️  Prazo curto (até 2 anos) com risco alto: volatilidade pode "
                      "destruir o capital antes do resgate. Risco ajustado para médio.")
        risco = 2
        risco_limit_prazo = True

    # ── Perfil emocional vs declarado ─────────────────────────────────────────
    risco_emoc = emocional
    if risco_emoc < risco:
        avisos.append(
            f"⚠️  Comportamento em queda ({['conservador','moderado','agressivo'][risco_emoc-1]}) "
            f"mais conservador que o risco declarado ({['baixo','médio','alto'][risco-1]}). "
            "Perfil comportamental prevalece para evitar decisões impulsivas.")
        risco = risco_emoc
    elif risco_emoc > risco:
        avisos.append("ℹ️  Você reagiria mais agressivamente em queda do que declarou. "
                      "Mantemos o risco declarado como base de segurança.")

    # ── Peso do patrimônio ────────────────────────────────────────────────────
    if patrim_pct == 3:
        if idade == 1 and dependentes == 1 and despesas == 1:
            avisos.append("ℹ️  Você investe mais de 75% do seu patrimônio. Como não tem despesas "
                          "fixas nem dependentes, o impacto de uma perda é administrável agora. "
                          "Reavalie conforme sua vida evoluir (aluguel, família).")
        elif idade == 1 and despesas <= 2 and dependentes == 1:
            avisos.append("⚠️  Mais de 75% do patrimônio com despesas baixas. "
                          "Mantenha uma pequena reserva acessível.")
            risco = min(risco, 2)
        else:
            avisos.append("🚨  Mais de 75% do patrimônio com obrigações financeiras. "
                          "Uma perda afetaria diretamente sua vida. Risco reduzido.")
            risco = min(risco, 2)
    elif patrim_pct == 2:
        if despesas == 3 or dependentes > 1:
            avisos.append("⚠️  Entre 25-75% do patrimônio com obrigações financeiras altas. "
                          "Considere manter parte em produto líquido.")
            if risco == 3:
                risco = 2
                avisos.append("ℹ️  Risco ajustado para médio pelo peso do investimento e suas obrigações.")

    # ── Bônus de aporte mensal (DCA) ──────────────────────────────────────────
    aporte_bonus = 0
    if aporte == 2 and prazo >= 2:
        avisos.append("ℹ️  Aportes mensais (DCA): reduz risco de entrada e permite "
                      "exposição levemente maior à renda variável.")
        aporte_bonus = 1

    # ── Ajuste de conhecimento via experiência prática ────────────────────────
    exp_avanc = {"ações", "opções"}
    tem_exp_a = bool(set(experiencia) & exp_avanc)
    nunca_inv = "nenhum" in experiencia

    if nunca_inv and conhecimento >= 2:
        avisos.append("⚠️  Conhecimento declarado intermediário/experiente sem histórico "
                      "de investimentos nos últimos 2 anos. Tratado como iniciante prático.")
        conhecimento = 1
    elif conhecimento == 3 and not tem_exp_a:
        avisos.append("ℹ️  Experiente sem histórico recente em ações/opções. "
                      "Retome com posições menores antes de escalar.")
    elif tem_exp_a and conhecimento == 1:
        conhecimento = 2
        avisos.append("ℹ️  Histórico em ações/opções → perfil ajustado para intermediário.")

    # ── Teto de risco por prazo ───────────────────────────────────────────────
    teto   = {1: 1, 2: 2, 3: 3}
    risco_f = min(risco, teto[prazo])
    if risco_f != risco and not risco_limit_prazo:
        avisos.append(
            f"ℹ️  Prazo {['curto','médio','longo'][prazo-1]} limita o risco máximo. "
            f"Risco ajustado: {['baixo','médio','alto'][risco-1]} → "
            f"{['baixo','médio','alto'][risco_f-1]}.")
    risco = risco_f

    # ── Recomendação base ─────────────────────────────────────────────────────
    if risco == 1:
        rec_key = RK.RF
    elif risco == 2:
        rec_key = RK.RF if prazo == 1 else RK.FUNDOS
    else:
        rec_key = RK.RV if prazo == 2 else RK.RV_CRIPTO

    if aporte_bonus and rec_key == RK.FUNDOS and risco >= 2:
        rec_key = RK.RV_DCA

    nivel_risco_perfil = risco

    # ── Fluxo de renda passiva ────────────────────────────────────────────────
    if fluxo == 1:
        avisos.append("ℹ️  Foco em renda passiva: FIIs, Tesouro IPCA+ com juros semestrais "
                      "e ações com dividendos são indicados.")
        if rec_key == RK.RF and objetivo != 1 and prazo >= 2:
            rec_key = RK.RF_IPCA

    # ── Dependentes ───────────────────────────────────────────────────────────
    meses_res = 3 + (dependentes - 1) * 3

    if dependentes == 2:
        avisos.append(f"ℹ️  1 dependente: mantenha reserva de {meses_res} meses antes de assumir riscos maiores.")
        if rec_key == RK.RV_CRIPTO:
            rec_key = RK.RV

    elif dependentes == 3:
        avisos.append(f"⚠️  2+ dependentes: reserva de {meses_res} meses recomendada. Evite risco alto.")
        if rec_key in {RK.RV_CRIPTO, RK.RV, RK.RV_DCA}:
            rec_key = RK.FUNDOS

    # ── Reserva de emergência ─────────────────────────────────────────────────
    if reserva_emerg == 1:
        if idade == 1 and dependentes == 1 and despesas == 1:
            avisos.append(
                f"ℹ️  Sem reserva de emergência — mas sem obrigações fixas nem dependentes, "
                f"isso não é impeditivo agora. Quando sua vida evoluir (aluguel, família), "
                f"constitua uma reserva de {meses_res} meses em Tesouro Selic.")

        elif idade == 1 and (dependentes > 1 or despesas > 1):
            avisos.append(f"⚠️  Jovem sem reserva com obrigações. "
                          f"Monte {meses_res} meses de reserva em paralelo.")
            if rec_key in {RK.RV_CRIPTO, RK.RV_DCA}:
                rec_key = RK.RV

        elif idade == 2:
            avisos.append(f"⚠️  Adulto sem reserva de emergência (recomendado: {meses_res} meses). "
                          "Reduzindo exposição a risco.")
            if rec_key in {RK.RV_CRIPTO, RK.RV_DCA}:
                rec_key = RK.RV
            elif rec_key == RK.RV:
                rec_key = RK.FUNDOS

        elif idade == 3:
            avisos.append("⚠️  Sênior sem reserva de emergência — priorize isso antes de investir.")
            rec_key = RK.RF_RESERVA

    elif reserva_emerg == 2:
        avisos.append(f"⚠️  Reserva incompleta (recomendado: {meses_res} meses). "
                      "Considere completá-la antes de assumir riscos maiores.")
        if idade != 1 and rec_key in _ARRISCADAS:
            if rec_key == RK.RV_CRIPTO:
                rec_key = RK.RV
            elif rec_key in {RK.RV, RK.RV_DCA}:
                rec_key = RK.FUNDOS

    # ── Tipo de renda ─────────────────────────────────────────────────────────
    if renda == 2:
        avisos.append("ℹ️  PJ contratado: estabilidade similar a CLT, mas sem FGTS. "
                      "Mantenha reserva ligeiramente maior.")
    elif renda == 3:
        avisos.append("ℹ️  Autônomo: mantenha liquidez maior para meses de receita baixa.")
        if rec_key == RK.RV_CRIPTO:
            rec_key = RK.RV
    elif renda == 4:
        if idade == 1 and despesas == 1:
            avisos.append("ℹ️  Sem renda e sem despesas: mantenha uma parcela mínima em liquidez "
                          "para imprevistos pontuais.")
        elif idade == 1:
            avisos.append("⚠️  Sem renda com despesas existentes: liquidez é importante mesmo que não planejada.")
        else:
            avisos.append("⚠️  Sem renda fixa regular: evite ativos de difícil resgate.")
            if rec_key in _ARRISCADAS:
                rec_key = RK.FUNDOS

    # ── Objetivo ──────────────────────────────────────────────────────────────
    if objetivo == 1:
        if rec_key in _ARRISCADAS:
            rec_key = RK.RF_LIQUIDEZ if prazo > 1 else RK.RF

    elif objetivo == 2:
        if rec_key == RK.RF and prazo >= 2 and nivel_risco_perfil >= 2:
            rec_key = RK.FUNDOS
        if rec_key == RK.FUNDOS and prazo == 3:
            rec_key = RK.RV

    elif objetivo == 3:
        if prazo == 1:
            avisos.append("⚠️  Prazo curto com objetivo de aposentadoria. Reavalie seu prazo.")
            rec_key = RK.RF_REAVALIE
        elif prazo == 2:
            if ir_tipo == 1:
                rec_key = RK.PREV_PGBL_RF
                avisos.append("ℹ️  Declaração completa: PGBL deduz até 12% da renda bruta anual. "
                              "Use tabela regressiva.")
            else:
                rec_key = RK.PREV_VGBL_RF
                avisos.append("ℹ️  VGBL é mais adequado — IR incide apenas sobre os ganhos.")
        else:
            if ir_tipo == 1:
                rec_key = RK.PREV_PGBL
                avisos.append("ℹ️  Declaração completa: PGBL deduz até 12% da renda bruta anual. "
                              "Use tabela regressiva para máxima eficiência (10% no resgate).")
            else:
                rec_key = RK.PREV_VGBL
                avisos.append("ℹ️  VGBL é mais adequado — IR incide apenas sobre os ganhos.")

    _PREV_KEYS = {RK.PREV_PGBL, RK.PREV_VGBL, RK.PREV_PGBL_RF, RK.PREV_VGBL_RF}

    # ── Faixa de valor ────────────────────────────────────────────────────────
    if faixa_valor == 1:
        avisos.append("ℹ️  Até R$1.000: Tesouro Selic e CDB com liquidez diária são os mais acessíveis. "
                      "Fundos geralmente exigem aporte mínimo maior.")
        if rec_key not in _PREV_KEYS and _risco(rec_key) >= 2:
            rec_key = RK.RF_SELIC_CDB
    elif faixa_valor == 3:
        avisos.append("ℹ️  Acima de R$10.000: acesso a fundos de qualidade e CDBs de bancos "
                      "menores com taxas melhores que os grandes bancos.")

    # ── Conhecimento ──────────────────────────────────────────────────────────
    if conhecimento == 1:
        avisos.append("ℹ️  Perfil iniciante: evite produtos complexos, mas ETFs e renda fixa podem ser adequados.")
        if rec_key in {RK.RV_CRIPTO, RK.FUNDOS_CRIPTO, RK.COE, RK.ESTRUTURADOS, RK.OFERTAS, RK.CAMBIO}:
            rec_key = (RK.FUNDOS_ACOES_ETF
                       if _pode_assumir_volatilidade(prazo, objetivo, emocional, reserva_emerg, renda)
                       else RK.FUNDOS_RF_LIQ)
    elif conhecimento == 3 and tem_exp_a:
        if nivel_risco_perfil == 3 and prazo == 3:
            avisos.append("ℹ️  Perfil experiente com histórico avançado: considere opções cobertas, "
                          "FIIs e parcela em cripto além da recomendação principal.")

    # ── Liquidez ──────────────────────────────────────────────────────────────
    if liquidez == 1:
        if liquidez_pct >= 50:
            avisos.append(f"⚠️  {liquidez_pct:.0f}% do investimento precisa de liquidez imediata. "
                          "Produto reorientado para alta liquidez.")
            if rec_key not in _PREV_KEYS:
                rec_key = RK.RF_SELIC_CDB
        else:
            avisos.append(f"ℹ️  Mantenha {liquidez_pct:.0f}% em Tesouro Selic ou CDB com liquidez diária "
                          "e invista o restante conforme a recomendação principal.")

    # ── Idade sênior ──────────────────────────────────────────────────────────
    if idade == 3:
        if rec_key == RK.RV_CRIPTO:
            avisos.append("⚠️  Perfil sênior: exposição direta a cripto removida.")
            rec_key = RK.RV
        elif _risco(rec_key) >= 3:
            avisos.append("ℹ️  Sênior com risco alto: certifique-se de ter reserva sólida "
                          "antes de manter grande exposição em renda variável.")

    # ── Carteira atual ────────────────────────────────────────────────────────
    if carteira_atual == 2:
        avisos.append("ℹ️  Carteira conservadora existente: recomendação visa diversificação adicional.")
        if rec_key == RK.RF and prazo >= 2 and nivel_risco_perfil >= 2:
            rec_key = RK.FUNDOS_DIVERSIF
    elif carteira_atual == 3:
        avisos.append("ℹ️  Carteira moderada existente: recomendação como incremento complementar.")
        if rec_key == RK.FUNDOS and nivel_risco_perfil >= 3 and prazo == 3:
            rec_key = RK.RV_COMPL
    elif carteira_atual == 4:
        avisos.append("ℹ️  Carteira arrojada existente: nova entrada reorientada para equilibrar.")
        if nivel_risco_perfil == 3:
            rec_key = RK.RF_EQUILIBRIO

    # ── Preferência por delegação ─────────────────────────────────────────────
    if controle == 2:
        _delegacao: Dict[str, str] = {
            RK.RV_DCA:           RK.FUNDOS_ACOES_DCA,
            RK.RV:               RK.FUNDOS_ACOES,
            RK.RV_CRIPTO:        RK.FUNDOS_CRIPTO,
            RK.RF_SELIC_CDB:     RK.FUNDOS_RF_LIQ,
            RK.RF:               RK.FUNDOS_RF,
            RK.RF_LIQUIDEZ:      RK.FUNDOS_RF,
            RK.RF_IPCA:          RK.FUNDOS_RF,
            RK.FUNDOS:           RK.FUNDOS_MULTI,
            RK.FUNDOS_DIVERSIF:  RK.FUNDOS_MULTI,
            RK.FUNDOS_CRIPTO:    RK.FUNDOS_CRIPTO,
            RK.FIIS:             RK.FIIS_DEL,
            RK.FUNDOS_ACOES_ETF: RK.FUNDOS_ACOES,
        }

        _bloqueados = {
            RK.RF_RESERVA, RK.RF_REAVALIE, RK.RF_EQUILIBRIO,
            RK.COE, RK.ESTRUTURADOS, RK.OFERTAS, RK.CAMBIO
        }

        if rec_key not in _bloqueados and rec_key in _delegacao:
            rec_key = _delegacao[rec_key]

    # ── Produtos avançados (investidor sofisticado) ───────────────────────────
    if conhecimento >= 2 and faixa_valor == 3 and prazo == 3 and liquidez == 2:
        if objetivo == 2 and carteira_atual == 4 and conhecimento >= 3:
            rec_key = RK.OFERTAS
        elif objetivo == 2 and carteira_atual == 4 and conhecimento >= 2:
            rec_key = RK.ESTRUTURADOS
        elif objetivo in (2, 3) and nivel_risco_perfil >= 2 and controle == 2:
            rec_key = RK.COE
        elif objetivo == 2 and carteira_atual in (3, 4) and renda != 4:
            rec_key = RK.CAMBIO

    return rec_key, nivel_risco_perfil, meses_res, avisos, conhecimento


# Tipagem auxiliar para o mypy
from typing import Dict  # noqa: E402 (já importado no topo, re-referenciado aqui apenas para anotação)