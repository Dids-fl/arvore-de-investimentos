"""Interface de linha de comando do recomendador de investimentos."""

from __future__ import annotations

import datetime as dt
import json
import logging
import math
import os
from pathlib import Path

from calendarios.sincronizar_b3 import sincronizar_calendarios_relevantes
from cli import (
    _APD,
    _CAD,
    _CD,
    _DD,
    _DPD,
    _EMD,
    _FD,
    _ID,
    _IRD,
    _KD,
    _LD,
    _MTD,
    _OD,
    _PD,
    _PPD,
    _RD,
    _RND,
    _RSD,
    _VD,
    DEMO_PADRAO,
    _DVd,
    _m,
    _n,
    _p,
    _p_primeira,
    _sep,
)
from engine import (
    DividaJurosAltosError,
    RecomendacaoBloqueadaError,
    buscar_ativos_da_analise,
    criar_analise,
    montar_payload_exportacao,
    resumo_taxas_mercado,
    rotulo_classe_ativo,
)
from mercado import load_market_data
from utils.exceptions import DadosIndisponiveisError
from utils.logging_config import get_logger, setup_logging

setup_logging(logging.INFO)
logger = get_logger(__name__)

OUTPUT_DIR = Path(os.getenv("INVEST_OUTPUT_DIR", ".")).expanduser()


def _salvar_json(nome: str, payload: dict) -> Path | None:
    """Salva JSON no diretório configurado e devolve o caminho criado."""
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        caminho = OUTPUT_DIR / nome
        with caminho.open("w", encoding="utf-8") as arquivo:
            json.dump(
                payload,
                arquivo,
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        logger.info("Arquivo JSON salvo em %s", caminho)
        return caminho
    except (OSError, TypeError, ValueError) as exc:
        logger.warning("Não foi possível salvar %s: %s", nome, exc)
        return None


def salvar_perfil_respostas(
    respostas: dict,
    timestamp: str,
) -> Path | None:
    return _salvar_json(f"perfil_respostas_{timestamp}.json", respostas)


def _entrada_opcional(
    mensagem: str,
    opcoes: set[str],
) -> str | None:
    """Lê uma opção fiscal; Enter mantém o dado como desconhecido."""
    while True:
        valor = input(f"{mensagem}\n   → ").strip().casefold()
        if not valor:
            return None
        if valor in opcoes:
            return valor
        print("   Opção inválida. Use " + ", ".join(sorted(opcoes)) + ".")


def _numero_opcional(mensagem: str) -> float | None:
    while True:
        valor = input(f"{mensagem}\n   → ").strip()
        if not valor:
            return None
        try:
            normalizado = (
                valor.replace(".", "").replace(",", ".")
                if "," in valor
                else valor
            )
            numero = float(normalizado)
        except ValueError:
            print("   Informe um número válido ou pressione Enter.")
            continue
        if not math.isfinite(numero) or numero < 0:
            print("   O valor deve ser finito e não negativo.")
            continue
        return numero


def _formatar_moeda(valor: object, casas: int = 0) -> str:
    if not isinstance(valor, (int, float)):
        return "indeterminado"
    return f"R$ {valor:,.{casas}f}"


def _coletar_respostas(primeira: object) -> dict:
    """Coleta apenas dados de interface; a interpretação pertence ao engine."""
    if primeira == "__DEMO__":
        respostas = dict(DEMO_PADRAO)
        respostas.setdefault("modo_meta", 2)
        respostas.setdefault("meta_valor", None)
        respostas.setdefault("meta_prazo", None)
        respostas.setdefault("cap_inicial", 0.0)
        respostas.setdefault("aporte_mensal", 0.0)
        respostas.setdefault("despesas_essenciais_mensais", 0.0)
        respostas.setdefault("reserva_atual", 0.0)
        respostas.setdefault("regime_previdencia", None)
        respostas.setdefault("renda_tributavel_anual", None)
        respostas.setdefault("elegibilidade_deducao_pgbl", None)
        respostas.setdefault("renda_tributavel_por_ano", {})
        respostas.setdefault("crescimento_renda_tributavel_anual", 0.0)
        respostas.setdefault("valor_aportes_ano", 0.0)
        respostas.setdefault("jurisdicao_cripto", None)
        return respostas

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
        "5. Prefere gerir os investimentos ou delegar a um gestor?\n"
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
        liquidez_pct = (
            _n(
                "   6a. Em uma emergência, qual percentual precisaria?\n"
                "       (exemplo: 30)",
                mn=1,
                mx=100,
            )
            or 0.0
        )

    reserva_emerg = _p(
        "7. Você possui reserva de emergência?\n"
        "   (não tenho | parcial | sim)",
        _RSD,
    )
    idade = _p(
        "8. Qual é sua faixa de idade?\n"
        "   (jovem = até 35 | adulto = 36 a 55 | sênior = acima de 55)",
        _ID,
    )
    despesas = _p(
        "9. Como são suas obrigações financeiras fixas?\n"
        "   (nenhuma | baixas | altas)",
        _DD,
    )
    despesas_essenciais_mensais = (
        _n(
            "   9a. Qual é o valor mensal das despesas essenciais? (R$)\n"
            "       Inclua moradia, alimentação, saúde, transporte e contas.",
            mn=0,
        )
        or 0.0
    )
    reserva_atual = (
        _n(
            "   9b. Quanto já possui separado para emergências? (R$)\n"
            "       Considere somente valores de liquidez imediata.",
            mn=0,
        )
        or 0.0
    )
    faixa_valor = _p(
        "10. Quanto possui para investir agora?\n"
        "    (baixo = até R$1.000 | médio = R$1k-10k | alto = acima)",
        _VD,
    )
    patrim_pct = _p(
        "11. Qual parcela do patrimônio esse valor representa?\n"
        "    (baixo = <25% | médio = 25%-75% | alto = >75%)",
        _PPD,
    )
    renda = _p(
        "12. Qual é sua situação de renda?\n"
        "    (clt | pj contratado | autônomo | sem renda)",
        _RND,
    )
    dividas = _p(
        "13. Você possui dívidas ativas?\n"
        "    (juros altos | juros baixos | não tenho)",
        _DVd,
    )
    conhecimento = _p(
        "14. Qual é seu conhecimento sobre investimentos?\n"
        "    (iniciante | intermediário | experiente)",
        _KD,
    )
    experiencia = _m(
        "15. Em quais produtos investiu nos últimos dois anos?\n"
        "    (poupança | tesouro | ações | fundos | opções | nenhum)\n"
        "    Separe por vírgula."
    )
    dependentes = _p(
        "16. Quantas pessoas dependem financeiramente de você?\n"
        "    (nenhum | um | dois ou mais)",
        _DPD,
    )
    aporte = _p(
        "17. Pretende realizar investimento único ou aportes mensais?\n"
        "    (único | mensal)",
        _APD,
    )
    emocional = _p(
        "18. Se a carteira caísse 30% em seis meses, o que faria?\n"
        "    (venderia tudo | esperaria recuperar | compraria mais)",
        _EMD,
    )
    ir_tipo = _p(
        "19. Como declara o Imposto de Renda?\n"
        "    (completo | simplificado | não declaro)",
        _IRD,
    )
    carteira_atual = _p(
        "20. Você já possui carteira de investimentos?\n"
        "    (não tenho | conservadora | moderada | arrojada)",
        _CAD,
    )
    modo_meta = _p(
        "21. O que deseja calcular?\n"
        "    (sim = atingir valor | rendendo = crescimento | não = pular)",
        _MTD,
    )

    meta_valor: float | None = None
    meta_prazo: float | None = None
    cap_inicial = 0.0
    aporte_mensal = 0.0
    if modo_meta == 1:
        meta_valor = _n(
            "    Qual valor deseja acumular? (R$)",
            mn=1,
        )
        meta_prazo = _n(
            "    Em quantos anos?",
            mn=1,
            mx=50,
        )
        cap_inicial = (
            _n("    Capital inicial disponível? (R$)", mn=0)
            or 0.0
        )
        if aporte == 2:
            aporte_mensal = (
                _n("    Aporte mensal? (R$)", mn=0)
                or 0.0
            )
    elif modo_meta == 2:
        cap_inicial = (
            _n("    Capital inicial disponível? (R$)", mn=0)
            or 0.0
        )
        if aporte == 2:
            aporte_mensal = (
                _n("    Aporte mensal? (R$)", mn=0)
                or 0.0
            )

    print(
        "\n   Dados tributários opcionais. Pressione Enter quando não souber; "
        "o resultado será marcado como indeterminado quando necessário."
    )
    regime_previdencia = _entrada_opcional(
        "   Regime da previdência (regressivo | progressivo | Enter)",
        {"regressivo", "progressivo"},
    )
    elegibilidade_deducao_pgbl = None
    if ir_tipo == 1:
        elegibilidade_texto = _entrada_opcional(
            (
                "   Cumpre as condições legais da dedução do PGBL? "
                "(sim | não | Enter)"
            ),
            {"sim", "não", "nao"},
        )
        elegibilidade_deducao_pgbl = {
            "sim": True,
            "não": False,
            "nao": False,
            None: None,
        }[elegibilidade_texto]
    renda_tributavel_anual = None
    if (
        regime_previdencia == "progressivo"
        or elegibilidade_deducao_pgbl is True
    ):
        renda_tributavel_anual = _numero_opcional(
            "   Renda tributável anual aproximada (R$ | Enter)"
        )
    valor_aportes_ano = 0.0
    crescimento_renda_tributavel_anual = 0.0
    if elegibilidade_deducao_pgbl is True:
        valor_aportes_ano = (
            _numero_opcional(
                "   PGBL/FAPI já usado no limite deste ano (R$ | Enter)"
            )
            or 0.0
        )
        crescimento_renda_tributavel_anual = (
            _numero_opcional(
                "   Crescimento anual esperado da renda (% | Enter = 0)"
            )
            or 0.0
        ) / 100.0
    jurisdicao_cripto = _entrada_opcional(
        "   Custódia de cripto (brasil | exterior | Enter)",
        {"brasil", "exterior"},
    )

    respostas = {
        "prazo": prazo,
        "risco": risco,
        "objetivo": objetivo,
        "fluxo": fluxo,
        "controle": controle,
        "liquidez": liquidez,
        "liquidez_pct": liquidez_pct,
        "reserva_emerg": reserva_emerg,
        "idade": idade,
        "despesas": despesas,
        "despesas_essenciais_mensais": (
            despesas_essenciais_mensais
        ),
        "reserva_atual": reserva_atual,
        "faixa_valor": faixa_valor,
        "patrim_pct": patrim_pct,
        "renda": renda,
        "dividas": dividas,
        "conhecimento": conhecimento,
        "experiencia": experiencia,
        "dependentes": dependentes,
        "aporte": aporte,
        "emocional": emocional,
        "ir_tipo": ir_tipo,
        "carteira_atual": carteira_atual,
        "modo_meta": modo_meta,
        "meta_valor": meta_valor,
        "meta_prazo": meta_prazo,
        "cap_inicial": cap_inicial,
        "aporte_mensal": aporte_mensal,
        "regime_previdencia": regime_previdencia,
        "renda_tributavel_anual": renda_tributavel_anual,
        "elegibilidade_deducao_pgbl": elegibilidade_deducao_pgbl,
        "valor_aportes_ano": valor_aportes_ano,
        "renda_tributavel_por_ano": {},
        "crescimento_renda_tributavel_anual": (
            crescimento_renda_tributavel_anual
        ),
        "jurisdicao_cripto": jurisdicao_cripto,
    }
    return respostas


def _imprimir_mercado(market: dict, resumo: dict) -> None:
    print("\n" + "═" * 58)
    print("   📊 RECOMENDADOR DE INVESTIMENTOS")
    print("═" * 58)

    avisos = list(market.get("avisos", []))
    if avisos:
        print("\n   ⚠️  Avisos dos dados de mercado:")
        for aviso in avisos:
            print(f"      {aviso}")
    else:
        print(
            "\n   ✅ Indicadores carregados com sucesso "
            f"({market.get('data_ref', 'sem data')})"
        )

    print("\n   Fontes utilizadas:")
    for fonte in market.get("fontes", []):
        print(f"      • {fonte}")

    if resumo["focus_selic"] is not None:
        print(
            "\n   Taxa-base equivalente da curva SELIC/Focus: "
            f"{resumo['taxa_base'] * 100:.2f}% a.a."
        )

    print("\n   Hipóteses por perfil:")
    for perfil in resumo["perfis"]:
        print(
            f"      {perfil['rotulo']:<11} "
            f"{perfil['taxa_bruta'] * 100:.2f}% bruto | "
            f"{perfil['taxa_real_bruta'] * 100:.2f}% real bruto"
        )
    print(
        "      O líquido depende do produto, prazo e contexto fiscal da "
        "carteira."
    )
    print(
        f"      IPCA de referência: {resumo['ipca'] * 100:.2f}% a.a."
    )


def _imprimir_recomendacao(analise: dict) -> None:
    resultado = analise["resultado"]
    info = resultado["info_principal"]

    print("\n" + "═" * 58)
    print("   ✅ RECOMENDAÇÃO PRINCIPAL:")
    print(f"   {resultado['recomendacao_display']}")
    print(f"   Perfil de risco: {resultado['nivel_risco_display']}")
    if resultado["perfil_exibido"] != resultado["recomendacao_principal"]:
        print(
            "   Classe usada apenas para resumir o risco: "
            f"{resultado['perfil_display']}"
        )
    if resultado["risco_recomendado"] != resultado["nivel_risco_perfil"]:
        print(
            "   Classificação da alocação final: "
            f"{resultado['risco_recomendado_display']}"
        )
    print("═" * 58)

    print("\n📋 O que avaliar ou comprar:")
    for item in info["o_que_comprar"]:
        print(f"   • {item}")
    print(f"\n   🛡️  Garantia: {info['garantia']}")
    print(f"   💰 Imposto:  {info['imposto']}")
    print(f"   🏦 Onde:     {info['onde']}")

    print("\n📊 Alocação sugerida:")
    for item in resultado["portfolio_itens"]:
        print(f"   {item['nome']:<45} {item['percentual']:>3}%")
    print("   ─" * 30)
    print("   TOTAL                                          100%")

    print(
        "\n   Taxa ponderada bruta: "
        f"{resultado['taxa_perfil'] * 100:.2f}% a.a."
    )
    print(
        "   Cenário pessimista:   "
        f"{resultado['taxa_pess'] * 100:.2f}% a.a."
    )
    print("   Tributação calculada separadamente por classe e lote.")
    reserva = resultado.get("plano_reserva")
    if isinstance(reserva, dict):
        print(
            "   Reserva-alvo: "
            f"R$ {reserva['valor_alvo']:,.2f} | "
            f"Atual: R$ {reserva['valor_atual']:,.2f} | "
            f"Déficit: R$ {reserva['deficit']:,.2f}"
        )


def _imprimir_projecoes(analise: dict) -> None:
    respostas = analise["respostas"]
    print("\n📅 Projeção de crescimento:")
    print(f"   Capital inicial: R$ {respostas['cap_inicial']:,.2f}")
    print(f"   Aporte mensal:   R$ {respostas['aporte_mensal']:,.2f}")
    print()
    print(
        "   Prazo       VF Bruto        Imposto      VF Líquido   "
        "Precisão fiscal"
    )
    print("   ─────────────────────────────────────────────────────────────────────")
    for linha in analise["projecoes"]:
        print(
            f"   {linha['anos']:>4g} ano(s) "
            f"{_formatar_moeda(linha['vf_bruto']):>15} "
            f"{_formatar_moeda(linha['imposto_estimado']):>15} "
            f"{_formatar_moeda(linha['vf_liquido']):>15} "
            f"{linha['precisao_tributaria']}"
        )
    indeterminadas = [
        linha
        for linha in analise["projecoes"]
        if linha["vf_liquido"] is None
    ]
    if indeterminadas:
        print(
            "\n   ⚠️  Há classes sem dados fiscais suficientes. "
            "O sistema não inventou uma alíquota para completar o líquido."
        )
        for premissa in indeterminadas[0]["premissas_tributarias"]:
            print(f"      • {premissa}")


def _imprimir_meta(analise: dict) -> None:
    meta = analise.get("meta")
    if meta is None:
        return

    print("\n🎯 Análise da meta financeira:")
    print(
        f"   Meta:            R$ {meta['valor_alvo']:,.2f} "
        f"em {meta['prazo_anos']:g} ano(s)"
    )
    if meta["valor_liquido_projetado"] is None:
        print(
            "   ⚠️  Resultado líquido indeterminado: "
            f"{meta['motivo_indeterminacao']}"
        )
        return
    print(
        "   Valor projetado: "
        f"R$ {meta['valor_liquido_projetado']:,.2f} líquido"
    )
    if meta["atingida"]:
        print(
            "   ✅ Meta atingível, com margem de "
            f"R$ {meta['diferenca']:,.2f}."
        )
    else:
        print(
            "   ⚠️  Déficit projetado: "
            f"R$ {abs(meta['diferenca']):,.2f}."
        )
        if meta["aporte_mensal_estimado"] is not None:
            print(
                "   Aporte mensal total estimado: "
                f"R$ {meta['aporte_mensal_estimado']:,.2f}"
            )


def _imprimir_perfil_e_avisos(analise: dict) -> None:
    resultado = analise["resultado"]
    print("\n🧾 Resumo do perfil:")
    for criterio, valor in resultado["perfil_resumo"].items():
        print(f"   {criterio:<26} {valor}")

    if resultado["avisos"]:
        print("\n⚠️  Observações e ajustes:")
        for aviso in resultado["avisos"]:
            print(f"   {aviso}")


def _consultar_e_imprimir_ativos(analise: dict) -> None:
    resultado = analise["resultado"]
    classes = resultado["classes_no_portfolio"]
    if not classes:
        return

    estimativas = {
        "acoes": "~20s — consulta e ranking de bolsa",
        "fiis": "~20s — consulta e ranking de bolsa",
        "cripto": "~20s — consulta online",
        "rf": "~1s — indicadores e títulos atuais",
        "fundos": (
            "primeira execução pode levar vários minutos; "
            "as seguintes usam cache"
        ),
        "etf": "~5s — cotações de ETFs",
        "estruturados": "~15s — dados cadastrais e de balcão",
    }
    _sep()
    print("\n📈 Classes que serão consultadas:")
    for classe in sorted(classes):
        print(
            f"   • {rotulo_classe_ativo(classe):<35} "
            f"{estimativas.get(classe, 'tempo variável')}"
        )
    print("\n   Buscar ativos específicos agora? (sim | não)")
    confirmou = input("   → ").strip().casefold() in {
        "sim",
        "s",
        "yes",
        "y",
    }
    if not confirmou:
        return

    print("\n   🔍 Buscando e rankeando ativos...")
    ativos, indisponiveis = buscar_ativos_da_analise(analise)
    analise["ativos_sugeridos"] = ativos
    analise["classes_indisponiveis"] = indisponiveis

    for classe, lista in ativos.items():
        if not lista:
            continue
        _sep()
        print(
            f"\n📊 TOP {len(lista)} "
            f"{rotulo_classe_ativo(classe)}:"
        )
        for indice, ativo in enumerate(lista, 1):
            ticker = str(ativo.get("ticker", ""))
            nome = str(ativo.get("nome", ""))
            score = ativo.get("score")
            preco = ativo.get("preco")
            print(f"\n   {indice}. {ticker:<10} {nome}")
            if isinstance(score, (int, float)):
                print(f"      Score: {score:.2f}/100", end="")
            if isinstance(preco, (int, float)) and preco:
                print(f"   Preço: R$ {preco:,.2f}", end="")
            print()
            for motivo in ativo.get("motivos", []):
                print(f"      {motivo}")

    if indisponiveis:
        _sep()
        print("\n⚠️  Fontes indisponíveis:")
        for classe, motivo in indisponiveis.items():
            print(f"   • {rotulo_classe_ativo(classe)}: {motivo}")
        print(
            "\n   Carteira executável incompleta: nenhuma redistribuição "
            "automática foi feita. Mantenha em liquidez o percentual sem "
            "ativo selecionado e tente novamente mais tarde."
        )


def main() -> None:
    for sincronizacao in sincronizar_calendarios_relevantes():
        if sincronizacao.status not in {"atualizado", "sem_alteracao"}:
            logger.warning(
                "Calendário B3 %s: %s",
                sincronizacao.ano,
                sincronizacao.mensagem,
            )
    try:
        market = load_market_data()
        resumo_mercado = resumo_taxas_mercado(market)
    except DadosIndisponiveisError as exc:
        print("\n❌ Indicadores obrigatórios indisponíveis:")
        print(f"   {exc}")
        print("   Nenhuma taxa fixa foi inventada como substituição.")
        return
    except (KeyError, TypeError, ValueError) as exc:
        logger.error("Payload de mercado inválido: %s", exc)
        print("\n❌ Os dados de mercado retornaram em formato inválido.")
        return

    _imprimir_mercado(market, resumo_mercado)
    print("\nResponda ao questionário para gerar a análise.")
    _sep()

    primeira = _p_primeira(
        "1. Qual é seu prazo de investimento?\n"
        "   (curto = até 2 anos | médio = 2 a 5 | longo = acima de 5)",
        _PD,
    )
    respostas = _coletar_respostas(primeira)
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d_%H%M%S")
    salvar_perfil_respostas(respostas, timestamp)

    try:
        analise = criar_analise(
            respostas,
            market,
            data_referencia=dt.datetime.now(dt.timezone.utc).date(),
        )
    except DividaJurosAltosError as exc:
        _sep()
        print("\n🚨 DÍVIDAS DE JUROS ALTOS DETECTADAS")
        print(f"\n   {exc}")
        print("   Depois de quitar ou renegociar, refaça o questionário.")
        return
    except RecomendacaoBloqueadaError as exc:
        print("\n🚨 A análise foi interrompida por segurança:")
        print(f"   {exc}")
        return
    except (KeyError, TypeError, ValueError) as exc:
        logger.exception("Falha de consistência na análise")
        print(f"\n❌ Não foi possível gerar a análise: {exc}")
        return

    _imprimir_recomendacao(analise)
    _imprimir_projecoes(analise)
    _imprimir_meta(analise)
    _imprimir_perfil_e_avisos(analise)

    try:
        _consultar_e_imprimir_ativos(analise)
    except Exception as exc:
        logger.exception("Falha ao consultar ativos")
        print(f"\n⚠️  A busca de ativos falhou: {exc}")

    payload = montar_payload_exportacao(analise)
    nome = (
        "perfil_investimento_"
        f"{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    )
    caminho = _salvar_json(nome, payload)
    if caminho is not None:
        print(f"\n💾 Resultado salvo em: {caminho}")
    else:
        print("\n⚠️  Não foi possível salvar o resultado.")
    _sep()
    print()


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\n\nOperação cancelada pelo usuário.")
