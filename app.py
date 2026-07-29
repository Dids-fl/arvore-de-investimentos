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

from engine import (
    DividaJurosAltosError,
    RecomendacaoBloqueadaError,
    buscar_ativos_da_analise,
    criar_analise,
    montar_payload_exportacao,
    rotulo_classe_ativo,
)
from mercado import load_market_data
from utils.exceptions import DadosIndisponiveisError
from utils.logging_config import get_logger, setup_logging


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
    return load_market_data()


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
        st.metric("SELIC", f"{market['selic'] * 100:.2f}%")
        st.metric("IPCA 12 meses", f"{market['ipca'] * 100:.2f}%")
        st.metric(
            "Ibovespa CAGR 10 anos",
            f"{market['ibov_cagr'] * 100:.2f}%",
        )
        if market.get("focus_selic") is not None:
            st.metric(
                "Focus SELIC",
                f"{market['focus_selic'] * 100:.2f}%",
            )

        st.divider()
        if market.get("cache_status") == "stale":
            st.warning("Usando dados reais de cache por falha na atualização.")
        else:
            st.caption("Indicadores carregados das fontes online/cache recente.")

        for aviso in market.get("avisos", []):
            st.caption(aviso)

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
                    "Usada somente no regime progressivo. Zero é uma "
                    "renda informada; selecione 'não informado' no regime "
                    "quando não souber."
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

        submitted = st.form_submit_button(
            "Gerar recomendação",
            type="primary",
            use_container_width=True,
        )

    if not submitted:
        return

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
            if regime_previdencia_informado == "progressivo"
            else None
        ),
        "jurisdicao_cripto": jurisdicao_cripto_informada,
        "pessoa_fisica": pessoa_fisica,
    }

    st.session_state.pop("analise_investimentos", None)
    try:
        with st.spinner("Calculando perfil, alocação e projeções..."):
            analise = criar_analise(
                respostas,
                market,
                data_referencia=dt.date.today(),
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
        f"{resultado['taxa_perfil'] * 100:.2f}% a.a.",
    )
    cols[3].metric(
        "Classificação da carteira",
        resultado["risco_recomendado_display"],
    )

    if resultado["perfil_exibido"] != resultado["recomendacao_principal"]:
        st.caption(
            "Categoria representativa da carteira: "
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


def _render_alocacao(analise: dict) -> None:
    resultado = analise["resultado"]
    itens = resultado["portfolio_itens"]
    labels = [item["nome"] for item in itens]
    values = [item["percentual"] for item in itens]

    st.subheader("📊 Alocação sugerida")
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
            height=420,
            margin={"t": 20, "b": 20, "l": 20, "r": 20},
            showlegend=False,
        )
        st.plotly_chart(figure, use_container_width=True)

    with col_table:
        tabela = pd.DataFrame(
            {"Classe": labels, "Alocação (%)": values}
        )
        st.dataframe(
            tabela,
            hide_index=True,
            use_container_width=True,
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
            f"Taxa-base: {resultado['taxa_base'] * 100:.2f}% a.a. · "
            f"Cenário pessimista: {resultado['taxa_pess'] * 100:.2f}% a.a."
        )


def _projecoes_dataframe(projecoes: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Anos": linha["anos"],
                "VF Bruto": linha["vf_bruto"],
                "Imposto estimado": linha["imposto_estimado"],
                "VF Líquido": linha["vf_liquido"],
                "Poder de compra": linha["vf_real"],
                "Pessimista líquido": linha[
                    "vf_pessimista_liquido"
                ],
                "Precisão tributária": linha["precisao_tributaria"],
            }
            for linha in projecoes
        ]
    )


def _render_projecoes(analise: dict) -> None:
    respostas = analise["respostas"]
    resultado = analise["resultado"]
    market = analise["market"]

    st.subheader("📈 Projeção de crescimento")
    st.caption(
        f"Capital inicial: **R$ {respostas['cap_inicial']:,.2f}** · "
        f"Aporte mensal: **R$ {respostas['aporte_mensal']:,.2f}** · "
        f"Taxa ponderada bruta: "
        f"**{resultado['taxa_perfil'] * 100:.2f}% a.a.** · "
        f"IPCA: **{market['ipca'] * 100:.2f}% a.a.**"
    )

    st.dataframe(
        _projecoes_dataframe(analise["projecoes"]),
        hide_index=True,
        use_container_width=True,
        column_config={
            "Anos": st.column_config.NumberColumn("Anos", format="%d"),
            "VF Bruto": st.column_config.NumberColumn(
                "VF Bruto",
                format="R$ %.2f",
            ),
            "Imposto estimado": st.column_config.NumberColumn(
                "Imposto estimado",
                format="R$ %.2f",
            ),
            "VF Líquido": st.column_config.NumberColumn(
                "VF Líquido",
                format="R$ %.2f",
            ),
            "Poder de compra": st.column_config.NumberColumn(
                "Poder de compra",
                format="R$ %.2f",
            ),
            "Pessimista líquido": st.column_config.NumberColumn(
                "Pessimista líquido",
                format="R$ %.2f",
            ),
        },
    )

    if any(
        linha["vf_liquido"] is None
        for linha in analise["projecoes"]
    ):
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
    figure.add_trace(
        go.Scatter(
            x=[linha["anos"] for linha in serie],
            y=[linha["vf_real"] for linha in serie],
            mode="lines",
            name="Poder de compra",
        )
    )
    figure.update_layout(
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
    st.plotly_chart(figure, use_container_width=True)


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
        resumo,
        hide_index=True,
        use_container_width=True,
        column_config={
            "Anos": st.column_config.NumberColumn("Anos", format="%d"),
            "Imposto estimado": st.column_config.NumberColumn(
                "Imposto estimado",
                format="R$ %.2f",
            ),
            "Imposto parcial calculado": st.column_config.NumberColumn(
                "Imposto parcial calculado",
                format="R$ %.2f",
            ),
            "Bruto sem tributação definida": st.column_config.NumberColumn(
                "Bruto sem tributação definida",
                format="R$ %.2f",
            ),
        },
    )

    horizonte = max(projecoes, key=lambda linha: float(linha["anos"]))
    with st.expander(
        f"Premissas por classe — horizonte de {horizonte['anos']:g} ano(s)"
    ):
        for detalhe in horizonte["tributacao_por_classe"].values():
            imposto = detalhe["imposto_estimado"]
            imposto_texto = (
                f"R$ {imposto:,.2f}"
                if isinstance(imposto, (int, float))
                else "indeterminado"
            )
            st.markdown(
                f"**{detalhe['nome']}** · "
                f"`{detalhe['tipo_produto']}` · "
                f"{detalhe['precisao']} · imposto {imposto_texto}"
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
        st.warning(meta["motivo_indeterminacao"])
        st.caption(
            "Preencha as premissas fiscais ausentes e gere a análise "
            "novamente para avaliar a meta líquida."
        )
        return

    cols = st.columns(3)
    cols[0].metric(
        "Valor-alvo nominal",
        f"R$ {meta['valor_alvo']:,.2f}",
    )
    cols[1].metric(
        f"Projeção em {meta['prazo_anos']:g} ano(s)",
        f"R$ {meta['valor_liquido_projetado']:,.2f}",
    )
    cols[2].metric(
        "Diferença",
        f"R$ {meta['diferenca']:,.2f}",
        delta=f"R$ {meta['diferenca']:,.2f}",
        delta_color="normal",
    )

    if meta["atingida"]:
        st.success(
            "A meta é atingível no cenário central, com margem nominal de "
            f"R$ {meta['diferenca']:,.2f}."
        )
    else:
        mensagem = (
            "Faltariam aproximadamente "
            f"R$ {abs(meta['diferenca']):,.2f} no cenário central."
        )
        if meta["aporte_mensal_estimado"] is not None:
            mensagem += (
                " O aporte mensal total estimado para atingir a meta é "
                f"R$ {meta['aporte_mensal_estimado']:,.2f}."
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
        use_container_width=True,
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
                "score": "Score",
                "motivos": "Destaques",
            }
            tabela = tabela.rename(
                columns={
                    antiga: nova
                    for antiga, nova in renomear.items()
                    if antiga in tabela.columns
                }
            )
            preferidas = ["Ticker", "Nome", "Preço", "Score", "Destaques"]
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
                tabela[colunas],
                hide_index=True,
                use_container_width=True,
                column_config={
                    "Preço": st.column_config.NumberColumn(
                        "Preço",
                        format="R$ %.2f",
                    ),
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
            use_container_width=True,
        )


def _render_exportacao(analise: dict) -> None:
    payload = montar_payload_exportacao(analise)
    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
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
        use_container_width=True,
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
            != dt.date.today().isoformat()
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
