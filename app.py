import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
import json

# Importações do motor de recomendação
from config import IR_RF
from categorias import _risco
from catalogo import _get_prod, _disp, _aliq
from mercado import load_market_data
from calculos import _vf_bruto, _vf_liquido, _vf_real
from recomendador import calcular_recomendacao
from portfolio import _build_portfolio, _classificar_portfolio_final
from recomendador_ativos import recomendar_por_portfolio, _LABEL, MIN_PCT
from utils.logging_config import setup_logging

# Configuração da página
st.set_page_config(
    page_title="Recomendador de Investimentos",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Título
st.title("📊 Recomendador de Investimentos")
st.markdown("**Análise completa de perfil – versão web**")

# Carrega dados de mercado uma vez
@st.cache_data(ttl=3600)
def get_market_data():
    return load_market_data()

market_data = get_market_data()
selic = market_data["selic"]
ipca = market_data["ipca"]
ibov_cagr = market_data["ibov_cagr"]
focus_selic = market_data.get("focus_selic")

TAXAS = {
    1: selic,
    2: (selic + ibov_cagr) / 2,
    3: ibov_cagr
}

# ── Função de mapeamento das respostas ──────────────────────────────────────
def map_respostas(prazo, risco, objetivo, fluxo, controle, liquidez, reserva,
                  idade, despesas, valor, patrimonio, renda, dividas,
                  conhecimento, experiencia, dependentes, aporte, emocional,
                  ir_tipo, carteira, meta, cap_inicial, aporte_mensal):
    """Mapeia as respostas do formulário para os valores inteiros esperados."""
    map_prazo = {"curto": 1, "médio": 2, "longo": 3}
    map_risco = {"baixo": 1, "médio": 2, "alto": 3}
    map_objetivo = {"reserva": 1, "crescimento": 2, "aposentadoria": 3}
    map_fluxo = {"renda": 1, "acúmulo": 2}
    map_controle = {"gerir": 1, "delegar": 2}
    map_liquidez = {"sim": 1, "não": 2}
    map_reserva = {"não tenho": 1, "parcial": 2, "sim": 3}
    map_idade = {"jovem": 1, "adulto": 2, "sênior": 3}
    map_despesas = {"nenhuma": 1, "baixas": 2, "altas": 3}
    map_valor = {"baixo": 1, "médio": 2, "alto": 3}
    map_patrimonio = {"baixo": 1, "médio": 2, "alto": 3}
    map_renda = {"clt": 1, "pj contratado": 2, "autônomo": 3, "sem renda": 4}
    map_dividas = {"juros altos": 1, "juros baixos": 2, "não tenho": 3}
    map_conhecimento = {"iniciante": 1, "intermediário": 2, "experiente": 3}
    map_dependentes = {"nenhum": 1, "um": 2, "dois ou mais": 3}
    map_aporte = {"único": 1, "mensal": 2}
    map_emocional = {"venderia tudo": 1, "esperaria recuperar": 2, "compraria mais": 3}
    map_ir = {"completo": 1, "simplificado": 2, "não declaro": 3}
    map_carteira = {"não tenho": 1, "conservadora": 2, "moderada": 3, "arrojada": 4}
    map_meta = {"sim": 1, "rendendo": 2, "não": 3}

    return {
        "prazo": map_prazo[prazo],
        "risco": map_risco[risco],
        "objetivo": map_objetivo[objetivo],
        "fluxo": map_fluxo[fluxo],
        "controle": map_controle[controle],
        "liquidez": map_liquidez[liquidez],
        "liquidez_pct": 0.0,
        "reserva_emerg": map_reserva[reserva],
        "idade": map_idade[idade],
        "despesas": map_despesas[despesas],
        "faixa_valor": map_valor[valor],
        "patrim_pct": map_patrimonio[patrimonio],
        "renda": map_renda[renda],
        "dividas": map_dividas[dividas],
        "conhecimento": map_conhecimento[conhecimento],
        "experiencia": experiencia if experiencia else ["nenhum"],
        "dependentes": map_dependentes[dependentes],
        "aporte": map_aporte[aporte],
        "emocional": map_emocional[emocional],
        "ir_tipo": map_ir[ir_tipo],
        "carteira_atual": map_carteira[carteira],
        "modo_meta": 2,
        "cap_inicial": cap_inicial,
        "aporte_mensal": aporte_mensal,
    }

# ── Função principal de recomendação ────────────────────────────────────────
def gerar_recomendacao(respostas):
    """Executa o motor de recomendação e retorna todos os resultados."""
    prazo = respostas["prazo"]
    risco = respostas["risco"]
    objetivo = respostas["objetivo"]
    fluxo = respostas["fluxo"]
    controle = respostas["controle"]
    liquidez = respostas["liquidez"]
    liquidez_pct = respostas["liquidez_pct"]
    reserva_emerg = respostas["reserva_emerg"]
    idade = respostas["idade"]
    despesas = respostas["despesas"]
    faixa_valor = respostas["faixa_valor"]
    patrim_pct = respostas["patrim_pct"]
    renda = respostas["renda"]
    dividas = respostas["dividas"]
    conhecimento = respostas["conhecimento"]
    experiencia = respostas["experiencia"]
    dependentes = respostas["dependentes"]
    aporte = respostas["aporte"]
    emocional = respostas["emocional"]
    ir_tipo = respostas["ir_tipo"]
    carteira_atual = respostas["carteira_atual"]
    cap_inicial = respostas["cap_inicial"]
    aporte_mensal = respostas["aporte_mensal"]

    if dividas == 1:
        st.error("🚨 DÍVIDAS DE JUROS ALTOS DETECTADAS!")
        st.warning("""
        Você possui dívidas com juros altos (cartão de crédito, cheque especial).
        Esses juros (>15% a.m.) superam qualquer retorno disponível no mercado.
        
        **✅ Recomendação: Quite suas dívidas PRIMEIRO.**
        Após quitar, volte e refaça este questionário.
        """)
        st.stop()

    rec_key, nivel_risco_perfil, meses_res, avisos, conhecimento_ajustado = calcular_recomendacao(
        prazo=prazo, risco=risco, objetivo=objetivo, fluxo=fluxo,
        controle=controle, liquidez=liquidez, liquidez_pct=liquidez_pct,
        reserva_emerg=reserva_emerg, idade=idade, despesas=despesas,
        faixa_valor=faixa_valor, patrim_pct=patrim_pct, renda=renda,
        dividas=dividas, conhecimento=conhecimento, experiencia=experiencia,
        dependentes=dependentes, aporte=aporte, emocional=emocional,
        ir_tipo=ir_tipo, carteira_atual=carteira_atual, TAXAS=TAXAS
    )

    portfolio = _build_portfolio(
        nivel_risco_perfil, conhecimento_ajustado, faixa_valor, objetivo,
        renda, dividas, dependentes, aporte, carteira_atual, ir_tipo,
        fluxo, patrim_pct, liquidez_pct, despesas, idade, avisos
    )

    perfil_exibido, risco_recomendado = _classificar_portfolio_final(portfolio)

    info = _get_prod(perfil_exibido)
    aliq, pgbl = _aliq(perfil_exibido)

    taxa_perfil = sum((pct / 100) * TAXAS[_risco(k)] for k, pct in portfolio.items())
    taxa_pess = max(ipca + 0.02, taxa_perfil * 0.6)

    from recomendador_ativos import _CLASSE as MAPA_CLASSE
    classes_no_portfolio = {
        MAPA_CLASSE[rk]
        for rk, pct in portfolio.items()
        if pct >= MIN_PCT and rk in MAPA_CLASSE
    }

    ativos_sugeridos = {}
    if classes_no_portfolio:
        ativos_sugeridos = recomendar_por_portfolio(
            portfolio, nivel_risco_perfil,
            selic=selic, ipca=ipca, ibov_cagr=ibov_cagr
        )

    rlabel = {1: "Conservador", 2: "Moderado", 3: "Agressivo"}
    perfil_risco_label = rlabel[nivel_risco_perfil]

    return {
        "rec_key": rec_key,
        "perfil_exibido": perfil_exibido,
        "perfil_display": _disp(perfil_exibido),
        "portfolio": portfolio,
        "nivel_risco": nivel_risco_perfil,
        "risco_label": perfil_risco_label,
        "risco_recomendado": risco_recomendado,
        "info": info,
        "aliq": aliq,
        "pgbl": pgbl,
        "taxa_perfil": taxa_perfil,
        "taxa_pess": taxa_pess,
        "avisos": avisos,
        "meses_res": meses_res,
        "cap_inicial": cap_inicial,
        "aporte_mensal": aporte_mensal,
        "ativos": ativos_sugeridos,
        "classes": classes_no_portfolio,
    }

# ── Interface do usuário ─────────────────────────────────────────────────────

with st.sidebar:
    st.header("📈 Dados de Mercado")
    st.metric("SELIC", f"{selic*100:.2f}%")
    st.metric("IPCA 12m", f"{ipca*100:.2f}%")
    st.metric("Ibovespa CAGR 10a", f"{ibov_cagr*100:.1f}%")
    if focus_selic:
        st.metric("Focus SELIC", f"{focus_selic*100:.2f}%")
    st.divider()
    st.caption("Dados atualizados em tempo real via BCB e Yahoo Finance")

with st.form("form_questionario"):
    st.subheader("📝 Perfil do Investidor")
    
    col1, col2 = st.columns(2)
    
    with col1:
        prazo = st.selectbox("Prazo de investimento", ["curto", "médio", "longo"])
        risco = st.selectbox("Tolerância a risco", ["baixo", "médio", "alto"])
        objetivo = st.selectbox("Objetivo principal", ["reserva", "crescimento", "aposentadoria"])
        fluxo = st.selectbox("Preferência de fluxo", ["renda", "acúmulo"])
        controle = st.selectbox("Gestão dos investimentos", ["gerir", "delegar"])
        liquidez = st.selectbox("Precisa de liquidez imediata?", ["sim", "não"])
        reserva = st.selectbox("Reserva de emergência", ["não tenho", "parcial", "sim"])
        idade = st.selectbox("Faixa etária", ["jovem", "adulto", "sênior"])
        despesas = st.selectbox("Obrigações fixas mensais", ["nenhuma", "baixas", "altas"])
        valor = st.selectbox("Valor disponível para investir", ["baixo", "médio", "alto"])
    
    with col2:
        patrimonio = st.selectbox("Parcela do patrimônio total", ["baixo", "médio", "alto"])
        renda = st.selectbox("Situação de renda", ["clt", "pj contratado", "autônomo", "sem renda"])
        dividas = st.selectbox("Dívidas ativas", ["juros altos", "juros baixos", "não tenho"])
        conhecimento = st.selectbox("Nível de conhecimento", ["iniciante", "intermediário", "experiente"])
        experiencia = st.multiselect("Produtos investidos nos últimos 2 anos", ["poupança", "tesouro", "ações", "fundos", "opções", "nenhum"])
        dependentes = st.selectbox("Pessoas que dependem de você", ["nenhum", "um", "dois ou mais"])
        aporte = st.selectbox("Tipo de aporte", ["único", "mensal"])
        emocional = st.selectbox("Reação a queda de 30%", ["venderia tudo", "esperaria recuperar", "compraria mais"])
        ir_tipo = st.selectbox("Declaração de IR", ["completo", "simplificado", "não declaro"])
        carteira = st.selectbox("Carteira atual", ["não tenho", "conservadora", "moderada", "arrojada"])
        meta = st.selectbox("Meta financeira", ["sim", "rendendo", "não"])
    
    st.subheader("💰 Dados Financeiros")
    col3, col4 = st.columns(2)
    with col3:
        cap_inicial = st.number_input("Capital inicial (R$)", min_value=0.0, value=6000.0, step=1000.0, format="%.2f")
    with col4:
        aporte_mensal = st.number_input("Aporte mensal (R$)", min_value=0.0, value=0.0, step=100.0, format="%.2f")
    
    submitted = st.form_submit_button("🚀 Gerar Recomendação", type="primary", use_container_width=True)

# ── Processamento e exibição dos resultados ─────────────────────────────────

if submitted:
    with st.spinner("Analisando seu perfil e buscando dados do mercado..."):
        respostas = map_respostas(
            prazo, risco, objetivo, fluxo, controle, liquidez, reserva,
            idade, despesas, valor, patrimonio, renda, dividas,
            conhecimento, experiencia, dependentes, aporte, emocional,
            ir_tipo, carteira, meta, cap_inicial, aporte_mensal
        )
        resultado = gerar_recomendacao(respostas)
    
    st.balloons()
    st.success("✅ Recomendação gerada com sucesso!")
    
    col_metric1, col_metric2, col_metric3, col_metric4 = st.columns(4)
    with col_metric1:
        st.metric("🎯 Perfil", resultado["risco_label"])
    with col_metric2:
        st.metric("📌 Produto", resultado["perfil_display"][:20] + "...")
    with col_metric3:
        st.metric("📈 Taxa Estimada", f"{resultado['taxa_perfil']*100:.2f}% a.a.")
    with col_metric4:
        st.metric("💰 IR", f"{resultado['aliq']*100:.0f}% sobre ganhos")
    
    st.divider()
    
    # ── Alocação do portfólio ────────────────────────────────────────────────
    st.subheader("📊 Alocação do Portfólio")
    portfolio = resultado["portfolio"]
    if portfolio:
        labels = [_disp(k) for k, v in portfolio.items() if v > 0]
        values = [v for v in portfolio.values() if v > 0]
        
        fig = go.Figure(data=[go.Pie(
            labels=labels,
            values=values,
            hole=0.4,
            textinfo='label+percent',
            textposition='auto',
            marker=dict(colors=px.colors.qualitative.Set3),
            hovertemplate='<b>%{label}</b><br>Alocação: %{percent}<br>Valor: %{value:.1f}%<extra></extra>'
        )])
        fig.update_layout(height=400, margin=dict(t=20, b=20, l=20, r=20), showlegend=False, title="Distribuição por classe de ativo")
        st.plotly_chart(fig, use_container_width=True)
        
        df_portfolio = pd.DataFrame({"Classe": labels, "Alocação (%)": values})
        st.dataframe(df_portfolio, hide_index=True, use_container_width=True)
    
    st.divider()
    
    # ── Detalhes do produto ──────────────────────────────────────────────────
    st.subheader("📋 Onde Investir")
    info = resultado["info"]
    col_info1, col_info2, col_info3 = st.columns(3)
    with col_info1:
        st.metric("🛡️ Garantia", info.get("garantia", "N/A"))
    with col_info2:
        st.metric("💰 Imposto", info.get("imposto", "N/A"))
    with col_info3:
        st.metric("🏦 Onde abrir", info.get("onde", "N/A"))
    
    with st.expander("📌 O que comprar dentro desta categoria", expanded=False):
        for item in info.get("o_que_comprar", []):
            st.write(f"• {item}")
    
    st.divider()
    
    # ── Projeções ─────────────────────────────────────────────────────────────
    st.subheader("📈 Projeção de Crescimento")
    st.caption(f"Taxa estimada: **{resultado['taxa_perfil']*100:.2f}% a.a. bruto** | IR: **{resultado['aliq']*100:.0f}%**")
    
    cap_inicial = resultado["cap_inicial"]
    aporte_mensal = resultado["aporte_mensal"]
    taxa = resultado["taxa_perfil"]
    aliq = resultado["aliq"]
    pgbl = resultado["pgbl"]
    taxa_pess = resultado["taxa_pess"]
    
    anos_lista = [1, 2, 5, 10, 20, 30]
    dados_proj = []
    for anos in anos_lista:
        vf_b = _vf_bruto(cap_inicial, aporte_mensal, taxa, anos)
        vf_l = _vf_liquido(cap_inicial, aporte_mensal, taxa, anos, aliq, pgbl)
        vf_r = _vf_real(vf_l, ipca, anos)
        vf_p = _vf_liquido(cap_inicial, aporte_mensal, taxa_pess, anos, aliq, pgbl)
        dados_proj.append({
            "Anos": anos,
            "VF Bruto": f"R$ {vf_b:,.0f}",
            "VF Líquido": f"R$ {vf_l:,.0f}",
            "VF Real (poder de compra)": f"R$ {vf_r:,.0f}",
            "Pessimista Líq.": f"R$ {vf_p:,.0f}"
        })
    df_proj = pd.DataFrame(dados_proj)
    st.dataframe(df_proj, hide_index=True, use_container_width=True)
    
    # Gráfico de projeção
    fig_proj = go.Figure()
    anos_cont = list(range(1, 31))
    vf_bruto_cont = [_vf_bruto(cap_inicial, aporte_mensal, taxa, a) for a in anos_cont]
    vf_liquido_cont = [_vf_liquido(cap_inicial, aporte_mensal, taxa, a, aliq, pgbl) for a in anos_cont]
    vf_real_cont = [_vf_real(vf_liquido_cont[i], ipca, anos_cont[i]) for i in range(len(anos_cont))]
    
    fig_proj.add_trace(go.Scatter(
        x=anos_cont, y=vf_bruto_cont,
        mode='lines+markers',
        name='Bruto',
        line=dict(color='blue', width=2)
    ))
    fig_proj.add_trace(go.Scatter(
        x=anos_cont, y=vf_liquido_cont,
        mode='lines+markers',
        name='Líquido (após IR)',
        line=dict(color='green', width=2)
    ))
    fig_proj.add_trace(go.Scatter(
        x=anos_cont, y=vf_real_cont,
        mode='lines+markers',
        name='Real (poder de compra)',
        line=dict(color='red', width=2)
    ))
    fig_proj.update_layout(
        title="Evolução do Patrimônio ao Longo do Tempo",
        xaxis_title="Anos",
        yaxis_title="Valor (R$)",
        hovermode="x unified",
        height=400,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    st.plotly_chart(fig_proj, use_container_width=True)
    
    st.divider()
    
    # ── Ativos Sugeridos ──────────────────────────────────────────────────────
    ativos = resultado["ativos"]
    if ativos:
        st.subheader("🎯 Ativos Sugeridos para seu Perfil")
        tabs = st.tabs(list(ativos.keys()))
        for tab, classe in zip(tabs, ativos.keys()):
            with tab:
                lista = ativos[classe]
                if not lista:
                    st.info("Nenhum ativo encontrado para esta classe.")
                    continue
                
                df_ativos = pd.DataFrame(lista)
                df_ativos['score'] = df_ativos['score'].round(0).astype(int)
                df_ativos['motivos'] = df_ativos['motivos'].apply(lambda x: ' | '.join(x) if x else '')
                
                # Renomeia colunas de forma segura
                colunas = {}
                for old, new in [('ticker', 'Ticker'), ('nome', 'Nome'), ('preco', 'Preço'),
                                 ('score', 'Score'), ('motivos', 'Destaques')]:
                    if old in df_ativos.columns:
                        colunas[old] = new
                if colunas:
                    df_ativos = df_ativos.rename(columns=colunas)
                
                # Formata Preço se existir
                if 'Preço' in df_ativos.columns:
                    df_ativos['Preço'] = df_ativos['Preço'].apply(lambda x: f"R$ {x:,.2f}" if x else "")
                
                # Seleciona colunas existentes para exibição
                colunas_exibir = ['Ticker', 'Nome', 'Preço', 'Score', 'Destaques']
                colunas_existentes = [c for c in colunas_exibir if c in df_ativos.columns]
                if not colunas_existentes:
                    st.dataframe(df_ativos, hide_index=True, use_container_width=True)
                else:
                    st.dataframe(df_ativos[colunas_existentes], hide_index=True, use_container_width=True)
    else:
        st.info("Nenhuma classe de ativo com alocação significativa para sugerir.")
    
    st.divider()
    
    # ── Avisos ─────────────────────────────────────────────────────────────────
    avisos = resultado["avisos"]
    if avisos:
        st.subheader("⚠️ Observações e Ajustes")
        for aviso in avisos:
            if "⚠️" in aviso or "🚨" in aviso:
                st.warning(aviso)
            elif "✅" in aviso:
                st.success(aviso)
            else:
                st.info(aviso)
    
    # ── Detalhes do perfil ──────────────────────────────────────────────────
    with st.expander("📋 Detalhes completos do perfil"):
        map_display = {
            "Prazo": {1: "Curto (até 2a)", 2: "Médio (2-5a)", 3: "Longo (5a+)"},
            "Risco emocional": {1: "Conservador", 2: "Moderado", 3: "Agressivo"},
            "Objetivo": {1: "Reserva", 2: "Crescimento", 3: "Aposentadoria"},
            "Fluxo": {1: "Renda passiva", 2: "Acúmulo"},
            "Controle": {1: "Gestão própria", 2: "Delegar"},
            "Liquidez": {1: "Sim", 2: "Não"},
            "Reserva emergência": {1: "Sem reserva", 2: "Parcial", 3: "Completa"},
            "Idade": {1: "Jovem (≤35)", 2: "Adulto (36-55)", 3: "Sênior (55+)"},
            "Despesas fixas": {1: "Nenhuma", 2: "Baixas", 3: "Altas"},
            "Valor disponível": {1: "Até R$1k", 2: "R$1k-10k", 3: ">R$10k"},
            "% do patrimônio": {1: "<25%", 2: "25-75%", 3: ">75%"},
            "Renda": {1: "CLT", 2: "PJ contratado", 3: "Autônomo", 4: "Sem renda"},
            "Dívidas": {1: "Juros altos", 2: "Juros baixos", 3: "Sem dívidas"},
            "Conhecimento": {1: "Iniciante", 2: "Intermediário", 3: "Experiente"},
            "Dependentes": {1: "Nenhum", 2: "Um", 3: "Dois+"},
            "Aporte": {1: "Único (Lump Sum)", 2: "Mensal (DCA)"},
            "Declaração IR": {1: "Completa", 2: "Simplificada", 3: "Não declara"},
            "Carteira atual": {1: "Sem carteira", 2: "Conservadora", 3: "Moderada", 4: "Arrojada"},
        }
        resp = respostas
        resumo = {
            "Prazo": map_display["Prazo"].get(resp["prazo"], "N/A"),
            "Risco efetivo": resultado["risco_label"],
            "Risco emocional": map_display["Risco emocional"].get(resp["emocional"], "N/A"),
            "Objetivo": map_display["Objetivo"].get(resp["objetivo"], "N/A"),
            "Fluxo": map_display["Fluxo"].get(resp["fluxo"], "N/A"),
            "Controle": map_display["Controle"].get(resp["controle"], "N/A"),
            "Liquidez": map_display["Liquidez"].get(resp["liquidez"], "N/A"),
            "Reserva emergência": map_display["Reserva emergência"].get(resp["reserva_emerg"], "N/A") + f" (rec.: {resultado['meses_res']} meses)",
            "Idade": map_display["Idade"].get(resp["idade"], "N/A"),
            "Despesas fixas": map_display["Despesas fixas"].get(resp["despesas"], "N/A"),
            "Valor disponível": map_display["Valor disponível"].get(resp["faixa_valor"], "N/A"),
            "% do patrimônio": map_display["% do patrimônio"].get(resp["patrim_pct"], "N/A"),
            "Renda": map_display["Renda"].get(resp["renda"], "N/A"),
            "Dívidas": map_display["Dívidas"].get(resp["dividas"], "N/A"),
            "Conhecimento": map_display["Conhecimento"].get(resp["conhecimento"], "N/A"),
            "Experiência": ", ".join(resp["experiencia"]) if resp["experiencia"] else "Nenhuma",
            "Dependentes": map_display["Dependentes"].get(resp["dependentes"], "N/A"),
            "Aporte": map_display["Aporte"].get(resp["aporte"], "N/A"),
            "Declaração IR": map_display["Declaração IR"].get(resp["ir_tipo"], "N/A"),
            "Carteira atual": map_display["Carteira atual"].get(resp["carteira_atual"], "N/A"),
            "Capital inicial": f"R$ {resp['cap_inicial']:,.2f}",
            "Aporte mensal": f"R$ {resp['aporte_mensal']:,.2f}",
        }
        df_resumo = pd.DataFrame(list(resumo.items()), columns=["Critério", "Resposta"])
        st.dataframe(df_resumo, hide_index=True, use_container_width=True)
    
    # ── Exportar ──────────────────────────────────────────────────────────────
    st.divider()
    col_export1, col_export2 = st.columns(2)
    with col_export1:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_data = {
            "recomendacao": resultado["perfil_exibido"],
            "portfolio": resultado["portfolio"],
            "nivel_risco": resultado["nivel_risco"],
            "taxa_perfil": resultado["taxa_perfil"],
            "avisos": resultado["avisos"],
        }
        json_str = json.dumps(export_data, ensure_ascii=False, indent=2)
        st.download_button(
            label="📥 Baixar resultado (JSON)",
            data=json_str,
            file_name=f"recomendacao_{timestamp}.json",
            mime="application/json",
            use_container_width=True
        )
    with col_export2:
        st.caption("Os dados são gerados em tempo real com base nas taxas atuais do mercado.")