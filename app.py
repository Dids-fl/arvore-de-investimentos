"""
Interface Streamlit do recomendador de investimentos.

Execute com:
    streamlit run app.py

Toda regra de recomendação, alocação, projeção, meta e busca de ativos é
orquestrada por engine.py. Este módulo contém apenas formulário, estado e
renderização.
"""

from __future__ import annotations

import datetime as dt
import json
import logging

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from calendarios.sincronizar_b3 import sincronizar_calendarios_relevantes
from decisao import analises as decisao_analises
from decisao import diario as decisao_diario
from decisao import historico as decisao_historico
from decisao.fgc import analisar_garantias
from engine import (
    DividaJurosAltosError,
    RecomendacaoBloqueadaError,
    buscar_ativos_da_analise,
    criar_analise,
    montar_payload_exportacao,
    nome_categoria,
    rotulo_classe_ativo,
)
from importacao.lotes_tributarios import (
    importar_lotes_tributarios,
    mesclar_metadados_tributarios,
)
from mercado import load_market_data
from utils.exceptions import DadosIndisponiveisError
from utils.logging_config import get_logger, setup_logging
from utils.formatacao import formatar_brl, formatar_pct



def _md(texto: str) -> str:
    """Escapa o cifrão: no Markdown do Streamlit, "R$ ... R$" vira fórmula."""
    return texto.replace("$", r"\$")


def _brl_md(valor) -> str:
    """Valor em reais para textos renderizados como Markdown."""
    return _md(formatar_brl(valor))


setup_logging(logging.INFO)
logger = get_logger(__name__)

st.set_page_config(
    page_title="Recomendador de Investimentos",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_data(ttl=3600, show_spinner=False)
def get_market_data() -> dict:
    """Cache da interface; mercado.py mantém também o cache persistente."""
    sincronizacoes = sincronizar_calendarios_relevantes()
    market = dict(load_market_data())
    market["_calendarios_b3"] = [
        resultado.como_dict() for resultado in sincronizacoes
    ]
    return market


def _market_signature(market: dict) -> tuple:
    """Identifica o conjunto de indicadores usado em uma análise."""
    return (
        market.get("selic"),
        market.get("focus_selic"),
        market.get("ipca"),
        market.get("ibov_cagr"),
        market.get("data_ref"),
        market.get("fetched_at"),
    )


def _render_sidebar(market: dict) -> None:
    with st.sidebar:
        st.header("📈 Dados de mercado")
        st.metric("SELIC", f"{formatar_pct(market['selic'])}")
        st.metric("IPCA 12 meses", f"{formatar_pct(market['ipca'])}")
        st.metric(
            "Ibovespa CAGR 10 anos",
            f"{formatar_pct(market['ibov_cagr'])}",
        )
        if market.get("focus_selic") is not None:
            st.metric(
                "Focus SELIC",
                f"{formatar_pct(market['focus_selic'])}",
            )
        if market.get("cdi") is not None:
            st.metric("CDI", f"{formatar_pct(market['cdi'])}")
        if market.get("poupanca") is not None:
            st.metric(
                "Poupança (anualizada)",
                f"{formatar_pct(market['poupanca'])}",
            )
        focus_ipca = market.get("focus_ipca_por_ano") or {}
        if focus_ipca:
            ano, taxa = next(iter(sorted(focus_ipca.items(), key=lambda i: int(i[0]))))
            st.metric(f"Focus IPCA {ano}", f"{formatar_pct(float(taxa))}")

        st.divider()
        if market.get("cache_status") == "stale":
            st.warning("Usando dados reais de cache por falha na atualização.")
        else:
            st.caption("Indicadores carregados das fontes online/cache recente.")

        for aviso in market.get("avisos", []):
            st.caption(aviso)

        sincronizacoes = market.get("_calendarios_b3", [])
        if sincronizacoes:
            with st.expander("Calendários B3"):
                for item in sincronizacoes:
                    simbolo = (
                        "✅"
                        if item["status"] in {"atualizado", "sem_alteracao"}
                        else "⚠️"
                    )
                    st.caption(
                        f"{simbolo} {item['ano']}: {item['mensagem']}"
                    )

        with st.expander("Fontes"):
            for fonte in market.get("fontes", []):
                st.write(f"• {fonte}")


def _render_questionario(market: dict) -> None:
    with st.form("form_questionario", clear_on_submit=False):
        st.subheader("📝 Perfil do investidor")
        st.caption(
            "Responda com sua situação real. Percentuais e meta só serão "
            "usados quando a opção correspondente estiver ativa."
        )

        col1, col2, col3 = st.columns(3)
        with col1:
            prazo = st.selectbox(
                "Prazo de investimento",
                ["curto", "médio", "longo"],
            )
            risco = st.selectbox(
                "Tolerância declarada a risco",
                ["baixo", "médio", "alto"],
            )
            objetivo = st.selectbox(
                "Objetivo principal",
                ["reserva", "crescimento", "aposentadoria"],
            )
            fluxo = st.selectbox(
                "Preferência de fluxo",
                ["renda", "acúmulo"],
            )
            controle = st.selectbox(
                "Gestão dos investimentos",
                ["gerir", "delegar"],
            )
            liquidez = st.selectbox(
                "Precisa de liquidez imediata?",
                ["sim", "não"],
            )
            liquidez_pct_informado = st.slider(
                "Percentual que precisaria resgatar",
                min_value=0,
                max_value=100,
                value=30,
                step=5,
                help="Ignorado quando a resposta de liquidez for 'não'.",
            )

        with col2:
            reserva = st.selectbox(
                "Reserva de emergência",
                ["não tenho", "parcial", "sim"],
            )
            idade = st.selectbox(
                "Faixa etária",
                ["jovem", "adulto", "sênior"],
            )
            despesas = st.selectbox(
                "Obrigações fixas mensais",
                ["nenhuma", "baixas", "altas"],
            )
            despesas_essenciais_mensais = st.number_input(
                "Despesas essenciais mensais (R$)",
                min_value=0.0,
                value=None,
                placeholder="Não informado",
                step=100.0,
                format="%.2f",
                help=(
                    "Inclua moradia, alimentação, saúde, transporte e "
                    "contas que continuariam existindo em uma emergência."
                ),
            )
            reserva_atual = st.number_input(
                "Reserva disponível hoje (R$)",
                min_value=0.0,
                value=None,
                placeholder="Não informado",
                step=500.0,
                format="%.2f",
                help=(
                    "Considere apenas dinheiro separado para emergências "
                    "com liquidez imediata."
                ),
            )
            valor = st.selectbox(
                "Valor disponível para investir",
                ["baixo", "médio", "alto"],
            )
            patrimonio = st.selectbox(
                "Parcela do patrimônio total",
                ["baixo", "médio", "alto"],
            )
            renda = st.selectbox(
                "Situação de renda",
                ["clt", "pj contratado", "autônomo", "sem renda"],
            )
            dividas = st.selectbox(
                "Dívidas ativas",
                ["juros altos", "juros baixos", "não tenho"],
            )

        with col3:
            conhecimento = st.selectbox(
                "Nível de conhecimento",
                ["iniciante", "intermediário", "experiente"],
            )
            experiencia = st.multiselect(
                "Produtos usados nos últimos dois anos",
                [
                    "poupança",
                    "tesouro",
                    "ações",
                    "fundos",
                    "opções",
                    "nenhum",
                ],
                default=["nenhum"],
            )
            dependentes = st.selectbox(
                "Pessoas que dependem de você",
                ["nenhum", "um", "dois ou mais"],
            )
            aporte = st.selectbox(
                "Tipo de aporte",
                ["único", "mensal"],
            )
            emocional = st.selectbox(
                "Reação a uma queda de 30%",
                ["venderia tudo", "esperaria recuperar", "compraria mais"],
            )
            ir_tipo = st.selectbox(
                "Declaração de IR",
                ["completo", "simplificado", "não declaro"],
            )
            carteira = st.selectbox(
                "Carteira atual",
                ["não tenho", "conservadora", "moderada", "arrojada"],
            )

        st.divider()
        st.subheader("💰 Capital e meta")
        modo_meta = st.selectbox(
            "O que deseja calcular?",
            ["sim", "rendendo", "não"],
            format_func=lambda valor_meta: {
                "sim": "Quero atingir um valor específico",
                "rendendo": "Quero ver como meu dinheiro pode crescer",
                "não": "Não quero projeção de meta",
            }[valor_meta],
        )

        fcol1, fcol2, fcol3, fcol4 = st.columns(4)
        with fcol1:
            cap_inicial = st.number_input(
                "Capital inicial (R$)",
                min_value=0.0,
                value=6_000.0,
                step=1_000.0,
                format="%.2f",
            )
        with fcol2:
            aporte_mensal_informado = st.number_input(
                "Aporte mensal (R$)",
                min_value=0.0,
                value=500.0,
                step=100.0,
                format="%.2f",
                help="Ignorado quando o tipo de aporte for 'único'.",
            )
        with fcol3:
            meta_valor_informado = st.number_input(
                "Valor-alvo (R$)",
                min_value=1.0,
                value=100_000.0,
                step=10_000.0,
                format="%.2f",
                help="Usado apenas para atingir um valor específico.",
            )
        with fcol4:
            meta_prazo_informado = st.number_input(
                "Prazo da meta (anos)",
                min_value=1,
                max_value=50,
                value=10,
                step=1,
            )

        st.divider()
        st.subheader("🧾 Premissas tributárias")
        st.caption(
            "Campos opcionais. Quando uma classe exigir um dado ausente, "
            "o valor líquido será marcado como indeterminado."
        )
        tcol1, tcol2, tcol3, tcol4 = st.columns(4)
        with tcol1:
            regime_previdencia_informado = st.selectbox(
                "Regime da previdência",
                ["não informado", "regressivo", "progressivo"],
            )
        with tcol2:
            renda_tributavel_anual_informada = st.number_input(
                "Renda tributável anual (R$)",
                min_value=0.0,
                value=0.0,
                step=5_000.0,
                format="%.2f",
                help=(
                    "Usada no regime progressivo e para estimar o benefício "
                    "fiscal do PGBL quando a elegibilidade for confirmada."
                ),
            )
        with tcol3:
            jurisdicao_cripto_informada = st.selectbox(
                "Custódia de cripto",
                ["não informado", "brasil", "exterior"],
            )
        with tcol4:
            pessoa_fisica = st.checkbox(
                "Investidor pessoa física",
                value=True,
                help="Afeta hipóteses de isenção de alguns produtos.",
            )

        pcol1, pcol2, pcol3 = st.columns(3)
        with pcol1:
            elegibilidade_pgbl_informada = st.selectbox(
                "Elegibilidade para dedução do PGBL",
                ["não informado", "sim", "não"],
                help=(
                    "Marque sim somente se usar deduções legais e cumprir "
                    "as condições da Receita, inclusive contribuição ao "
                    "RGPS/RPPS quando aplicável."
                ),
            )
        with pcol2:
            aportes_pgbl_ano_informados = st.number_input(
                "PGBL/FAPI já usado no limite deste ano (R$)",
                min_value=0.0,
                value=0.0,
                step=1_000.0,
                format="%.2f",
                help=(
                    "Reduz o espaço ainda disponível dentro do limite de "
                    "12% no primeiro ano da projeção."
                ),
            )
        with pcol3:
            crescimento_renda_pgbl_pct = st.number_input(
                "Crescimento anual da renda (%)",
                min_value=-99.0,
                max_value=100.0,
                value=0.0,
                step=0.5,
                format="%.2f",
                help=(
                    "Cenário para a renda tributável dos anos futuros. "
                    "Não representa previsão nem mudança da legislação."
                ),
            )

        metadados_fiscais_json = st.text_area(
            "Metadados fiscais avançados por categoria (JSON)",
            value="{}",
            height=100,
            help=(
                "Opcional: permite informar lotes previdenciários existentes, "
                "estado tributário de fundos, feriados adicionais e bases "
                "anuais. Use as chaves canônicas das categorias do catálogo."
            ),
        )
        arquivo_lotes = st.file_uploader(
            "Importar lotes históricos de fundos/previdência",
            type=["csv", "xlsx", "xlsm"],
            help=(
                "Use o modelo modelos/lotes_tributarios_exemplo.csv. O "
                "arquivo é validado e convertido para os metadados fiscais; "
                "nenhum valor digitado no JSON é sobrescrito."
            ),
        )

        submitted = st.form_submit_button(
            "Gerar recomendação",
            type="primary",
            width="stretch",
        )

    if not submitted:
        return

    try:
        metadados_fiscais = json.loads(metadados_fiscais_json or "{}")
    except json.JSONDecodeError as exc:
        st.error(f"JSON de metadados fiscais inválido: {exc}")
        return
    if not isinstance(metadados_fiscais, dict):
        st.error("Os metadados fiscais avançados devem formar um objeto JSON.")
        return

    if arquivo_lotes is not None:
        try:
            importacao = importar_lotes_tributarios(
                arquivo_lotes.getvalue(),
                nome_arquivo=arquivo_lotes.name,
                data_referencia=dt.datetime.now(dt.timezone.utc).date(),
            )
            metadados_fiscais = mesclar_metadados_tributarios(
                metadados_fiscais,
                importacao.metadados_por_categoria,
            )
        except (KeyError, TypeError, ValueError) as exc:
            st.error(f"Arquivo de lotes inválido: {exc}")
            return
        st.success(
            f"{importacao.quantidade_lotes} lote(s) importado(s), com saldo "
            f"total de {_brl_md(importacao.saldo_total)}."
        )
        st.dataframe(
            pd.DataFrame(importacao.resumo),
            hide_index=True,
            width="stretch",
        )
        for aviso_importacao in importacao.avisos:
            st.warning(aviso_importacao)

    respostas = {
        "prazo": prazo,
        "risco": risco,
        "objetivo": objetivo,
        "fluxo": fluxo,
        "controle": controle,
        "liquidez": liquidez,
        "liquidez_pct": float(liquidez_pct_informado),
        "reserva_emerg": reserva,
        "idade": idade,
        "despesas": despesas,
        "despesas_essenciais_mensais": (
            None
            if despesas_essenciais_mensais is None
            else float(despesas_essenciais_mensais)
        ),
        "reserva_atual": (
            None if reserva_atual is None else float(reserva_atual)
        ),
        "faixa_valor": valor,
        "patrim_pct": patrimonio,
        "renda": renda,
        "dividas": dividas,
        "conhecimento": conhecimento,
        "experiencia": experiencia,
        "dependentes": dependentes,
        "aporte": aporte,
        "emocional": emocional,
        "ir_tipo": ir_tipo,
        "carteira_atual": carteira,
        "modo_meta": modo_meta,
        "meta_valor": float(meta_valor_informado),
        "meta_prazo": float(meta_prazo_informado),
        "cap_inicial": float(cap_inicial),
        "aporte_mensal": float(aporte_mensal_informado),
        "regime_previdencia": regime_previdencia_informado,
        "renda_tributavel_anual": (
            float(renda_tributavel_anual_informada)
            if (
                regime_previdencia_informado == "progressivo"
                or elegibilidade_pgbl_informada == "sim"
            )
            else None
        ),
        "elegibilidade_deducao_pgbl": {
            "não informado": None,
            "sim": True,
            "não": False,
        }[elegibilidade_pgbl_informada],
        "valor_aportes_ano": float(aportes_pgbl_ano_informados),
        "crescimento_renda_tributavel_anual": (
            float(crescimento_renda_pgbl_pct) / 100.0
        ),
        "renda_tributavel_por_ano": {},
        "metadados_tributarios_por_categoria": metadados_fiscais,
        "jurisdicao_cripto": jurisdicao_cripto_informada,
        "pessoa_fisica": pessoa_fisica,
    }

    st.session_state.pop("analise_investimentos", None)
    try:
        with st.spinner("Calculando perfil, alocação e projeções..."):
            analise = criar_analise(
                respostas,
                market,
                data_referencia=dt.datetime.now(dt.timezone.utc).date(),
            )
    except DividaJurosAltosError as exc:
        st.error("🚨 Dívidas de juros altos detectadas")
        st.warning(str(exc))
        return
    except RecomendacaoBloqueadaError as exc:
        st.error("A análise foi interrompida por uma regra de segurança.")
        st.warning(str(exc))
        return
    except (KeyError, TypeError, ValueError) as exc:
        logger.exception("Erro de consistência ao gerar recomendação")
        st.error(f"Não foi possível montar a recomendação: {exc}")
        return
    except Exception as exc:
        logger.exception("Falha inesperada ao gerar recomendação")
        st.error(
            "Ocorreu uma falha inesperada ao gerar a recomendação. "
            f"Detalhe: {exc}"
        )
        return

    st.session_state["analise_investimentos"] = analise


def _render_metricas(analise: dict) -> None:
    resultado = analise["resultado"]
    cols = st.columns(4)
    cols[0].metric("Perfil", resultado["nivel_risco_display"])
    cols[1].metric(
        "Recomendação principal",
        resultado["recomendacao_display"],
    )
    cols[2].metric(
        "Taxa ponderada",
        f"{formatar_pct(resultado['taxa_perfil'])} a.a.",
    )
    cols[3].metric(
        "Classificação da carteira",
        resultado["risco_recomendado_display"],
    )

    if resultado["perfil_exibido"] != resultado["recomendacao_principal"]:
        st.caption(
            "Classe usada apenas para resumir o risco da carteira: "
            f"**{resultado['perfil_display']}**. A recomendação principal "
            "preserva a regra específica do questionário."
        )


def _render_recomendacao_principal(analise: dict) -> None:
    resultado = analise["resultado"]
    info = resultado["info_principal"]

    st.subheader("📋 Recomendação principal")
    st.markdown(f"### {resultado['recomendacao_display']}")
    cols = st.columns(3)
    cols[0].metric("Garantia", info.get("garantia", "Não informado"))
    cols[1].metric("Imposto", info.get("imposto", "Não informado"))
    cols[2].metric("Onde acessar", info.get("onde", "Não informado"))

    with st.expander("O que avaliar ou comprar nessa categoria"):
        itens = info.get("o_que_comprar", [])
        if itens:
            for item in itens:
                st.write(f"• {item}")
        else:
            st.info("O catálogo não possui itens para essa categoria.")

    ranking = resultado.get("ranking_previdencia_liquida")
    if isinstance(ranking, dict):
        if ranking.get("aplicado"):
            alternativas = ranking["alternativas"]
            pgbl = alternativas["pgbl"]
            vgbl = alternativas["vgbl"]
            st.caption(
                "Comparação previdenciária: "
                f"PGBL {formatar_pct(pgbl['tir_liquida_anual'])} a.a. líquido "
                f"versus VGBL {formatar_pct(vgbl['tir_liquida_anual'])} a.a. "
                "líquido. A adequação à aposentadoria foi mantida antes "
                "desta comparação."
            )
        elif ranking.get("motivo_escolha_conservadora"):
            st.caption(ranking["motivo_escolha_conservadora"])


def _render_alocacao(analise: dict) -> None:
    resultado = analise["resultado"]
    itens = resultado["portfolio_itens"]
    labels = [item["nome"] for item in itens]
    values = [item["percentual"] for item in itens]

    st.subheader("📊 Alocação sugerida")
    plano_reserva = resultado.get("plano_reserva")
    if isinstance(plano_reserva, dict):
        st.caption(
            "Reserva-alvo: "
            f"{_brl_md(plano_reserva['valor_alvo'])} · "
            f"Reserva atual: {_brl_md(plano_reserva['valor_atual'])} · "
            f"Déficit: {_brl_md(plano_reserva['deficit'])}"
        )
    col_chart, col_table = st.columns([1.25, 1])
    with col_chart:
        figure = go.Figure(
            data=[
                go.Pie(
                    labels=labels,
                    values=values,
                    hole=0.45,
                    textinfo="label+percent",
                    marker={"colors": px.colors.qualitative.Set3},
                    hovertemplate=(
                        "<b>%{label}</b><br>"
                        "Alocação: %{value:.1f}%<extra></extra>"
                    ),
                )
            ]
        )
        figure.update_layout(
            separators=",.",  # padrão brasileiro: 1.234,56
            height=420,
            margin={"t": 20, "b": 20, "l": 20, "r": 20},
            showlegend=False,
        )
        st.plotly_chart(figure, width="stretch")

    with col_table:
        tabela = pd.DataFrame(
            {"Classe": labels, "Alocação (%)": values}
        )
        st.dataframe(
            tabela,
            hide_index=True,
            width="stretch",
            column_config={
                "Alocação (%)": st.column_config.ProgressColumn(
                    "Alocação (%)",
                    min_value=0,
                    max_value=100,
                    format="%d%%",
                )
            },
        )
        st.caption(
            f"Taxa-base: {formatar_pct(resultado['taxa_base'])} a.a. · "
            f"Cenário pessimista: {formatar_pct(resultado['taxa_pess'])} a.a."
        )
        st.caption(
            "Todas as classes partem dos juros esperados pelo mercado (curva "
            "Selic/Focus): de 2004 a 2025, o Ibovespa rendeu em média perto do "
            "CDI, e essa regra foi a que menos errou na validação histórica. "
            "Mais ações significam mais risco, não retorno garantido maior; "
            "por isso o cenário pessimista fica mais baixo para carteiras "
            "com mais renda variável."
        )


_COLUNAS_EM_REAIS = {
    "Bruto sem tributação definida",
    "Carteira (líquido)",
    "Diferença",
    "Imposto estimado",
    "Imposto parcial calculado",
    "Líquido máximo",
    "Líquido mínimo",
    "Pessimista líquido",
    "Poder de compra",
    "Poupança",
    "Preço",
    "VF Bruto",
    "VF Líquido",
}


def _com_reais(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Mostra valores em reais no padrão brasileiro (R$ 1.234,56).

    O formato numérico do Streamlit segue o padrão americano; como estas
    tabelas são só de leitura, os valores são exibidos já formatados.
    """
    dataframe = dataframe.copy()
    for coluna in dataframe.columns:
        if coluna in _COLUNAS_EM_REAIS:
            dataframe[coluna] = dataframe[coluna].map(
                lambda valor: "—" if valor is None or valor != valor else formatar_brl(valor)
            )
    return dataframe


def _projecoes_dataframe(projecoes: list[dict]) -> pd.DataFrame:
    tem_faixa = any(linha.get("vf_liquido_min") is not None for linha in projecoes)
    linhas = []
    for linha in projecoes:
        item = {
            "Anos": linha["anos"],
            "VF Bruto": linha["vf_bruto"],
            "Imposto estimado": linha["imposto_estimado"],
            "VF Líquido": linha["vf_liquido"],
        }
        if tem_faixa:
            item["Líquido mínimo"] = linha.get("vf_liquido_min")
            item["Líquido máximo"] = linha.get("vf_liquido_max")
        item.update(
            {
                "Poder de compra": linha["vf_real"],
                # Sem dado fiscal, o pessimista usa o pior cenário fiscal.
                "Pessimista líquido": (
                    linha["vf_pessimista_liquido"]
                    if linha["vf_pessimista_liquido"] is not None
                    else linha.get("vf_pessimista_liquido_min")
                ),
                "Precisão tributária": linha["precisao_tributaria"],
            }
        )
        linhas.append(item)
    dataframe = pd.DataFrame(linhas)
    if tem_faixa and dataframe["VF Líquido"].isna().all():
        dataframe = dataframe.drop(columns=["VF Líquido", "Imposto estimado"])
    return dataframe


def _faixa_ipca(projecoes: list[dict], market: dict) -> str:
    valores = [linha["ipca_horizonte"] for linha in projecoes if linha.get("ipca_horizonte") is not None]
    if not valores:
        return f"{formatar_pct(market['ipca'])} a.a. (últimos 12 meses)"
    menor, maior = min(valores), max(valores)
    if round(menor, 4) == round(maior, 4):
        return f"{formatar_pct(menor)} a.a."
    return f"{formatar_pct(menor)} a {formatar_pct(maior)} a.a., conforme o prazo"


def _render_projecoes(analise: dict) -> None:
    respostas = analise["respostas"]
    resultado = analise["resultado"]
    market = analise["market"]

    st.subheader("📈 Projeção de crescimento")
    st.caption(
        f"Capital inicial: **{_brl_md(respostas['cap_inicial'])}** · "
        f"Aporte mensal: **{_brl_md(respostas['aporte_mensal'])}** · "
        f"Taxa ponderada bruta: "
        f"**{formatar_pct(resultado['taxa_perfil'])} a.a.** · "
        f"IPCA esperado (Focus): **{_faixa_ipca(analise['projecoes'], market)}**"
    )

    st.dataframe(
        _com_reais(_projecoes_dataframe(analise["projecoes"])),
        hide_index=True,
        width="stretch",
        column_config={
            "Anos": st.column_config.NumberColumn("Anos", format="%d"),
            "VF Bruto": st.column_config.TextColumn("VF Bruto"),
            "Imposto estimado": st.column_config.TextColumn("Imposto estimado"),
            "VF Líquido": st.column_config.TextColumn("VF Líquido"),
            "Poder de compra": st.column_config.TextColumn("Poder de compra"),
            "Pessimista líquido": st.column_config.TextColumn("Pessimista líquido"),
            "Líquido mínimo": st.column_config.TextColumn("Líquido mínimo"),
            "Líquido máximo": st.column_config.TextColumn("Líquido máximo"),
        },
    )

    comparativo = analise.get("comparativo_poupanca")
    if comparativo:
        taxa_poupanca = market.get("poupanca")
        st.markdown(
            f"**Comparativo com a poupança** "
            f"({formatar_pct(taxa_poupanca)} a.a., isenta de IR — BCB/SGS 195)"
        )
        st.dataframe(
            _com_reais(pd.DataFrame(
                [
                    {
                        "Anos": linha["anos"],
                        "Carteira (líquido)": linha["vf_liquido_carteira"],
                        "Poupança": linha["valor_poupanca"],
                        "Diferença": linha["diferenca"],
                    }
                    for linha in comparativo
                ]
            )),
            hide_index=True,
            width="stretch",
            column_config={
                "Anos": st.column_config.NumberColumn("Anos", format="%d"),
                "Carteira (líquido)": st.column_config.TextColumn("Carteira (líquido)"),
                "Poupança": st.column_config.TextColumn("Poupança"),
                "Diferença": st.column_config.TextColumn("Diferença"),
            },
        )
        st.caption(
            "A taxa da poupança muda com a Selic; o comparativo a mantém "
            "constante como hipótese, assim como as demais projeções."
        )

    if any(
        linha["vf_liquido"] is None
        for linha in analise["projecoes"]
    ):
        variaveis = next(
            (linha["faixa_variaveis"] for linha in analise["projecoes"] if linha.get("faixa_variaveis")),
            [],
        )
        if variaveis:
            st.info(
                "Faltam dados fiscais (" + ", ".join(variaveis) + "). Em vez de "
                "uma alíquota genérica, o líquido aparece como faixa entre o pior "
                "e o melhor cenário possível. Preencha as premissas tributárias "
                "para obter um valor único."
            )
        else:
            st.warning(
                "Há tributação indeterminada. As células líquidas vazias não "
                "foram preenchidas com uma alíquota genérica."
            )

    serie = analise["serie_projecao"]
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=[linha["anos"] for linha in serie],
            y=[linha["vf_bruto"] for linha in serie],
            mode="lines",
            name="Bruto",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=[linha["anos"] for linha in serie],
            y=[linha["vf_liquido"] for linha in serie],
            mode="lines",
            name="Líquido",
        )
    )
    if any(linha.get("vf_liquido_min") is not None for linha in serie):
        figure.add_trace(
            go.Scatter(
                x=[linha["anos"] for linha in serie],
                y=[linha.get("vf_liquido_max") for linha in serie],
                mode="lines",
                line={"width": 0},
                name="Líquido (melhor cenário fiscal)",
                showlegend=False,
            )
        )
        figure.add_trace(
            go.Scatter(
                x=[linha["anos"] for linha in serie],
                y=[linha.get("vf_liquido_min") for linha in serie],
                mode="lines",
                line={"width": 0},
                fill="tonexty",
                name="Líquido (faixa entre cenários fiscais)",
            )
        )
    figure.add_trace(
        go.Scatter(
            x=[linha["anos"] for linha in serie],
            y=[linha["vf_real"] for linha in serie],
            mode="lines",
            name="Poder de compra",
        )
    )
    figure.update_layout(
        separators=",.",  # padrão brasileiro: 1.234,56
        title="Evolução estimada do patrimônio",
        xaxis_title="Anos",
        yaxis_title="Valor (R$)",
        hovermode="x unified",
        height=430,
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "right",
            "x": 1,
        },
    )
    st.plotly_chart(figure, width="stretch")


def _render_tributacao(analise: dict) -> None:
    projecoes = analise["projecoes"]
    if not projecoes:
        return

    st.subheader("🧾 Tributação das projeções")
    resumo = pd.DataFrame(
        [
            {
                "Anos": linha["anos"],
                "Imposto estimado": linha["imposto_estimado"],
                "Imposto parcial calculado": linha[
                    "imposto_calculado_parcial"
                ],
                "Bruto sem tributação definida": linha[
                    "bruto_indeterminado"
                ],
                "Precisão": linha["precisao_tributaria"],
            }
            for linha in projecoes
        ]
    )
    st.dataframe(
        _com_reais(resumo),
        hide_index=True,
        width="stretch",
        column_config={
            "Anos": st.column_config.NumberColumn("Anos", format="%d"),
            "Imposto estimado": st.column_config.TextColumn("Imposto estimado"),
            "Imposto parcial calculado": st.column_config.TextColumn("Imposto parcial calculado"),
            "Bruto sem tributação definida": st.column_config.TextColumn("Bruto sem tributação definida"),
        },
    )

    horizonte = max(projecoes, key=lambda linha: float(linha["anos"]))
    with st.expander(
        f"Premissas por classe — horizonte de {horizonte['anos']:g} ano(s)"
    ):
        for detalhe in horizonte["tributacao_por_classe"].values():
            imposto = detalhe["imposto_estimado"]
            imposto_texto = (
                f"{_brl_md(imposto)}"
                if isinstance(imposto, (int, float))
                else "indeterminado"
            )
            st.markdown(
                f"**{detalhe['nome']}** · "
                f"`{detalhe['tipo_produto']}` · "
                f"{detalhe['precisao']} · imposto {imposto_texto}"
            )
            metodo = detalhe.get("metodo_tributacao")
            if metodo == "come_cotas_prospectivo_por_lote":
                st.caption(
                    "Come-cotas futuro: "
                    f"{detalhe['eventos_come_cotas']} evento(s), "
                    f"{_brl_md(detalhe['come_cotas_estimado'])} antecipados e "
                    "sem reconstrução de histórico anterior."
                )
            elif (
                metodo == "lotes_individuais"
                and detalhe["tipo_produto"] in {"pgbl", "vgbl"}
            ):
                st.caption(
                    f"Previdência calculada em {detalhe['quantidade_lotes']} "
                    "lote(s), conforme a idade de cada aporte."
                )
            for premissa in detalhe["premissas"]:
                st.caption(f"• {premissa}")

    st.caption(
        f"Data de referência dos cálculos: {analise['data_referencia']}. "
        "As regras podem mudar antes dos resgates projetados."
    )


def _render_meta(analise: dict) -> None:
    meta = analise.get("meta")
    if meta is None:
        return

    st.subheader("🎯 Análise da meta")
    if meta["valor_liquido_projetado"] is None:
        if meta.get("valor_liquido_min") is not None:
            cols = st.columns(2)
            cols[0].metric("Valor-alvo nominal", formatar_brl(meta["valor_alvo"]))
            cols[1].metric(
                f"Projeção em {meta['prazo_anos']:g} ano(s)",
                f"{formatar_brl(meta['valor_liquido_min'])} a "
                f"{formatar_brl(meta['valor_liquido_max'])}",
            )
            veredito = {
                "todos": (st.success, "A meta é atingida em todos os cenários fiscais."),
                "nenhum": (st.warning, "A meta não é atingida em nenhum cenário fiscal."),
                "depende": (
                    st.info,
                    "A meta depende dos dados fiscais: é atingida em alguns cenários.",
                ),
            }.get(meta.get("atingida_cenarios"))
            if veredito:
                veredito[0](veredito[1])
        else:
            st.warning(meta["motivo_indeterminacao"])
        st.caption(
            meta["motivo_indeterminacao"]
            + " Preencha as premissas fiscais para obter um valor único."
        )
        return

    cols = st.columns(3)
    cols[0].metric(
        "Valor-alvo nominal",
        f"{formatar_brl(meta['valor_alvo'])}",
    )
    cols[1].metric(
        f"Projeção em {meta['prazo_anos']:g} ano(s)",
        f"{formatar_brl(meta['valor_liquido_projetado'])}",
    )
    cols[2].metric(
        "Diferença",
        f"{formatar_brl(meta['diferenca'])}",
        delta=f"{formatar_brl(meta['diferenca'])}",
        delta_color="normal",
    )

    if meta["atingida"]:
        st.success(
            "A meta é atingível no cenário central, com margem nominal de "
            f"{_brl_md(meta['diferenca'])}."
        )
    else:
        mensagem = (
            "Faltariam aproximadamente "
            f"{_brl_md(abs(meta['diferenca']))} no cenário central."
        )
        if meta["aporte_mensal_estimado"] is not None:
            mensagem += (
                " O aporte mensal total estimado para atingir a meta é "
                f"{_brl_md(meta['aporte_mensal_estimado'])}."
            )
        st.warning(mensagem)


# ── Decisões grandes ──────────────────────────────────────────────────────────

VALOR_EXEMPLO = 100_000.0


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def _indices_historicos() -> pd.DataFrame:
    return decisao_historico.carregar_indices()


def _horizonte_anos(analise: dict) -> float:
    meta = analise.get("meta")
    if isinstance(meta, dict) and meta.get("prazo_anos") is not None:
        return float(meta["prazo_anos"])
    return float(analise["resultado"]["prazo_taxa_meses"]) / 12.0


def _render_crises(carteira: dict, valor: float, indices: pd.DataFrame) -> None:
    usa_cripto = any(
        "btc" in decisao_historico.PROXY_CATEGORIA.get(categoria, {}) for categoria in carteira
    )
    if usa_cripto and indices["btc"].notna().sum() < 24:
        st.warning(
            "A base não tem histórico de bitcoin, então a parte em cripto foi simulada "
            "como Ibovespa. Isso subestima o risco: o bitcoin já caiu mais de 70% "
            "em mais de uma ocasião."
        )
    resultado = decisao_analises.teste_crises(carteira, valor, indices)
    pior = resultado["pior_queda"]
    if pior["perda"] >= 0:
        st.success(
            "Nas crises desde 2000, esta carteira não teve um único mês abaixo do "
            "valor investido: ela é toda de renda fixa pós-fixada."
        )
    else:
        st.metric(
            f"Pior queda do histórico ({pior['pico']} a {pior['fundo']})",
            formatar_brl(pior["perda_reais"]),
            delta=formatar_pct(pior["perda"]),
            delta_color="inverse",
        )
        st.caption(
            "Depois do fundo, levou "
            f"{decisao_analises.meses_por_extenso(pior['meses_para_recuperar'])} "
            "para voltar ao valor anterior."
        )
    linhas = [
        {
            "Crise": c["crise"],
            "Período": f"{c['inicio']} a {c['fim']}",
            "Pior momento": formatar_pct(c["perda_maxima"]),
            "Em reais": formatar_brl(c["perda_maxima_reais"]),
            "Tempo para voltar ao valor inicial": decisao_analises.meses_por_extenso(
                c["meses_para_recuperar"]
            ),
            "Carteira no fim do período": formatar_pct(c["carteira_no_fim"]),
            "CDI no período": formatar_pct(c["cdi_no_fim"]),
        }
        for c in resultado["crises"]
    ]
    st.dataframe(pd.DataFrame(linhas), hide_index=True, width="stretch")
    st.caption(
        "Simulação mensal com índices de cada classe (CDI, Tesouro IPCA+, Ibovespa, "
        "FIIs, dólar), carteira rebalanceada todo mês. Quedas dentro de um mês "
        "não aparecem inteiras: no pior dia da Covid a bolsa chegou a cair mais "
        "do que o fechamento mensal mostra. Fundos multimercado e previdência são "
        "aproximados por 70% CDI, 15% IPCA+ e 15% Ibovespa; classes sem dado na "
        "época (FIIs antes de 2020, bitcoin) usam substitutos de risco parecido."
    )


def _render_faixas(
    carteira: dict, valor: float, prazo: float, cdi_esperado: float, indices: pd.DataFrame
) -> None:
    faixas = decisao_analises.faixas_retorno(carteira, prazo, cdi_esperado, indices, valor)
    anos = faixas["anos"]
    st.markdown(
        f"Retorno por ano em **{anos} ano(s)**, partindo do CDI esperado hoje "
        f"({formatar_pct(cdi_esperado)} a.a.) e da variação que esta carteira teve "
        "em relação ao CDI em todas as janelas de mesmo prazo desde 2000."
    )
    linhas = [
        {
            "Certeza": nome,
            "Retorno por ano": f"{formatar_pct(f['minimo'])} a {formatar_pct(f['maximo'])}",
            f"Valor em {anos} ano(s)": (
                f"{formatar_brl(f['valor_minimo'])} a {formatar_brl(f['valor_maximo'])}"
            ),
        }
        for nome, f in faixas["faixas"].items()
    ]
    st.dataframe(pd.DataFrame(linhas), hide_index=True, width="stretch")
    cols = st.columns(3)
    cols[0].metric("Mediana", f"{formatar_pct(faixas['mediana'])} a.a.")
    cols[1].metric(
        "Vezes que perdeu dinheiro no prazo", formatar_pct(faixas["chance_perder_dinheiro"], 0)
    )
    cols[2].metric("Vezes que rendeu menos que o CDI", formatar_pct(faixas["chance_abaixo_do_cdi"], 0))
    observacoes = [
        "Inclui o erro da própria previsão do CDI, medido na validação histórica.",
        f"Há {faixas['janelas']} janelas sobrepostas, mas só "
        f"{faixas['janelas_independentes']} períodos de {anos} ano(s) sem sobreposição: "
        "quanto maior o prazo, menos histórico independente existe.",
    ]
    if faixas["prazo_limitado"]:
        observacoes.append(
            f"Seu prazo ({prazo:g} anos) passa de {decisao_analises.PRAZO_MAXIMO_FAIXA} anos; "
            "não há histórico suficiente além disso, então a faixa mostrada é a de 10 anos."
        )
    st.caption(" ".join(observacoes))


def _render_garantias(carteira: dict, valor: float, taxa: float, prazo: float) -> None:
    # O FGC cobre o saldo na data da quebra; CDBs longos costumam ter até 5 anos.
    rendimento = (1 + taxa) ** min(max(prazo, 1), 5) - 1
    resultado = analisar_garantias(carteira, valor, rendimento_ate_vencimento=rendimento)
    grupos = resultado["grupos"]
    nomes = {
        "fgc_ou_tesouro": "Tesouro Direto ou CDB/LCI/LCA (FGC)",
        "tesouro": "Somente Tesouro Direto",
        "fundos": "Fundos e previdência (patrimônio separado, sem FGC)",
        "sem_garantia": "Sem garantia (ações, FIIs, cripto, COE, crédito privado)",
    }
    st.dataframe(
        pd.DataFrame(
            [
                {"Tipo de garantia": nomes[k], "Valor": formatar_brl(v)}
                for k, v in grupos.items()
                if v > 0
            ]
        ),
        hide_index=True,
        width="stretch",
    )
    for alerta in resultado["alertas"]:
        st.warning(_md(alerta))
    if not resultado["alertas"]:
        st.success("Os valores cabem nos limites de garantia sem precisar dividir.")
    st.caption(
        "FGC: até R\\$ 250 mil por CPF em cada instituição ou conglomerado (juros "
        "incluídos) e teto de R\\$ 1 milhão a cada 4 anos. O cálculo inclui os "
        f"juros de até 5 anos ({_brl_md(resultado['valor_bancario_no_vencimento'])} na "
        "parte bancária); reavalie a divisão quando o saldo crescer. Bancos do mesmo "
        "grupo contam como um só."
    )


def _render_custo_saida(carteira: dict, valor: float, taxa: float, indices: pd.DataFrame) -> None:
    linhas = decisao_analises.custo_de_sair(carteira, valor, taxa, indices)
    tabela = []
    for linha in linhas:
        registro = {
            "Classe": nome_categoria(linha["categoria"]),
            "Aplicado": formatar_brl(linha["valor"]),
        }
        for h in linha["horizontes"]:
            rotulo = f"{h['meses']} meses"
            registro[f"Resgate em {rotulo}"] = formatar_brl(h["liquido_central"])
            registro[f"Pior caso em {rotulo}"] = formatar_brl(h["liquido_pior_caso"])
        tabela.append(registro)
    st.dataframe(pd.DataFrame(tabela), hide_index=True, width="stretch")
    with st.expander("Como e quando dá para resgatar cada classe"):
        for linha in linhas:
            st.write(f"• **{nome_categoria(linha['categoria'])}:** {linha['liquidez']}")
    st.caption(
        "Valores líquidos de IR. \"Resgate\" usa a taxa esperada da carteira; "
        "\"pior caso\" aplica a ela o resultado das 5% piores janelas históricas "
        "daquela classe contra o CDI, no mesmo prazo. Renda fixa e fundos seguem a tabela regressiva (6 meses já passam "
        "de 180 dias, então pagam 20%); ações e ETFs 15% e FIIs 20% sobre o ganho, "
        "sem considerar a isenção de vendas de até R\\$ 20 mil por mês em ações. "
        "Previdência no regime regressivo: 35% antes de 2 anos e, no PGBL, sobre "
        "todo o valor resgatado. Sair cedo de previdência quase sempre é caro."
    )


def _render_entrada(carteira: dict, valor: float, indices: pd.DataFrame) -> None:
    resultado = decisao_analises.entrada_parcelada(carteira, valor, indices)
    if not resultado["faz_diferenca"]:
        st.info(
            "Para esta carteira, parcelar a entrada não muda quase nada: ela é "
            "praticamente toda pós-fixada. Pode investir de uma vez."
        )
        return
    meses = resultado["horizonte_meses"]
    linhas = [
        {
            "Estratégia": e["nome"],
            f"Valor típico em {meses} meses": formatar_brl(e["mediana"]),
            "Pior caso": formatar_brl(e["pior_caso"]),
            "5% piores": formatar_brl(e["pior_5pct"]),
            "Melhor caso": formatar_brl(e["melhor_caso"]),
            "Superou investir de uma vez": (
                "—" if e["venceu_de_uma_vez"] is None else formatar_pct(e["venceu_de_uma_vez"], 0)
            ),
        }
        for e in resultado["estrategias"]
    ]
    st.dataframe(pd.DataFrame(linhas), hide_index=True, width="stretch")
    st.caption(
        f"Testado em {resultado['datas_testadas']} datas de início desde 2000. Enquanto "
        "não entra na carteira, o dinheiro rende CDI. Parcelar não aumenta o "
        "retorno esperado; o que ele faz é reduzir o arrependimento de entrar "
        "tudo logo antes de uma queda. Se uma queda forte faria você desistir, "
        "parcelar em 6 a 12 meses é a opção mais segura."
    )


def _render_historico(analise: dict, indices: pd.DataFrame) -> None:
    observacao = st.text_input(
        "Anotação (opcional)",
        key="decisao_observacao",
        placeholder="Ex.: investi R$ 200 mil no banco X",
    )
    if st.button("Salvar esta análise no meu histórico", key="decisao_salvar"):
        try:
            decisao_diario.salvar(decisao_diario.registro_da_analise(analise, observacao))
            st.success("Análise salva. Ela aparece abaixo e fica só neste computador.")
        except OSError as exc:
            st.error(f"Não foi possível salvar o histórico: {exc}")
    registros = decisao_diario.listar()
    if not registros:
        st.caption(
            "Nenhuma análise salva ainda. Salve as decisões que você realmente "
            "tomar; daqui a alguns meses o app compara o previsto com o que "
            "aconteceu."
        )
        return
    for registro in registros:
        avaliacao = decisao_diario.avaliar(registro, indices)
        titulo = (
            f"{registro['data']} · {registro.get('perfil') or ''} · "
            f"{_brl_md(registro.get('valor') or 0)}"
        )
        if registro.get("observacao"):
            titulo += f" · {registro['observacao']}"
        with st.expander(titulo):
            st.write(
                "Carteira: "
                + ", ".join(
                    f"{nome_categoria(k)} {v:.0f}%".replace(".", ",")
                    for k, v in registro["carteira"].items()
                )
            )
            if avaliacao["meses"] == 0:
                st.caption("Ainda não passou um mês completo para comparar.")
            else:
                cols = st.columns(4)
                cols[0].metric(
                    f"Rendeu ({avaliacao['meses']} meses, até {avaliacao['ate']})",
                    formatar_pct(avaliacao["realizado"]),
                )
                cols[1].metric("Previsto", formatar_pct(avaliacao["previsto"]))
                cols[2].metric("Pessimista", formatar_pct(avaliacao["pessimista"]))
                cols[3].metric("CDI", formatar_pct(avaliacao["cdi"]))
                st.write(f"Resultado: **{avaliacao['situacao']}**.")
                st.caption(
                    "Aproximação pelos índices de cada classe, não pelos seus "
                    "ativos reais, e sem IR."
                )
            if st.button("Apagar", key=f"decisao_apagar_{registro['id']}"):
                decisao_diario.remover(registro["id"])
                st.rerun()


def _render_decisao(analise: dict) -> None:
    resultado = analise["resultado"]
    carteira = {k: float(v) for k, v in resultado["portfolio"].items() if float(v) > 0}
    if not carteira:
        return
    st.subheader("🛡️ Antes de uma decisão grande")
    valor = float(analise["respostas"].get("cap_inicial") or 0)
    if valor <= 0:
        valor = VALOR_EXEMPLO
        st.caption(f"Sem capital inicial informado: os valores usam {_brl_md(valor)} como exemplo.")
    try:
        indices = _indices_historicos()
    except Exception as exc:  # noqa: BLE001 — base embarcada ilegível
        logger.exception("Base histórica indisponível")
        st.warning(f"Histórico das classes indisponível: {exc}")
        return
    prazo = _horizonte_anos(analise)
    abas = st.tabs(
        [
            "Teste de crise",
            "Faixas por prazo",
            "Garantias (FGC)",
            "Custo de sair antes",
            "Entrada parcelada",
            "Meu histórico",
        ]
    )
    with abas[0]:
        _render_crises(carteira, valor, indices)
    with abas[1]:
        _render_faixas(carteira, valor, prazo, float(resultado["taxa_base"]), indices)
    with abas[2]:
        _render_garantias(carteira, valor, float(resultado["taxa_perfil"]), prazo)
    with abas[3]:
        _render_custo_saida(carteira, valor, float(resultado["taxa_perfil"]), indices)
    with abas[4]:
        _render_entrada(carteira, valor, indices)
    with abas[5]:
        _render_historico(analise, indices)


def _render_ativos(analise: dict) -> None:
    resultado = analise["resultado"]
    classes = resultado["classes_no_portfolio"]

    st.subheader("🔎 Ativos específicos")
    if not classes:
        st.info("A carteira não contém classes com ranking implementado.")
        return

    nomes = [
        resultado["classes_display"].get(
            classe,
            rotulo_classe_ativo(classe),
        )
        for classe in sorted(classes)
    ]
    st.caption(
        "Classes disponíveis: "
        + ", ".join(nomes)
        + ". A consulta só ocorre ao clicar no botão."
    )

    if st.button(
        "Buscar e rankear ativos agora",
        type="secondary",
        width="stretch",
    ):
        try:
            with st.spinner(
                "Consultando fontes externas e calculando os rankings..."
            ):
                ativos, indisponiveis = buscar_ativos_da_analise(analise)
            analise["ativos_sugeridos"] = ativos
            analise["classes_indisponiveis"] = indisponiveis
            st.session_state["analise_investimentos"] = analise
        except Exception as exc:
            logger.exception("Erro inesperado na busca de ativos")
            st.error(f"Não foi possível concluir a busca de ativos: {exc}")

    ativos = analise.get("ativos_sugeridos", {})
    indisponiveis = analise.get("classes_indisponiveis", {})
    if indisponiveis:
        st.warning("Algumas fontes não puderam ser consultadas:")
        for classe, motivo in indisponiveis.items():
            st.caption(f"• **{rotulo_classe_ativo(classe)}**: {motivo}")
        st.warning(
            "A carteira executável está incompleta. Nenhum percentual foi "
            "redistribuído automaticamente; mantenha a parcela sem ativo "
            "selecionado em liquidez e tente novamente mais tarde."
        )

    if not ativos:
        return

    tabs = st.tabs(
        [rotulo_classe_ativo(classe) for classe in ativos]
    )
    for tab, (classe, lista) in zip(tabs, ativos.items()):
        with tab:
            if not lista:
                st.info("Nenhum ativo passou pelos filtros dessa classe.")
                continue

            tabela = pd.DataFrame(lista)
            if "motivos" in tabela.columns:
                tabela["motivos"] = tabela["motivos"].apply(
                    lambda motivos: (
                        " | ".join(motivos)
                        if isinstance(motivos, list)
                        else str(motivos or "")
                    )
                )
            for coluna in ("score", "preco"):
                if coluna in tabela.columns:
                    tabela[coluna] = pd.to_numeric(
                        tabela[coluna],
                        errors="coerce",
                    )
            if "score" in tabela.columns:
                tabela["score"] = tabela["score"].round(2)

            renomear = {
                "ticker": "Ticker",
                "nome": "Nome",
                "preco": "Preço",
                "score": "Score (/100)",
                "motivos": "Destaques",
            }
            tabela = tabela.rename(
                columns={
                    antiga: nova
                    for antiga, nova in renomear.items()
                    if antiga in tabela.columns
                }
            )
            preferidas = [
                "Ticker",
                "Nome",
                "Preço",
                "Score (/100)",
                "Destaques",
            ]
            colunas = [
                coluna
                for coluna in preferidas
                if coluna in tabela.columns
            ]
            colunas.extend(
                coluna
                for coluna in tabela.columns
                if coluna not in colunas
            )
            st.dataframe(
                _com_reais(tabela[colunas]),
                hide_index=True,
                width="stretch",
                column_config={
                    "Preço": st.column_config.TextColumn("Preço"),
                    "Score": st.column_config.NumberColumn(
                        "Score",
                        format="%.2f",
                    ),
                },
            )


def _render_avisos_e_perfil(analise: dict) -> None:
    resultado = analise["resultado"]
    if resultado["avisos"]:
        st.subheader("⚠️ Observações e ajustes")
        for aviso in resultado["avisos"]:
            if "🚨" in aviso or "⚠️" in aviso:
                st.warning(aviso)
            else:
                st.info(aviso)

    with st.expander("Respostas e classificação"):
        st.dataframe(
            pd.DataFrame(
                resultado["perfil_resumo"].items(),
                columns=["Critério", "Resultado"],
            ),
            hide_index=True,
            width="stretch",
        )


def _render_exportacao(analise: dict) -> None:
    payload = montar_payload_exportacao(analise)
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d_%H%M%S")
    st.download_button(
        "Baixar análise completa em JSON",
        data=json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        file_name=f"recomendacao_{timestamp}.json",
        mime="application/json",
        width="stretch",
    )


def _render_resultado(analise: dict) -> None:
    st.success("Recomendação calculada.")
    _render_metricas(analise)
    st.divider()
    _render_recomendacao_principal(analise)
    st.divider()
    _render_alocacao(analise)
    st.divider()
    _render_projecoes(analise)
    _render_tributacao(analise)
    _render_meta(analise)
    st.divider()
    _render_decisao(analise)
    st.divider()
    _render_ativos(analise)
    st.divider()
    _render_avisos_e_perfil(analise)
    st.divider()
    _render_exportacao(analise)


def main() -> None:
    st.title("📊 Recomendador de Investimentos")
    st.markdown(
        "Perfil, alocação, projeções e ranking de ativos para o mercado "
        "brasileiro."
    )
    st.warning(
        "Ferramenta educacional. As projeções dependem de hipóteses e não "
        "constituem garantia de retorno nem recomendação profissional."
    )

    try:
        with st.spinner("Carregando indicadores de mercado..."):
            market = get_market_data()
    except DadosIndisponiveisError as exc:
        st.error(
            "Não foi possível obter os indicadores obrigatórios. "
            f"Detalhe: {exc}"
        )
        st.info(
            "O sistema não substitui dados ausentes por taxas fixas "
            "inventadas. Tente novamente mais tarde."
        )
        st.stop()
    except Exception as exc:
        logger.exception("Falha inesperada ao carregar mercado")
        st.error(f"Falha inesperada ao carregar dados de mercado: {exc}")
        st.stop()

    analise_anterior = st.session_state.get("analise_investimentos")
    if (
        analise_anterior is not None
        and (
            _market_signature(analise_anterior.get("market", {}))
            != _market_signature(market)
            or analise_anterior.get("data_referencia")
            != dt.datetime.now(dt.timezone.utc).date().isoformat()
        )
    ):
        st.session_state.pop("analise_investimentos", None)
        st.info(
            "Os indicadores ou a data de referência foram atualizados. "
            "Gere uma nova recomendação para manter os cálculos consistentes."
        )

    _render_sidebar(market)
    _render_questionario(market)

    analise = st.session_state.get("analise_investimentos")
    if analise is not None:
        st.divider()
        _render_resultado(analise)


if __name__ == "__main__":
    main()
