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
from engine import (
    DividaJurosAltosError,
    RecomendacaoBloqueadaError,
    buscar_ativos_da_analise,
    criar_analise,
    montar_payload_exportacao,
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
            f"total de {formatar_brl(importacao.saldo_total)}."
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
            f"{formatar_brl(plano_reserva['valor_alvo'])} · "
            f"Reserva atual: {formatar_brl(plano_reserva['valor_atual'])} · "
            f"Déficit: {formatar_brl(plano_reserva['deficit'])}"
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
                "Pessimista líquido": linha["vf_pessimista_liquido"],
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
        f"Capital inicial: **{formatar_brl(respostas['cap_inicial'])}** · "
        f"Aporte mensal: **{formatar_brl(respostas['aporte_mensal'])}** · "
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
                f"{formatar_brl(imposto)}"
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
                    f"{formatar_brl(detalhe['come_cotas_estimado'])} antecipados e "
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
            f"{formatar_brl(meta['diferenca'])}."
        )
    else:
        mensagem = (
            "Faltariam aproximadamente "
            f"{formatar_brl(abs(meta['diferenca']))} no cenário central."
        )
        if meta["aporte_mensal_estimado"] is not None:
            mensagem += (
                " O aporte mensal total estimado para atingir a meta é "
                f"{formatar_brl(meta['aporte_mensal_estimado'])}."
            )
        st.warning(mensagem)


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
