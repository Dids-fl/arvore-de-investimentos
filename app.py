"""
Interface Streamlit do recomendador de investimentos.

Execute com:
    streamlit run app.py

Este módulo mantém a interface separada da regra de recomendação. O
questionário é convertido pelos mesmos mapas usados pelo CLI e o resultado
central é produzido por engine.py.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from typing import Any, Optional

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st

from calculos import _vf_bruto, _vf_liquido, _vf_real
from core.catalogo import _aliq, _disp, _get_prod
from core.categorias import _risco
from engine import gerar_recomendacao_completa, mapear_respostas_formulario
from mercado import load_market_data
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

st.set_page_config(
    page_title="Recomendador de Investimentos",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


ANOS_PROJECAO = (1, 2, 5, 10, 20, 30)
RISCO_LABEL = {1: "Conservador", 2: "Moderado", 3: "Agressivo"}


@st.cache_data(ttl=3600, show_spinner=False)
def get_market_data() -> dict:
    """Cache de interface; mercado.py mantém também seu cache persistente."""
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


def _normalizar_experiencia(experiencia: list[str]) -> list[str]:
    itens = list(dict.fromkeys(experiencia or []))
    if len(itens) > 1 and "nenhum" in itens:
        itens.remove("nenhum")
    return itens or ["nenhum"]


def _taxas_por_risco(
    selic: float,
    focus_selic: Optional[float],
    ibov_cagr: float,
) -> tuple[dict[int, float], float]:
    """
    Usa de fato o Focus quando ele existe.

    A implementação anterior exibia a média SELIC–Focus, mas continuava
    calculando a carteira apenas com a SELIC corrente.
    """
    taxa_base = (
        (selic + focus_selic) / 2.0
        if focus_selic is not None
        else selic
    )
    return (
        {
            1: taxa_base,
            2: (taxa_base + ibov_cagr) / 2.0,
            3: ibov_cagr,
        },
        taxa_base,
    )


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
    Projeta cada classe com sua própria tributação.

    Isso evita aplicar a alíquota de uma única categoria representativa sobre
    toda a carteira.
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
    """Estima por busca binária o aporte mensal para atingir a meta líquida."""
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


def _montar_projecoes(analise: dict) -> list[dict[str, float]]:
    resultado = analise["resultado"]
    respostas = analise["respostas"]
    market = analise["market"]
    portfolio = resultado["portfolio"]
    taxas = resultado["TAXAS"]
    taxa_pess = resultado["taxa_pess"]

    linhas: list[dict[str, float]] = []
    for anos in ANOS_PROJECAO:
        central = _projetar_portfolio(
            respostas["cap_inicial"],
            respostas["aporte_mensal"],
            portfolio,
            taxas,
            market["ipca"],
            anos,
        )
        pessimista = _projetar_portfolio(
            respostas["cap_inicial"],
            respostas["aporte_mensal"],
            portfolio,
            taxas,
            market["ipca"],
            anos,
            taxa_unica=taxa_pess,
        )
        linhas.append(
            {
                "Anos": anos,
                "VF Bruto": central["bruto"],
                "VF Líquido": central["liquido"],
                "Poder de compra": central["real"],
                "Pessimista líquido": pessimista["liquido"],
            }
        )
    return linhas


def _classes_para_busca(
    portfolio: dict[str, int],
    recomendacao_principal: str,
) -> tuple[dict[str, int], set[str]]:
    """
    Inclui na busca a recomendação específica mesmo quando portfolio.py a
    converteu em uma categoria genérica.
    """
    portfolio_busca = dict(portfolio)
    if (
        recomendacao_principal in MAPA_CLASSE
        and recomendacao_principal not in portfolio_busca
    ):
        portfolio_busca[recomendacao_principal] = MIN_PCT

    classes = {
        MAPA_CLASSE[categoria]
        for categoria, pct in portfolio_busca.items()
        if pct >= MIN_PCT and categoria in MAPA_CLASSE
    }
    return portfolio_busca, classes


def _criar_analise(
    respostas: dict,
    meta_valor: Optional[float],
    meta_prazo: Optional[float],
    market: dict,
) -> dict:
    """Executa o motor e corrige os cálculos de apresentação."""
    resultado = gerar_recomendacao_completa(respostas, market)

    taxas, taxa_base = _taxas_por_risco(
        market["selic"],
        market.get("focus_selic"),
        market["ibov_cagr"],
    )
    portfolio = resultado["portfolio"]
    taxa_perfil = _taxa_ponderada(portfolio, taxas)
    taxa_pess = min(
        taxa_perfil,
        max(market["ipca"] + 0.02, taxa_perfil * 0.60),
    )

    recomendacao_principal = resultado["rec_key"]
    portfolio_busca, classes = _classes_para_busca(
        portfolio,
        recomendacao_principal,
    )

    resultado.update(
        {
            "recomendacao_principal": recomendacao_principal,
            "recomendacao_display": _disp(recomendacao_principal),
            "info_principal": _get_prod(recomendacao_principal),
            "TAXAS": taxas,
            "taxa_base": taxa_base,
            "taxa_perfil": taxa_perfil,
            "taxa_pess": taxa_pess,
            "portfolio_busca": portfolio_busca,
            "classes_no_portfolio": classes,
        }
    )

    return {
        "respostas": respostas,
        "meta_valor": meta_valor,
        "meta_prazo": meta_prazo,
        "market": market,
        "resultado": resultado,
        "ativos_sugeridos": {},
        "classes_indisponiveis": {},
    }


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
        status_cache = market.get("cache_status")
        if status_cache == "stale":
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
            "Responda com sua situação real. As opções de percentual e meta "
            "só serão usadas quando a resposta correspondente for selecionada."
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
        meta = st.selectbox(
            "O que deseja calcular?",
            ["sim", "rendendo", "não"],
            format_func=lambda valor_meta: {
                "sim": "Quero atingir um valor específico",
                "rendendo": "Quero ver como o dinheiro pode crescer",
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
                help="Usado apenas na opção de atingir um valor específico.",
            )
        with fcol4:
            meta_prazo_informado = st.number_input(
                "Prazo da meta (anos)",
                min_value=1,
                max_value=50,
                value=10,
                step=1,
            )

        submitted = st.form_submit_button(
            "Gerar recomendação",
            type="primary",
            use_container_width=True,
        )

    if not submitted:
        return

    liquidez_pct = (
        float(liquidez_pct_informado)
        if liquidez == "sim"
        else 0.0
    )
    aporte_mensal = (
        float(aporte_mensal_informado)
        if aporte == "mensal"
        else 0.0
    )
    meta_valor = (
        float(meta_valor_informado)
        if meta == "sim"
        else None
    )
    meta_prazo = (
        float(meta_prazo_informado)
        if meta == "sim"
        else None
    )

    respostas_texto = {
        "prazo": prazo,
        "risco": risco,
        "objetivo": objetivo,
        "fluxo": fluxo,
        "controle": controle,
        "liquidez": liquidez,
        "liquidez_pct": liquidez_pct,
        "reserva_emerg": reserva,
        "idade": idade,
        "despesas": despesas,
        "faixa_valor": valor,
        "patrim_pct": patrimonio,
        "renda": renda,
        "dividas": dividas,
        "conhecimento": conhecimento,
        "experiencia": _normalizar_experiencia(experiencia),
        "dependentes": dependentes,
        "aporte": aporte,
        "emocional": emocional,
        "ir_tipo": ir_tipo,
        "carteira_atual": carteira,
        "modo_meta": meta,
        "cap_inicial": float(cap_inicial),
        "aporte_mensal": aporte_mensal,
    }

    try:
        respostas = mapear_respostas_formulario(respostas_texto)
    except ValueError as exc:
        logger.warning("Resposta inválida no formulário: %s", exc)
        st.error(f"Há uma resposta inválida no formulário: {exc}")
        return

    st.session_state.pop("analise_investimentos", None)

    # Impede que o sys.exit() legado de recomendador.py alcance o Streamlit.
    if respostas["dividas"] == 1:
        st.error("🚨 Dívidas de juros altos detectadas")
        st.warning(
            "Quite ou renegocie cartão de crédito e cheque especial antes de "
            "investir. O custo dessas dívidas normalmente supera o retorno "
            "esperado dos investimentos."
        )
        return

    try:
        with st.spinner("Calculando perfil e alocação..."):
            analise = _criar_analise(
                respostas,
                meta_valor,
                meta_prazo,
                market,
            )
    except SystemExit:
        logger.error("O motor tentou encerrar o processo.")
        st.error(
            "O motor interrompeu a recomendação por uma regra de segurança."
        )
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
    cols[0].metric(
        "Perfil",
        RISCO_LABEL[resultado["nivel_risco_perfil"]],
    )
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
        RISCO_LABEL[resultado["risco_recomendado"]],
    )

    categoria = resultado["perfil_exibido"]
    if categoria != resultado["recomendacao_principal"]:
        st.caption(
            "Categoria representativa da carteira: "
            f"**{_disp(categoria)}**. A recomendação principal acima preserva "
            "o produto específico escolhido pelas regras do questionário."
        )


def _render_alocacao(analise: dict) -> None:
    resultado = analise["resultado"]
    portfolio = resultado["portfolio"]

    st.subheader("📊 Alocação sugerida")
    labels = [_disp(k) for k, pct in portfolio.items() if pct > 0]
    values = [pct for pct in portfolio.values() if pct > 0]

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
            st.info("O catálogo não possui itens detalhados para essa categoria.")


def _render_projecoes(analise: dict) -> list[dict[str, float]]:
    respostas = analise["respostas"]
    resultado = analise["resultado"]
    market = analise["market"]
    projecoes = _montar_projecoes(analise)

    st.subheader("📈 Projeção de crescimento")
    st.caption(
        f"Capital inicial: **R$ {respostas['cap_inicial']:,.2f}** · "
        f"Aporte mensal: **R$ {respostas['aporte_mensal']:,.2f}** · "
        f"Taxa ponderada bruta: "
        f"**{resultado['taxa_perfil'] * 100:.2f}% a.a.** · "
        f"IPCA de referência: **{market['ipca'] * 100:.2f}% a.a.**"
    )

    dataframe = pd.DataFrame(projecoes)
    st.dataframe(
        dataframe,
        hide_index=True,
        use_container_width=True,
        column_config={
            "Anos": st.column_config.NumberColumn("Anos", format="%d"),
            "VF Bruto": st.column_config.NumberColumn(
                "VF Bruto",
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

    anos_continuos = list(range(1, 31))
    bruto_continuo: list[float] = []
    liquido_continuo: list[float] = []
    real_continuo: list[float] = []

    for anos in anos_continuos:
        projecao = _projetar_portfolio(
            respostas["cap_inicial"],
            respostas["aporte_mensal"],
            resultado["portfolio"],
            resultado["TAXAS"],
            market["ipca"],
            anos,
        )
        bruto_continuo.append(projecao["bruto"])
        liquido_continuo.append(projecao["liquido"])
        real_continuo.append(projecao["real"])

    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=anos_continuos,
            y=bruto_continuo,
            mode="lines",
            name="Bruto",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=anos_continuos,
            y=liquido_continuo,
            mode="lines",
            name="Líquido",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=anos_continuos,
            y=real_continuo,
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
    return projecoes


def _render_meta(analise: dict) -> Optional[dict[str, Any]]:
    meta_valor = analise.get("meta_valor")
    meta_prazo = analise.get("meta_prazo")
    if meta_valor is None or meta_prazo is None:
        return None

    respostas = analise["respostas"]
    resultado = analise["resultado"]
    market = analise["market"]

    projecao = _projetar_portfolio(
        respostas["cap_inicial"],
        respostas["aporte_mensal"],
        resultado["portfolio"],
        resultado["TAXAS"],
        market["ipca"],
        meta_prazo,
    )
    valor_projetado = projecao["liquido"]
    diferenca = valor_projetado - meta_valor
    atingida = diferenca >= 0
    aporte_necessario = _aporte_necessario_para_meta(
        meta_valor,
        meta_prazo,
        respostas["cap_inicial"],
        resultado["portfolio"],
        resultado["TAXAS"],
        market["ipca"],
    )

    st.subheader("🎯 Análise da meta")
    cols = st.columns(3)
    cols[0].metric("Valor-alvo nominal", f"R$ {meta_valor:,.2f}")
    cols[1].metric(
        f"Projeção em {meta_prazo:g} ano(s)",
        f"R$ {valor_projetado:,.2f}",
    )
    cols[2].metric(
        "Diferença",
        f"R$ {diferenca:,.2f}",
        delta=f"R$ {diferenca:,.2f}",
        delta_color="normal",
    )

    if atingida:
        st.success(
            f"A meta é atingível no cenário central, com margem nominal de "
            f"R$ {diferenca:,.2f}."
        )
    else:
        mensagem = (
            f"Faltariam aproximadamente R$ {abs(diferenca):,.2f} no "
            "cenário central."
        )
        if aporte_necessario is not None:
            mensagem += (
                f" O aporte mensal total estimado para atingir a meta é "
                f"R$ {aporte_necessario:,.2f}."
            )
        st.warning(mensagem)

    return {
        "valor_alvo": meta_valor,
        "prazo_anos": meta_prazo,
        "valor_liquido_projetado": valor_projetado,
        "atingida": atingida,
        "diferenca": diferenca,
        "aporte_mensal_informado": respostas["aporte_mensal"],
        "aporte_mensal_estimado": aporte_necessario,
    }


def _render_ativos(analise: dict) -> None:
    resultado = analise["resultado"]
    classes = resultado["classes_no_portfolio"]

    st.subheader("🔎 Ativos específicos")
    if not classes:
        st.info(
            "A alocação não contém classes com suporte a ranking de ativos."
        )
        return

    nomes_classes = [_LABEL.get(classe, classe.upper()) for classe in sorted(classes)]
    st.caption(
        "Classes disponíveis: " + ", ".join(nomes_classes)
        + ". A consulta só ocorre quando você clicar no botão."
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
                payload = recomendar_por_portfolio(
                    resultado["portfolio_busca"],
                    resultado["nivel_risco_perfil"],
                    selic=analise["market"]["selic"],
                    ipca=analise["market"]["ipca"],
                    ibov_cagr=analise["market"]["ibov_cagr"],
                )
            if not isinstance(payload, dict):
                raise TypeError(
                    "O ranking de ativos retornou um formato inválido."
                )
            indisponiveis = payload.pop("_indisponiveis", {})
            analise["ativos_sugeridos"] = payload
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
            st.caption(
                f"• **{_LABEL.get(classe, classe.upper())}**: {motivo}"
            )

    if not ativos:
        return

    tabs = st.tabs(
        [_LABEL.get(classe, classe.upper()) for classe in ativos]
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
            if "score" in tabela.columns:
                tabela["score"] = pd.to_numeric(
                    tabela["score"],
                    errors="coerce",
                ).round(2)
            if "preco" in tabela.columns:
                tabela["preco"] = pd.to_numeric(
                    tabela["preco"],
                    errors="coerce",
                )

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
            colunas_preferidas = [
                "Ticker",
                "Nome",
                "Preço",
                "Score",
                "Destaques",
            ]
            colunas = [
                coluna
                for coluna in colunas_preferidas
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
    respostas = analise["respostas"]

    if resultado["avisos"]:
        st.subheader("⚠️ Observações e ajustes")
        for aviso in resultado["avisos"]:
            if "🚨" in aviso or "⚠️" in aviso:
                st.warning(aviso)
            else:
                st.info(aviso)

    display = {
        "Prazo": {1: "Curto", 2: "Médio", 3: "Longo"}[respostas["prazo"]],
        "Risco declarado": {
            1: "Baixo",
            2: "Médio",
            3: "Alto",
        }[respostas["risco"]],
        "Risco efetivo": RISCO_LABEL[resultado["nivel_risco_perfil"]],
        "Objetivo": {
            1: "Reserva",
            2: "Crescimento",
            3: "Aposentadoria",
        }[respostas["objetivo"]],
        "Liquidez": (
            f"Sim — {respostas['liquidez_pct']:.0f}%"
            if respostas["liquidez"] == 1
            else "Não"
        ),
        "Capital inicial": f"R$ {respostas['cap_inicial']:,.2f}",
        "Aporte mensal": f"R$ {respostas['aporte_mensal']:,.2f}",
        "Experiência": ", ".join(respostas["experiencia"]),
        "Recomendação principal": resultado["recomendacao_display"],
    }

    with st.expander("Respostas e classificação"):
        st.dataframe(
            pd.DataFrame(display.items(), columns=["Critério", "Resultado"]),
            hide_index=True,
            use_container_width=True,
        )


def _render_exportacao(
    analise: dict,
    projecoes: list[dict[str, float]],
    resultado_meta: Optional[dict[str, Any]],
) -> None:
    resultado = analise["resultado"]
    portfolio = resultado["portfolio"]

    tributacao = {
        _disp(categoria): {
            "aliquota_pct": round(_aliq(categoria)[0] * 100, 2),
            "incide_sobre_total_pgbl": _aliq(categoria)[1],
        }
        for categoria, pct in portfolio.items()
        if pct > 0
    }

    export_data = {
        "recomendacao": resultado["recomendacao_principal"],
        "recomendacao_display": resultado["recomendacao_display"],
        "categoria_representativa_carteira": resultado["perfil_exibido"],
        "portfolio": portfolio,
        "portfolio_display": {
            _disp(categoria): pct
            for categoria, pct in portfolio.items()
            if pct > 0
        },
        "nivel_risco_perfil": resultado["nivel_risco_perfil"],
        "risco_recomendacao": resultado["risco_recomendado"],
        "taxas_utilizadas": {
            "selic_atual_pct": round(analise["market"]["selic"] * 100, 2),
            "focus_selic_pct": (
                round(analise["market"]["focus_selic"] * 100, 2)
                if analise["market"].get("focus_selic") is not None
                else None
            ),
            "taxa_base_pct": round(resultado["taxa_base"] * 100, 2),
            "ipca_12m_pct": round(analise["market"]["ipca"] * 100, 2),
            "ibov_cagr_10a_pct": round(
                analise["market"]["ibov_cagr"] * 100,
                2,
            ),
            "taxa_carteira_ponderada_bruto_pct": round(
                resultado["taxa_perfil"] * 100,
                2,
            ),
            "taxa_pessimista_bruto_pct": round(
                resultado["taxa_pess"] * 100,
                2,
            ),
            "tributacao_por_classe": tributacao,
        },
        "meta": resultado_meta,
        "projecoes": projecoes,
        "avisos": resultado["avisos"],
        "ativos_sugeridos": analise.get("ativos_sugeridos", {}),
        "classes_indisponiveis": analise.get(
            "classes_indisponiveis",
            {},
        ),
        "fontes_de_dados": analise["market"].get("fontes", []),
        "dados_mercado": {
            "data_ref": analise["market"].get("data_ref"),
            "fetched_at": analise["market"].get("fetched_at"),
            "cache_status": analise["market"].get("cache_status"),
        },
    }

    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    st.download_button(
        "Baixar análise completa em JSON",
        data=json.dumps(
            export_data,
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
    projecoes = _render_projecoes(analise)
    resultado_meta = _render_meta(analise)
    st.divider()
    _render_ativos(analise)
    st.divider()
    _render_avisos_e_perfil(analise)
    st.divider()
    _render_exportacao(analise, projecoes, resultado_meta)


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
            "Não foi possível obter os indicadores obrigatórios de mercado. "
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
        and _market_signature(analise_anterior.get("market", {}))
        != _market_signature(market)
    ):
        st.session_state.pop("analise_investimentos", None)
        st.info(
            "Os indicadores de mercado foram atualizados. Gere uma nova "
            "recomendação para manter os cálculos consistentes."
        )

    _render_sidebar(market)
    _render_questionario(market)

    analise = st.session_state.get("analise_investimentos")
    if analise is not None:
        st.divider()
        _render_resultado(analise)


if __name__ == "__main__":
    main()