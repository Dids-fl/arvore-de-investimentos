import json
import datetime
from typing import Optional, List

from config import IR_RF
from categorias import _risco
from catalogo import _get_prod, _disp, _aliq
from mercado import load_market_data
from calculos import _vf_bruto, _vf_liquido, _vf_real
from cli import (
    _sep, _p, _p_primeira, _n, _m,
    _PD, _RD, _OD, _FD, _CD, _LD, _RSD, _ID, _DD, _VD, _PPD,
    _RND, _DVd, _KD, _DPD, _APD, _EMD, _IRD, _CAD, _MTD,
    DEMO_PADRAO,
)
from portfolio import _build_portfolio, _classificar_portfolio_final
from recomendador import calcular_recomendacao


def main() -> None:
    # ── Carrega taxas de mercado ───────────────────────────────────────────────
    market = load_market_data()

    selic       = market["selic"]
    focus_selic = market["focus_selic"]
    ipca        = market["ipca"]
    ibov_cagr   = market["ibov_cagr"]
    _data_ref   = market["data_ref"]
    _fontes     = market["fontes"]
    _avisos_api = market["avisos"]

    _taxa_base = (selic + focus_selic) / 2 if focus_selic else selic

    TAXAS = {1: selic, 2: (selic + ibov_cagr) / 2, 3: ibov_cagr}

    def _label_taxa(nivel: int) -> str:
        t = TAXAS[nivel]
        d = {
            1: f"SELIC atual {selic*100:.2f}% a.a.",
            2: f"Média entre SELIC ({selic*100:.2f}%) e Ibovespa CAGR 10a ({ibov_cagr*100:.2f}%)",
            3: f"Ibovespa CAGR histórico 10 anos ({ibov_cagr*100:.2f}% a.a.)",
        }
        return f"~{t*100:.2f}% a.a. bruto  [{d[nivel]}]"

    # ── Cabeçalho ─────────────────────────────────────────────────────────────
    print("\n" + "═" * 58)
    print("   📊 RECOMENDADOR DE INVESTIMENTOS")
    print("   Análise completa de perfil — versão corrigida")
    print("═" * 58)

    if _avisos_api:
        print("\n   ⚠️  Algumas taxas usam fallback (APIs indisponíveis):")
        for a in _avisos_api:
            print(f"      {a}")
    else:
        print(f"\n   ✅ Taxas em tempo real obtidas com sucesso ({_data_ref})")

    print("\n   Dados utilizados:")
    for f in _fontes:
        print(f"      • {f}")
    if focus_selic:
        print(f"\n   Taxa base = média SELIC atual e previsão Focus:")
        print(f"      ({selic*100:.2f}% + {focus_selic*100:.2f}%) ÷ 2 = {_taxa_base*100:.2f}% a.a.")

    print("\n   Taxas por perfil de risco (aproximação conservadora — IR sobre taxa bruta):")
    for nivel, label in [(1, "Baixo"), (2, "Médio"), (3, "Alto")]:
        t    = TAXAS[nivel]
        liq  = t * (1 - IR_RF)
        real = (1 + liq) / (1 + ipca) - 1
        print(f"      {label:<6}: {t*100:.2f}% bruto | {liq*100:.2f}% líq. aprox. | {real*100:.2f}% real")
    print(f"      IPCA projetado: {ipca*100:.2f}% a.a.  |  Projeção detalhada usa IR no resgate.")
    print("\nResponda as perguntas para receber sua recomendação.")

    _sep()

    # ── Questionário ──────────────────────────────────────────────────────────
    primeira = _p_primeira(
        "1. Qual é o seu prazo de investimento?\n"
        "   (curto = até 2 anos | médio = 2 a 5 anos | longo = acima de 5 anos)",
        _PD,
    )
    MODO_DEMO = primeira == "__DEMO__"

    meta_valor:    Optional[float] = None
    meta_prazo:    Optional[float] = None
    cap_inicial:   float           = 0.0
    aporte_mensal: float           = 0.0

    if MODO_DEMO:
        d              = DEMO_PADRAO
        prazo          = d["prazo"]
        risco          = d["risco"]
        objetivo       = d["objetivo"]
        fluxo          = d["fluxo"]
        controle       = d["controle"]
        liquidez       = d["liquidez"]
        liquidez_pct   = d["liquidez_pct"]
        reserva_emerg  = d["reserva_emerg"]
        idade          = d["idade"]
        despesas       = d["despesas"]
        faixa_valor    = d["faixa_valor"]
        patrim_pct     = d["patrim_pct"]
        renda          = d["renda"]
        dividas        = d["dividas"]
        conhecimento   = d["conhecimento"]
        experiencia    = d["experiencia"]
        dependentes    = d["dependentes"]
        aporte         = d["aporte"]
        emocional      = d["emocional"]
        ir_tipo        = d["ir_tipo"]
        carteira_atual = d["carteira_atual"]
        cap_inicial    = d["cap_inicial"]
        aporte_mensal  = d["aporte_mensal"]

    else:
        prazo = primeira
        risco = _p(
            "2. Qual é o seu nível de tolerância a risco?\n"
            "   (baixo | médio | alto)",
            _RD,
        )
        objetivo = _p(
            "3. Qual é o seu principal objetivo?\n"
            "   (reserva | crescimento | aposentadoria)",
            _OD,
        )
        fluxo = _p(
            "4. Durante o investimento, você prefere:\n"
            "   (renda = receber dividendos/juros periodicamente\n"
            "    acúmulo = acumular tudo e resgatar no final)",
            _FD,
        )
        controle = _p(
            "5. Prefere gerir os investimentos você mesmo ou delegar a um gestor?\n"
            "   (gerir | delegar)",
            _CD,
        )
        liquidez = _p(
            "6. Você precisa ter acesso rápido ao dinheiro investido?\n"
            "   (sim | não)",
            _LD,
        )
        liquidez_pct = 0.0
        if liquidez == 1:
            liquidez_pct = _n(
                "   6a. Em uma emergência, qual % estima precisar resgatar?\n"
                "       (ex: 30 = precisaria de 30% do valor investido)",
                mn=1, mx=100,
            )

        reserva_emerg = _p(
            "7. Você já tem reserva de emergência (3-6 meses de gastos)?\n"
            "   (não tenho | parcial | sim)",
            _RSD,
        )
        idade = _p(
            "8. Qual é a sua faixa de idade?\n"
            "   (jovem = até 35 | adulto = 36 a 55 | sênior = acima de 55)",
            _ID,
        )
        despesas = _p(
            "9. Como são suas obrigações financeiras mensais fixas?\n"
            "   (nenhuma = sem aluguel/dependentes/contas relevantes\n"
            "    baixas   = algumas contas, não comprometem muito\n"
            "    altas    = aluguel, dependentes ou financiamentos pesados)",
            _DD,
        )
        faixa_valor = _p(
            "10. Quanto você tem disponível para investir agora?\n"
            "    (baixo = até R$1.000 | médio = R$1k-10k | alto = acima de R$10.000)",
            _VD,
        )
        patrim_pct = _p(
            "11. Este valor representa qual parcela do seu patrimônio total?\n"
            "    (baixo = menos de 25% | médio = 25%-75% | alto = mais de 75%)",
            _PPD,
        )
        renda = _p(
            "12. Qual é a sua situação de renda?\n"
            "    (clt = emprego formal\n"
            "     pj contratado = PJ fixo em empresa (comporta como CLT)\n"
            "     autônomo = freelancer/PJ variável\n"
            "     sem renda = estudante/sem emprego)",
            _RND,
        )
        dividas = _p(
            "13. Você possui dívidas ativas?\n"
            "    (juros altos = cartão/cheque especial\n"
            "     juros baixos = financiamento/consignado\n"
            "     não tenho)",
            _DVd,
        )
        conhecimento = _p(
            "14. Qual é o seu nível de conhecimento sobre investimentos?\n"
            "    (iniciante | intermediário | experiente)",
            _KD,
        )
        experiencia = _m(
            "15. Quais produtos você já investiu nos últimos 2 anos?\n"
            "    (poupança | tesouro | ações | fundos | opções | nenhum)\n"
            "    Separe por vírgula se houver mais de um."
        )
        dependentes = _p(
            "16. Quantas pessoas dependem financeiramente de você?\n"
            "    (nenhum | um | dois ou mais)",
            _DPD,
        )
        aporte = _p(
            "17. Você pretende fazer aportes mensais ou investimento único?\n"
            "    (único | mensal)",
            _APD,
        )
        emocional = _p(
            "18. Se sua carteira caísse 30% em 6 meses, o que você faria?\n"
            "    (venderia tudo | esperaria recuperar | compraria mais)",
            _EMD,
        )
        ir_tipo = _p(
            "19. Como você declara o Imposto de Renda?\n"
            "    (completo | simplificado | não declaro)",
            _IRD,
        )
        carteira_atual = _p(
            "20. Você já possui alguma carteira de investimentos?\n"
            "    (não tenho | conservadora | moderada | arrojada)",
            _CAD,
        )

        modo_meta = _p(
            "21. Você tem uma meta financeira?\n"
            "    (sim      = quero saber se consigo atingir um valor específico\n"
            "     rendendo = quero ver como meu dinheiro cresce ao longo do tempo\n"
            "     não      = pular esta etapa)",
            _MTD,
        )

        if modo_meta == 1:
            meta_valor  = _n("    Qual valor quer acumular? (R$, ex: 500000)", mn=1)
            meta_prazo  = _n("    Em quantos anos? (ex: 10)", mn=1, mx=50)
            cap_inicial = _n("    Capital inicial disponível? (R$, ex: 10000)", mn=0)
            if aporte == 2:
                ap_raw        = _n("    Aporte mensal? (R$, ex: 500 — ou 0 se não houver)", mn=0)
                aporte_mensal = ap_raw if ap_raw is not None else 0.0
        elif modo_meta == 2:
            cap_inicial = _n("    Capital inicial disponível? (R$, ex: 5000)", mn=0)
            if aporte == 2:
                ap_raw        = _n("    Aporte mensal? (R$, ex: 300 — ou 0 se não houver)", mn=0)
                aporte_mensal = ap_raw if ap_raw is not None else 0.0

        if cap_inicial is None:
            cap_inicial = 0.0

    # ── Motor de recomendação ─────────────────────────────────────────────────
    rec_key, nivel_risco_perfil, meses_res, avisos, conhecimento = calcular_recomendacao(
        prazo=prazo,
        risco=risco,
        objetivo=objetivo,
        fluxo=fluxo,
        controle=controle,
        liquidez=liquidez,
        liquidez_pct=liquidez_pct,
        reserva_emerg=reserva_emerg,
        idade=idade,
        despesas=despesas,
        faixa_valor=faixa_valor,
        patrim_pct=patrim_pct,
        renda=renda,
        dividas=dividas,
        conhecimento=conhecimento,
        experiencia=experiencia,
        dependentes=dependentes,
        aporte=aporte,
        emocional=emocional,
        ir_tipo=ir_tipo,
        carteira_atual=carteira_atual,
        TAXAS=TAXAS,
    )

    # ── Montagem e classificação do portfólio ─────────────────────────────────
    portfolio = _build_portfolio(
        nivel_risco_perfil, conhecimento, faixa_valor, objetivo, renda, dividas,
        dependentes, aporte, carteira_atual, ir_tipo, fluxo, patrim_pct,
        liquidez_pct, despesas, idade, avisos,
    )

    perfil_exibido, risco_recomendado = _classificar_portfolio_final(portfolio)
    info       = _get_prod(perfil_exibido)
    taxa_perfil = sum((pct / 100) * TAXAS[_risco(k)] for k, pct in portfolio.items())
    taxa_pess  = max(ipca + 0.02, taxa_perfil * 0.6)
    aliq, pgbl = _aliq(perfil_exibido)

    # ── Resultado ─────────────────────────────────────────────────────────────
    print("\n" + "═" * 58)
    print("   ✅ ONDE INVESTIR:")
    print(f"   {_disp(perfil_exibido)}")
    print(f"   Risco efetivo do perfil: {nivel_risco_perfil}")
    print(f"   Risco da recomendação:   {risco_recomendado}")
    print("═" * 58)

    print("\n📋 O que comprar dentro desta categoria:")
    for item in info["o_que_comprar"]:
        print(f"   • {item}")

    print(f"\n   🛡️  Garantia:   {info['garantia']}")
    print(f"   💰 Imposto:    {info['imposto']}")
    print(f"   🏦 Onde abrir: {info['onde']}")

    print("\n📊 Sugestão de alocação do portfólio:")
    for k, v in portfolio.items():
        if v > 0:
            print(f"   {_disp(k):<45} {v:>3}%")
    print("   ─" * 30)
    print("   TOTAL                                          100%  (✓)")

    print("\n💹 Taxas utilizadas nas projeções:")
    print(f"   • SELIC {selic*100:.2f}% a.a. — BCB/SGS série 432 (ref. {_data_ref})")
    print(f"   • IPCA 12m {ipca*100:.2f}% a.a. — BCB/SGS série 13522")
    print(f"   • Ibovespa CAGR 10a {ibov_cagr*100:.1f}% a.a. — Yahoo Finance/yfinance")

    print(f"\n   Taxa da carteira final (bruto): ~{taxa_perfil*100:.2f}% a.a. bruto")
    print(f"   Alíquota IR:                   {aliq*100:.0f}% sobre GANHOS")
    print(f"   Juro real bruto s/ inflação:   ~{((1 + taxa_perfil) / (1 + ipca) - 1) * 100:.2f}% a.a.")
    print(f"   IPCA projetado:                {ipca*100:.2f}% a.a.")

    print(f"\n📅 Projeção de crescimento (~{taxa_perfil*100:.2f}% a.a. bruto):")
    print(f"   Capital inicial: R$ {cap_inicial:,.2f}")

    _pp = {
        "Prazo":              {1: "Curto (até 2a)", 2: "Médio (2-5a)", 3: "Longo (5a+)"}[prazo],
        "Risco emocional":    {1: "Conservador", 2: "Moderado", 3: "Agressivo"}[emocional],
        "Risco efetivo":      {1: "Baixo", 2: "Médio", 3: "Alto"}[nivel_risco_perfil],
        "Objetivo":           {1: "Reserva", 2: "Crescimento", 3: "Aposentadoria"}[objetivo],
        "Fluxo":              {1: "Renda passiva", 2: "Acúmulo"}[fluxo],
        "Controle":           {1: "Gestão própria", 2: "Delegar"}[controle],
        "Liquidez":           (f"Sim — {liquidez_pct:.0f}% estimado" if liquidez == 1 else "Não"),
        "Reserva emergência": (
            {1: "Sem reserva", 2: "Parcial", 3: "Completa"}[reserva_emerg]
            + f" (rec.: {meses_res} meses)"
        ),
        "Idade":              {1: "Jovem (≤35)", 2: "Adulto (36-55)", 3: "Sênior (55+)"}[idade],
        "Despesas fixas":     {1: "Nenhuma", 2: "Baixas", 3: "Altas"}[despesas],
        "Valor disponível":   {1: "Até R$1k", 2: "R$1k-10k", 3: ">R$10k"}[faixa_valor],
        "% do patrimônio":    {1: "<25%", 2: "25-75%", 3: ">75%"}[patrim_pct],
        "Renda":              {1: "CLT", 2: "PJ contratado", 3: "Autônomo", 4: "Sem renda"}[renda],
        "Dívidas":            {1: "Juros altos", 2: "Juros baixos", 3: "Sem dívidas"}[dividas],
        "Conhecimento":       {1: "Iniciante", 2: "Intermediário", 3: "Experiente"}[conhecimento],
        "Experiência":        ", ".join(experiencia),
        "Dependentes":        {1: "Nenhum", 2: "Um", 3: "Dois+"}[dependentes],
        "Aporte":             {1: "Único (Lump Sum)", 2: "Mensal (DCA)"}[aporte],
        "Declaração IR":      {1: "Completa", 2: "Simplificada", 3: "Não declara"}[ir_tipo],
        "Carteira atual":     {
            1: "Sem carteira", 2: "Conservadora", 3: "Moderada", 4: "Arrojada"
        }[carteira_atual],
    }

    print()
    print("   Prazo    VF Bruto   VF Real atual   VF Poder de Compra   Pessimista Líq.")
    print("   ────────────────────────────────────────────────────────────────────────")

    for anos in [1, 2, 5, 10, 20, 30]:
        vf_b = _vf_bruto(cap_inicial, aporte_mensal, taxa_perfil, anos)
        vf_l = _vf_liquido(cap_inicial, aporte_mensal, taxa_perfil, anos, aliq, pgbl)
        vf_r = _vf_real(vf_l, ipca, anos)
        vf_p = _vf_liquido(cap_inicial, aporte_mensal, taxa_pess,  anos, aliq, pgbl)
        print(
            f"   {anos:<2} ano(s) "
            f"R$ {vf_b:>11,.0f} "
            f"R$ {vf_l:>11,.0f} "
            f"R$ {vf_r:>11,.0f} "
            f"R$ {vf_p:>12,.0f}"
        )

    print("   ────────────────────────────────────────────────────────────────────────")
    print(f"   Pessimista = {taxa_pess*100:.1f}% a.a.")
    print(f"   VF Real = poder de compra em preços de hoje (IPCA {ipca*100:.1f}% a.a.)")

    # ── Avisos de negócio ─────────────────────────────────────────────────────
    if avisos:
        print("\n⚠️  Observações e ajustes aplicados:")
        for av in avisos:
            print(f"   {av}")

    # ── Salva JSON ────────────────────────────────────────────────────────────
    res = {
        "recomendacao":       perfil_exibido,
        "portfolio":          portfolio,
        "portfolio_display":  {_disp(k): v for k, v in portfolio.items() if v > 0},
        "nivel_risco_perfil": nivel_risco_perfil,
        "risco_recomendacao": risco_recomendado,
        "taxas_utilizadas": {
            "selic_atual":                  round(selic * 100, 2),
            "focus_selic":                  round(focus_selic * 100, 2) if focus_selic else None,
            "ipca_12m":                     round(ipca * 100, 2),
            "ibov_cagr_10a":                round(ibov_cagr * 100, 2),
            "taxa_perfil_bruto_pct":        round(TAXAS[nivel_risco_perfil] * 100, 2),
            "taxa_recomendacao_bruto_pct":  round(TAXAS[risco_recomendado] * 100, 2),
            "aliquota_ir_pct":              round(aliq * 100, 0),
            "pgbl":                         pgbl,
        },
        "perfil":          _pp,
        "avisos":          avisos,
        "fontes_de_dados": _fontes,
    }

    _ts    = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    _fname = f"perfil_investimento_{_ts}.json"

    try:
        with open(_fname, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=2)
        print(f"\n\n💾 Resultado salvo em: {_fname}")
    except Exception as e:
        print(f"\n\n⚠️  Não foi possível salvar o arquivo: {e}")

    _sep()
    print()


if __name__ == "__main__":
    main()
