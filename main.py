"""Interface de linha de comando do recomendador de investimentos."""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

from config import IR_RF
from core.categorias import _risco
from core.catalogo import _get_prod, _disp, _aliq
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
from recomendador_ativos import (
    MIN_PCT,
    _CLASSE as MAPA_CLASSE,
    _LABEL,
    recomendar_por_portfolio,
)
from utils.exceptions import DadosIndisponiveisError
from utils.logging_config import get_logger, setup_logging

setup_logging(logging.INFO)
logger = get_logger(__name__)

OUTPUT_DIR = Path(os.getenv("INVEST_OUTPUT_DIR", ".")).expanduser()
ANOS_PROJECAO = (1, 2, 5, 10, 20, 30)


def _salvar_json(nome: str, payload: dict) -> Optional[Path]:
    """Salva JSON no diretório configurado e devolve o caminho criado."""
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        path = OUTPUT_DIR / nome
        with path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2, default=str)
        logger.info("Arquivo JSON salvo em %s", path)
        return path
    except (OSError, TypeError, ValueError) as exc:
        logger.warning("Não foi possível salvar %s: %s", nome, exc)
        return None


def salvar_perfil_respostas(
    respostas: dict,
    timestamp: str,
) -> Optional[Path]:
    return _salvar_json(f"perfil_respostas_{timestamp}.json", respostas)


def _normalizar_experiencia(experiencia: list[str]) -> list[str]:
    """
    Impede a combinação contraditória de "nenhum" com produtos concretos.

    Se o usuário marcou produtos e também "nenhum", as escolhas concretas
    prevalecem. Uma lista vazia é interpretada como ausência de experiência.
    """
    itens = list(dict.fromkeys(experiencia or []))
    if len(itens) > 1 and "nenhum" in itens:
        itens.remove("nenhum")
        logger.warning(
            "A opção 'nenhum' foi removida porque outros produtos também "
            "foram informados."
        )
    return itens or ["nenhum"]


def _taxas_por_risco(
    selic: float,
    focus_selic: Optional[float],
    ibov_cagr: float,
) -> tuple[dict[int, float], float]:
    """
    Constrói as taxas usadas pelo modelo.

    Quando o Focus está disponível, ele realmente participa da taxa-base;
    antes, a média era apenas exibida e não entrava nas projeções.
    """
    taxa_base = (
        (selic + focus_selic) / 2.0
        if focus_selic is not None
        else selic
    )
    taxas = {
        1: taxa_base,
        2: (taxa_base + ibov_cagr) / 2.0,
        3: ibov_cagr,
    }
    return taxas, taxa_base


def _taxa_ponderada(
    portfolio: dict[str, int],
    taxas: dict[int, float],
) -> float:
    return sum(
        (pct / 100.0) * taxas[_risco(categoria)]
        for categoria, pct in portfolio.items()
        if pct > 0
    )


def _projetar_portfolio(
    cap_inicial: float,
    aporte_mensal: float,
    portfolio: dict[str, int],
    taxas: dict[int, float],
    ipca: float,
    anos: float,
    *,
    taxa_unica: Optional[float] = None,
) -> dict[str, float]:
    """
    Projeta cada classe separadamente.

    Isso evita aplicar a alíquota de um único "produto representativo" ao
    portfólio inteiro. Cada parcela usa a tributação configurada para sua
    própria categoria.
    """
    bruto = 0.0
    liquido = 0.0

    for categoria, pct in portfolio.items():
        if pct <= 0:
            continue

        peso = pct / 100.0
        taxa = (
            taxa_unica
            if taxa_unica is not None
            else taxas[_risco(categoria)]
        )
        aliquota, pgbl = _aliq(categoria)
        cap_classe = cap_inicial * peso
        aporte_classe = aporte_mensal * peso

        bruto += _vf_bruto(cap_classe, aporte_classe, taxa, anos)
        liquido += _vf_liquido(
            cap_classe,
            aporte_classe,
            taxa,
            anos,
            aliquota,
            pgbl,
        )

    return {
        "bruto": bruto,
        "liquido": liquido,
        "real": _vf_real(liquido, ipca, anos),
    }


def _aporte_necessario_para_meta(
    meta_valor: float,
    meta_prazo: float,
    cap_inicial: float,
    portfolio: dict[str, int],
    taxas: dict[int, float],
    ipca: float,
) -> Optional[float]:
    """
    Resolve por busca binária o aporte mensal necessário para a meta líquida.

    Retorna None se nem um aporte mensal extremamente alto alcançar a meta,
    protegendo o programa contra laços sem limite.
    """
    sem_aporte = _projetar_portfolio(
        cap_inicial,
        0.0,
        portfolio,
        taxas,
        ipca,
        meta_prazo,
    )["liquido"]
    if sem_aporte >= meta_valor:
        return 0.0

    inferior = 0.0
    superior = max(100.0, meta_valor / max(1.0, meta_prazo * 12.0))

    for _ in range(30):
        valor = _projetar_portfolio(
            cap_inicial,
            superior,
            portfolio,
            taxas,
            ipca,
            meta_prazo,
        )["liquido"]
        if valor >= meta_valor:
            break
        superior *= 2.0
    else:
        return None

    for _ in range(60):
        meio = (inferior + superior) / 2.0
        valor = _projetar_portfolio(
            cap_inicial,
            meio,
            portfolio,
            taxas,
            ipca,
            meta_prazo,
        )["liquido"]
        if valor >= meta_valor:
            superior = meio
        else:
            inferior = meio

    return superior


def _bloquear_divida_cara(taxas: dict[int, float]) -> None:
    _sep()
    print("\n🚨 ATENÇÃO — DÍVIDAS DE JUROS ALTOS DETECTADAS")
    _sep()
    print("\n   Cartão de crédito e cheque especial normalmente custam")
    print("   muito mais do que o retorno esperado dos investimentos.")
    print(f"\n   Maior retorno usado pelo modelo: ~{max(taxas.values()) * 100:.1f}% a.a.")
    print("\n   ✅ Recomendação: quite ou renegocie essas dívidas primeiro.")
    print("   Depois, refaça o questionário.\n")

def main() -> None:
    try:
        market = load_market_data()
    except DadosIndisponiveisError as exc:
        print("\n" + "═" * 58)
        print("   📊 RECOMENDADOR DE INVESTIMENTOS")
        print("═" * 58)
        print("\n❌ Não foi possível obter os indicadores obrigatórios:")
        print(f"   {exc}")
        print("\n   O sistema não inventa valores fixos como substituto.")
        print("   Verifique sua conexão e tente novamente em instantes.")
        return

    try:
        selic = float(market["selic"])
        focus_raw = market.get("focus_selic")
        focus_selic = (
            float(focus_raw) if focus_raw is not None else None
        )
        ipca = float(market["ipca"])
        ibov_cagr = float(market["ibov_cagr"])
        data_ref = str(market["data_ref"])
        fontes = list(market.get("fontes", []))
        avisos_api = list(market.get("avisos", []))
    except (KeyError, TypeError, ValueError) as exc:
        logger.error("Payload de mercado inválido: %s", exc)
        print("\n❌ Os dados de mercado retornaram em formato inválido.")
        print("   Apague o cache de mercado e tente novamente.")
        return

    TAXAS, taxa_base = _taxas_por_risco(
        selic,
        focus_selic,
        ibov_cagr,
    )

    print("\n" + "═" * 58)
    print("   📊 RECOMENDADOR DE INVESTIMENTOS")
    print("   Análise completa de perfil — versão melhorada")
    print("═" * 58)

    if avisos_api:
        print("\n   ⚠️  Avisos sobre os dados de mercado:")
        for aviso_api in avisos_api:
            print(f"      {aviso_api}")
    else:
        print(f"\n   ✅ Indicadores carregados com sucesso ({data_ref})")

    print("\n   Dados utilizados:")
    for fonte in fontes:
        print(f"      • {fonte}")
    if focus_selic is not None:
        print("\n   Taxa-base = média da SELIC atual com o Focus:")
        print(
            f"      ({selic * 100:.2f}% + {focus_selic * 100:.2f}%) "
            f"÷ 2 = {taxa_base * 100:.2f}% a.a."
        )

    print("\n   Taxas por perfil de risco usadas pelo modelo:")
    for nivel, label in [(1, "Baixo"), (2, "Médio"), (3, "Alto")]:
        t = TAXAS[nivel]
        liq = t * (1 - IR_RF)
        real = (1 + liq) / (1 + ipca) - 1
        print(
            f"      {label:<6}: {t * 100:.2f}% bruto | "
            f"{liq * 100:.2f}% líq. aprox. | "
            f"{real * 100:.2f}% real"
        )
    print(
        f"      IPCA de referência: {ipca * 100:.2f}% a.a. | "
        "A projeção detalhada trata cada classe separadamente."
    )
    print("\nResponda as perguntas para receber sua recomendação.")

    _sep()

    # ── Questionário ──────────────────────────────────────────────────────────
    primeira = _p_primeira(
        "1. Qual é o seu prazo de investimento?\n"
        "   (curto = até 2 anos | médio = 2 a 5 anos | longo = acima de 5 anos)",
        _PD,
    )
    modo_demo = primeira == "__DEMO__"

    modo_meta: int = 3
    meta_valor: Optional[float] = None
    meta_prazo: Optional[float] = None
    cap_inicial: float = 0.0
    aporte_mensal: float           = 0.0

    if modo_demo:
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
        modo_meta      = int(d.get("modo_meta", 2))
        meta_valor     = d.get("meta_valor")
        meta_prazo     = d.get("meta_prazo")
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
            ) or 0.0

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
            cap_inicial = _n("    Capital inicial disponível? (R$, ex: 10000)", mn=0) or 0.0
            if aporte == 2:
                ap_raw        = _n("    Aporte mensal? (R$, ex: 500 — ou 0 se não houver)", mn=0)
                aporte_mensal = ap_raw if ap_raw is not None else 0.0
        elif modo_meta == 2:
            cap_inicial = _n("    Capital inicial disponível? (R$, ex: 5000)", mn=0) or 0.0
            if aporte == 2:
                ap_raw        = _n("    Aporte mensal? (R$, ex: 300 — ou 0 se não houver)", mn=0)
                aporte_mensal = ap_raw if ap_raw is not None else 0.0

    experiencia = _normalizar_experiencia(experiencia)

    # Salva as respostas antes do processamento para permitir auditoria.
    respostas_usuario = {
        "prazo": prazo, "risco": risco, "objetivo": objetivo, "fluxo": fluxo,
        "controle": controle, "liquidez": liquidez, "liquidez_pct": liquidez_pct,
        "reserva_emerg": reserva_emerg, "idade": idade, "despesas": despesas,
        "faixa_valor": faixa_valor, "patrim_pct": patrim_pct, "renda": renda,
        "dividas": dividas, "conhecimento": conhecimento, "experiencia": experiencia,
        "dependentes": dependentes, "aporte": aporte, "emocional": emocional,
        "ir_tipo": ir_tipo, "carteira_atual": carteira_atual,
        "modo_meta": modo_meta, "meta_valor": meta_valor,
        "meta_prazo": meta_prazo,
        "cap_inicial": cap_inicial, "aporte_mensal": aporte_mensal,
    }
    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    salvar_perfil_respostas(respostas_usuario, timestamp)

    # Evita que sys.exit() dentro da implementação legada do recomendador
    # encerre o processo inteiro.
    if dividas == 1:
        _bloquear_divida_cara(TAXAS)
        return

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

    portfolio = _build_portfolio(
        nivel_risco_perfil, conhecimento, faixa_valor, objetivo, renda, dividas,
        dependentes, aporte, carteira_atual, ir_tipo, fluxo, patrim_pct,
        liquidez_pct, despesas, idade, avisos,
    )

    categoria_carteira, risco_recomendado = (
        _classificar_portfolio_final(portfolio)
    )

    # A recomendação específica produzida por recomendador.py não deve ser
    # descartada pela classificação genérica da carteira.
    recomendacao_principal = rec_key
    info = _get_prod(recomendacao_principal)
    taxa_perfil = _taxa_ponderada(portfolio, TAXAS)

    # Um cenário chamado de pessimista nunca pode render mais que o cenário
    # central, mesmo quando IPCA + 2 p.p. superar a taxa da carteira.
    taxa_pess = min(
        taxa_perfil,
        max(ipca + 0.02, taxa_perfil * 0.60),
    )

    # ── Resultado ─────────────────────────────────────────────────────────────
    print("\n" + "═" * 58)
    print("   ✅ RECOMENDAÇÃO PRINCIPAL:")
    print(f"   {_disp(recomendacao_principal)}")
    rlabel = {1: "Conservador", 2: "Moderado", 3: "Agressivo"}
    print(f"   Perfil de risco: {rlabel[nivel_risco_perfil]}")
    if categoria_carteira != recomendacao_principal:
        print(
            "   Categoria representativa da carteira: "
            f"{_disp(categoria_carteira)}"
        )
    if risco_recomendado != nivel_risco_perfil:
        print(
            f"   ℹ️  Alocação final classificada como "
            f"{rlabel[risco_recomendado]} após os ajustes de segurança."
        )
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
    print(
        f"   • SELIC {selic * 100:.2f}% a.a. — "
        f"BCB/SGS série 432 (ref. {data_ref})"
    )
    if focus_selic is not None:
        print(
            f"   • Focus SELIC {focus_selic * 100:.2f}% a.a. — BCB/Olinda"
        )
    print(
        f"   • IPCA 12m {ipca * 100:.2f}% a.a. — BCB/SGS série 13522"
    )
    print(
        f"   • Ibovespa CAGR 10a {ibov_cagr * 100:.2f}% a.a. — "
        "Yahoo Finance/yfinance"
    )

    print(
        f"\n   Taxa ponderada da carteira: ~"
        f"{taxa_perfil * 100:.2f}% a.a. bruto"
    )
    print("   Tributação: calculada separadamente para cada classe.")
    print(
        f"   Juro real bruto s/ inflação: ~"
        f"{((1 + taxa_perfil) / (1 + ipca) - 1) * 100:.2f}% a.a."
    )
    print(f"   IPCA de referência:          {ipca * 100:.2f}% a.a.")

    print(
        f"\n📅 Projeção de crescimento "
        f"(~{taxa_perfil * 100:.2f}% a.a. bruto):"
    )
    print(f"   Capital inicial: R$ {cap_inicial:,.2f}")
    print(f"   Aporte mensal:   R$ {aporte_mensal:,.2f}")

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
    if meta_valor is not None and meta_prazo is not None:
        _pp["Meta financeira"] = (
            f"R$ {meta_valor:,.2f} em {meta_prazo:g} ano(s)"
        )

    print()
    print(
        "   Prazo      VF Bruto     VF Líquido   "
        "Poder de compra   Pessimista líq."
    )
    print("   ────────────────────────────────────────────────────────────────────────")

    projecoes: list[dict[str, float]] = []
    for anos in ANOS_PROJECAO:
        central = _projetar_portfolio(
            cap_inicial,
            aporte_mensal,
            portfolio,
            TAXAS,
            ipca,
            anos,
        )
        pessimista = _projetar_portfolio(
            cap_inicial,
            aporte_mensal,
            portfolio,
            TAXAS,
            ipca,
            anos,
            taxa_unica=taxa_pess,
        )
        projecoes.append(
            {
                "anos": anos,
                "vf_bruto": central["bruto"],
                "vf_liquido": central["liquido"],
                "vf_real": central["real"],
                "vf_pessimista_liquido": pessimista["liquido"],
            }
        )
        print(
            f"   {anos:<2} ano(s) "
            f"R$ {central['bruto']:>11,.0f} "
            f"R$ {central['liquido']:>11,.0f} "
            f"R$ {central['real']:>13,.0f} "
            f"R$ {pessimista['liquido']:>13,.0f}"
        )

    print("   ────────────────────────────────────────────────────────────────────────")
    print(f"   Pessimista = {taxa_pess * 100:.2f}% a.a.")
    print(
        f"   Poder de compra = valor líquido descontado por "
        f"IPCA de {ipca * 100:.2f}% a.a."
    )

    resultado_meta: Optional[dict[str, Any]] = None
    if meta_valor is not None and meta_prazo is not None:
        projecao_meta = _projetar_portfolio(
            cap_inicial,
            aporte_mensal,
            portfolio,
            TAXAS,
            ipca,
            meta_prazo,
        )
        valor_meta_projetado = projecao_meta["liquido"]
        diferenca_meta = valor_meta_projetado - meta_valor
        atingida = diferenca_meta >= 0
        aporte_necessario = _aporte_necessario_para_meta(
            meta_valor,
            meta_prazo,
            cap_inicial,
            portfolio,
            TAXAS,
            ipca,
        )

        print("\n🎯 Análise da meta financeira:")
        print(
            f"   Meta:              R$ {meta_valor:,.2f} "
            f"em {meta_prazo:g} ano(s)"
        )
        print(f"   Valor projetado:   R$ {valor_meta_projetado:,.2f} líquido")
        if atingida:
            print(f"   ✅ Meta atingível, com margem de R$ {diferenca_meta:,.2f}.")
        else:
            print(f"   ⚠️  Déficit projetado: R$ {abs(diferenca_meta):,.2f}.")
            if aporte_necessario is not None:
                print(
                    f"   Aporte mensal estimado para atingir a meta: "
                    f"R$ {aporte_necessario:,.2f}"
                )
            else:
                print(
                    "   Não foi possível estimar um aporte mensal dentro "
                    "dos limites do cálculo."
                )

        resultado_meta = {
            "valor_alvo": meta_valor,
            "prazo_anos": meta_prazo,
            "valor_liquido_projetado": valor_meta_projetado,
            "atingida": atingida,
            "diferenca": diferenca_meta,
            "aporte_mensal_informado": aporte_mensal,
            "aporte_mensal_estimado": aporte_necessario,
        }

    if avisos:
        print("\n⚠️  Observações e ajustes aplicados:")
        for av in avisos:
            print(f"   {av}")

    # ── Ativos específicos ────────────────────────────────────────────────────
    ativos_sugeridos: dict[str, list] = {}
    indisponiveis: dict[str, str] = {}

    # A recomendação principal também participa da busca, ainda que a
    # classificação genérica do portfólio não tenha preservado sua chave.
    portfolio_busca = dict(portfolio)
    if (
        recomendacao_principal in MAPA_CLASSE
        and recomendacao_principal not in portfolio_busca
    ):
        portfolio_busca[recomendacao_principal] = MIN_PCT

    classes_no_portfolio = {
        MAPA_CLASSE[rk]
        for rk, pct in portfolio_busca.items()
        if pct >= MIN_PCT and rk in MAPA_CLASSE
    }

    if classes_no_portfolio:
        _sep()
        _nomes = {
            "acoes":  "ações",
            "fiis":   "FIIs",
            "cripto": "criptomoedas",
            "rf":     "renda fixa",
            "fundos": "fundos",
        }
        _tempo = {
            "acoes":   "~20s — busca e rankeia dados em tempo real da bolsa",
            "fiis":    "~20s — busca e rankeia dados em tempo real da bolsa",
            "cripto":  "~20s — busca e rankeia dados em tempo real",
            "rf":      "~1s  — calcula retorno real a partir de SELIC/IPCA/CDI atuais",
            "fundos":  "~5-10s — processa histórico de cotas da CVM em lote e rankeia",
            "etf":     "~5s  — busca cotações de ETFs via Yahoo Finance",
            "etfs":    "~5s  — busca cotações de ETFs via Yahoo Finance",
            "estruturados": "~15s — baixa cadastro B3 e negociações balcão (cached 7 dias)",
        }
        classes_sorted = sorted(classes_no_portfolio)
        classes_str = " e ".join(
            _nomes.get(classe, classe)
            for classe in classes_sorted
        )

        print(f"\n📈 Seu portfólio inclui {classes_str}.")
        print("   Posso recomendar ativos específicos e rankeados para cada grupo:")
        for classe in classes_sorted:
            nome_classe = _nomes.get(classe, classe).capitalize()
            tempo = _tempo.get(classe, "tempo variável — consulta online")
            print(f"     • {nome_classe:<12} — {tempo}")
        print()
        print("   Quer ver as recomendações? (sim | não)")
        quer_ativos = input("   → ").strip().lower() in ("sim", "s", "yes", "y")
    else:
        quer_ativos = False

    if quer_ativos:
        print("\n   🔍 Buscando e rankeando ativos...")
        ativos_sugeridos = recomendar_por_portfolio(
            portfolio_busca, nivel_risco_perfil,
            selic=selic, ipca=ipca, ibov_cagr=ibov_cagr,
        )

        indisponiveis = ativos_sugeridos.pop("_indisponiveis", {})

        if not ativos_sugeridos and not indisponiveis:
            print("\n   ⚠️  Não foi possível buscar ativos no momento.")
            print("   Verifique sua conexão ou tente novamente mais tarde.")
        else:
            perfil_label = (
                "conservador" if nivel_risco_perfil == 1 else
                "moderado"    if nivel_risco_perfil == 2 else
                "agressivo"
            )
            for classe, lista in ativos_sugeridos.items():
                if not lista:
                    continue
                label = _LABEL.get(classe, classe.upper())
                _sep()
                print(f"\n📊 TOP {len(lista)} {label} PARA SEU PERFIL ({perfil_label}):")
                print()
                for i, ativo in enumerate(lista, 1):
                    ticker = ativo.get("ticker", "")
                    nome   = ativo.get("nome", "")
                    preco  = ativo.get("preco", 0)
                    score  = ativo.get("score", 0)
                    print(f"   {i}. {ticker:<8} {'— ' + nome if nome else ''}")
                    print(f"      Score: {score:.0f}/10"
                          + (f"   Preço: R${preco:,.2f}" if preco else ""))
                    for motivo in ativo.get("motivos", []):
                        print(f"      {motivo}")
                    print()

            if indisponiveis:
                _sep()
                print("\n⚠️  Fontes de dados indisponíveis no momento (sem mock/fallback):")
                for classe, motivo in indisponiveis.items():
                    label = _LABEL.get(classe, classe.upper())
                    print(f"   • {label}: {motivo}")

    # ── Salva JSON ────────────────────────────────────────────────────────────
    res = {
        "recomendacao": recomendacao_principal,
        "recomendacao_display": _disp(recomendacao_principal),
        "categoria_representativa_carteira": categoria_carteira,
        "portfolio": portfolio,
        "portfolio_display": {
            _disp(k): v for k, v in portfolio.items() if v > 0
        },
        "nivel_risco_perfil": nivel_risco_perfil,
        "risco_recomendacao": risco_recomendado,
        "taxas_utilizadas": {
            "selic_atual_pct": round(selic * 100, 2),
            "focus_selic_pct": (
                round(focus_selic * 100, 2)
                if focus_selic is not None
                else None
            ),
            "taxa_base_pct": round(taxa_base * 100, 2),
            "ipca_12m_pct": round(ipca * 100, 2),
            "ibov_cagr_10a_pct": round(ibov_cagr * 100, 2),
            "taxa_carteira_ponderada_bruto_pct": round(
                taxa_perfil * 100,
                2,
            ),
            "taxa_pessimista_bruto_pct": round(taxa_pess * 100, 2),
            "tributacao_por_classe": {
                _disp(categoria): {
                    "aliquota_pct": round(_aliq(categoria)[0] * 100, 2),
                    "incide_sobre_total_pgbl": _aliq(categoria)[1],
                }
                for categoria, pct in portfolio.items()
                if pct > 0
            },
        },
        "perfil": _pp,
        "meta": resultado_meta,
        "projecoes": projecoes,
        "avisos": avisos,
        "ativos_sugeridos": ativos_sugeridos,
        "classes_indisponiveis": indisponiveis,
        "fontes_de_dados": fontes,
        "dados_mercado": {
            "data_ref": data_ref,
            "fetched_at": market.get("fetched_at"),
            "cache_status": market.get("cache_status"),
        },
    }

    ts_resultado = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    nome_resultado = f"perfil_investimento_{ts_resultado}.json"
    caminho_resultado = _salvar_json(nome_resultado, res)
    if caminho_resultado is not None:
        print(f"\n\n💾 Resultado salvo em: {caminho_resultado}")
    else:
        print("\n\n⚠️  Não foi possível salvar o resultado.")

    _sep()
    print()

if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\n\nOperação cancelada pelo usuário.")