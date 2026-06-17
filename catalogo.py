# O catálogo completo de produtos: o que comprar dentro de cada categoria, 
# garantias, impostos e onde abrir conta. Também calcula a alíquota correta para cada produto.

from typing import Dict, Tuple
from config import IR_RF, IR_ACOES, IR_VGBL, IR_PGBL, IR_FII
from categorias import RK, _RK_DISPLAY

_PROD: Dict[str, dict] = {
    RK.RF: {
        "o_que_comprar": [
            "Tesouro Selic — mais seguro do Brasil, garantia do governo, liquidez D+1",
            "CDB de banco digital com liquidez diária — busque 100%+ do CDI (ex: Nubank, Inter, C6)",
            "LCI/LCA de banco sólido — isento de IR para PF (verifique carência mínima)",
        ],
        "garantia": "CDB/LCI/LCA: FGC até R$250k por CPF por instituição. Tesouro: governo federal.",
        "imposto":  "CDB: 15% sobre GANHOS (>720 dias). LCI/LCA: ISENTO. Tesouro Selic: 15% sobre ganhos.",
        "onde":     "tesourodireto.gov.br, Nubank, Inter, C6, XP, Rico.",
    },
    RK.RF_LIQUIDEZ: {
        "o_que_comprar": [
            "Tesouro Selic (liquidez D+1, segurança máxima)",
            "CDB com liquidez diária de banco digital (100%+ CDI)",
        ],
        "garantia": "Tesouro: governo federal. CDB: FGC até R$250k.",
        "imposto":  "15% sobre GANHOS (>720 dias).",
        "onde":     "tesourodireto.gov.br, bancos digitais.",
    },
    RK.RF_RESERVA: {
        "o_que_comprar": [
            "PASSO 1: Abra conta no Tesouro Direto via corretora (tesourodireto.gov.br)",
            "PASSO 2: Invista APENAS em Tesouro Selic até ter 3-6 meses de gastos guardados",
            "PASSO 3: Com a reserva completa, refaça este questionário para diversificar",
        ],
        "garantia": "Garantia do governo federal (a mais alta disponível no Brasil).",
        "imposto":  "15% sobre GANHOS (>720 dias).",
        "onde":     "tesourodireto.gov.br",
    },
    RK.RF_IPCA: {
        "o_que_comprar": [
            "Tesouro IPCA+ com juros semestrais (pagamento a cada 6 meses — renda passiva)",
            "CDB com pagamento de juros mensais ou semestrais",
            "Debêntures incentivadas com cupom semestral (isentas de IR para PF)",
        ],
        "garantia": "Tesouro: governo federal. Debêntures: sem FGC (risco de crédito).",
        "imposto":  "Tesouro IPCA+: 15% sobre ganhos. Debêntures incentivadas: ISENTO.",
        "onde":     "Tesouro Direto, corretoras.",
    },
    RK.RF_SELIC_CDB: {
        "o_que_comprar": [
            "Tesouro Selic — mais seguro do Brasil (garantia governo federal, liquidez D+1)",
            "CDB com liquidez diária de banco digital — busque 100%+ do CDI",
        ],
        "garantia": "Tesouro: governo federal. CDB: FGC até R$250k por CPF por instituição.",
        "imposto":  "15% sobre GANHOS (>720 dias). Resgates antes de 180 dias: 22,5%.",
        "onde":     "tesourodireto.gov.br, Nubank, Inter, PicPay, C6.",
    },
    RK.RF_REAVALIE: {
        "o_que_comprar": [
            "Tesouro Selic até reavaliar o prazo correto para aposentadoria",
            "Com prazo mais longo confirmado, refaça este questionário para Previdência Privada",
        ],
        "garantia": "Governo federal.",
        "imposto":  "15% sobre GANHOS (>720 dias).",
        "onde":     "tesourodireto.gov.br",
    },
    RK.RF_EQUILIBRIO: {
        "o_que_comprar": [
            "Tesouro IPCA+ (proteção contra inflação, âncora de longo prazo)",
            "Fundo Multimercado de baixa volatilidade (retorno CDI+ sem exposição total ao mercado)",
        ],
        "garantia": "Tesouro: governo federal. Fundos: patrimônio separado.",
        "imposto":  "15% sobre ganhos.",
        "onde":     "tesourodireto.gov.br, corretoras.",
    },
    RK.FUNDOS: {
        "o_que_comprar": [
            "Fundo Multimercado de gestora independente reconhecida (busque CDI+ com volatilidade baixa)",
            "Fundo de Renda Fixa Ativo (CDI+ com gestão ativa — taxa de admin <1% a.a.)",
            "Fundo de Debêntures Incentivadas (isento de IR para PF)",
        ],
        "garantia": "Sem FGC. Patrimônio separado da gestora por lei.",
        "imposto":  "15% sobre ganhos (>720 dias). Come-cotas semestral (maio/nov) — reduz rentabilidade efetiva.",
        "onde":     "XP, BTG, Warren, Órama, Rico.",
    },
    RK.FUNDOS_DIVERSIF: {
        "o_que_comprar": [
            "Fundo Multimercado moderado (complementa a renda fixa que você já tem)",
            "Fundo de ações passivo com ETF (BOVA11) para exposição gradual à renda variável",
        ],
        "garantia": "Sem FGC. Patrimônio separado.",
        "imposto":  "15% sobre ganhos. Come-cotas semestral.",
        "onde":     "XP, BTG, Warren.",
    },
    RK.FUNDOS_MULTI: {
        "o_que_comprar": [
            "Fundos macro de retorno absoluto (buscam CDI+ independente do mercado)",
            "Taxa de administração <1,5% a.a. e performance de 20% sobre CDI",
            "Gestoras reconhecidas: SPX, Verde, Ibiúna, Kinea, Kadima",
        ],
        "garantia": "Sem FGC. Patrimônio separado.",
        "imposto":  "15% sobre ganhos. Come-cotas em maio e novembro.",
        "onde":     "XP, BTG, Warren, Órama.",
    },
    RK.FUNDOS_RF: {
        "o_que_comprar": [
            "Fundo de Renda Fixa DI (acompanha CDI, baixo risco — taxa admin <0,5% a.a.)",
            "VGBL de renda fixa para objetivo previdência (IR mais eficiente no longo prazo)",
        ],
        "garantia": "Sem FGC para fundos. FGS para previdência.",
        "imposto":  "15% sobre ganhos. Come-cotas semestral para fundos de RF.",
        "onde":     "Corretoras.",
    },
    RK.FUNDOS_RF_LIQ: {
        "o_que_comprar": [
            "Fundo DI com liquidez D+0 ou D+1 (acompanha CDI diariamente)",
            "Fundo de Renda Fixa Simples (sem come-cotas, taxa admin muito baixa)",
        ],
        "garantia": "Sem FGC.",
        "imposto":  "15% sobre ganhos. Come-cotas em maio e novembro.",
        "onde":     "Corretoras.",
    },
    RK.FUNDOS_ACOES: {
        "o_que_comprar": [
            "ETF passivo BOVA11 (taxa ~0,1% a.a. — bate a maioria dos fundos ativos no longo prazo)",
            "Fundo de ações ativo de gestora com track record >5 anos consistente",
            "Fundo Small Caps para maior potencial de crescimento (maior volatilidade)",
        ],
        "garantia": "Sem FGC. Patrimônio separado.",
        "imposto":  "15% sobre ganhos. Fundos de ações NÃO têm come-cotas.",
        "onde":     "XP, BTG, Rico, Clear.",
    },
    RK.FUNDOS_ACOES_ETF: {
        "o_que_comprar": [
            "BOVA11 — ETF Ibovespa (começa com qualquer valor, taxa ~0,1% a.a.)",
            "IVVB11 — ETF S&P500 em BRL (diversificação internacional automática)",
            "SMALL11 — ETF Small Caps brasileiras (maior potencial, maior volatilidade)",
        ],
        "garantia": "Sem FGC. Patrimônio separado.",
        "imposto":  "15% sobre ganho de capital (sem come-cotas).",
        "onde":     "Qualquer corretora com home broker.",
        "dica":     "ETFs são a opção mais simples, barata e diversificada para iniciantes.",
    },
    RK.FUNDOS_ACOES_DCA: {
        "o_que_comprar": [
            "BOVA11 comprado mensalmente (DCA automático no Ibovespa)",
            "Fundo de ações passivo com taxa <0,3% a.a. com aportes mensais programados",
        ],
        "garantia": "Sem FGC.",
        "imposto":  "15% sobre ganhos.",
        "onde":     "Qualquer corretora.",
    },
    RK.FUNDOS_CRIPTO: {
        "o_que_comprar": [
            "HASH11 — ETF de cripto diversificado (BTC, ETH e outras — regulamentado CVM)",
            "BITH11 — ETF de Bitcoin puro (regulamentado, sem custódia própria necessária)",
            "Evite exchange direta se for iniciante em cripto",
        ],
        "garantia": "Sem garantia. Alta volatilidade — quedas de 50-80% são históricas.",
        "imposto":  "15% sobre ganho de capital. Sem isenção de R$20k/mês.",
        "onde":     "Qualquer corretora com home broker.",
        "dica":     "ETFs de cripto são mais seguros que compra direta: sem risco de exchange, sem custódia própria.",
    },
    RK.FIIS: {
        "o_que_comprar": [
            "FIIs de tijolo: HGLG11 (logística), XPML11 (shopping), BRCO11 (galpões)",
            "FIIs de papel: KNCR11, MXRF11 (recebíveis — menor volatilidade que tijolo)",
            "BCFF11 — FOF de FIIs (fundo de fundos — diversificação automática)",
        ],
        "garantia": "Sem garantia. Risco de vacância e variação de mercado.",
        "imposto":  "Dividendos mensais ISENTOS de IR para PF. Ganho de capital na venda: 20%.",
        "onde":     "Qualquer corretora com home broker.",
        "dica":     "Combine FIIs de papel (estabilidade) e tijolo (crescimento) para equilibrar risco e renda.",
    },
    RK.FIIS_DEL: {
        "o_que_comprar": [
            "FIIs de papel: KNCR11, MXRF11 (recebíveis — renda estável e previsível)",
            "FIIs de tijolo: HGLG11 (logística), XPML11 (shopping)",
            "BCFF11 — FOF de FIIs (diversificação automática delegada ao gestor)",
        ],
        "garantia": "Sem garantia.",
        "imposto":  "Dividendos mensais ISENTOS de IR para PF. Ganho de capital na venda: 20%.",
        "onde":     "Qualquer corretora.",
    },
    RK.RV: {
        "o_que_comprar": [
            "BOVA11 — ETF do Ibovespa (87+ maiores empresas brasileiras em um só ativo)",
            "IVVB11 — ETF do S&P500 em BRL (500 maiores empresas americanas)",
            "Ações de empresas líderes com histórico de dividendos (bancos, utilities, commodities)",
            "FIIs — dividendos mensais isentos de IR para PF (HGLG11, MXRF11, XPML11)",
        ],
        "garantia": "Sem garantia. Pode perder parte ou todo o capital.",
        "imposto":  "15% sobre ganho de capital. FIIs: dividendos isentos, ganho de capital 20%. Ações: isento em vendas até R$20k/mês.",
        "onde":     "Qualquer corretora com home broker (XP, Clear, Rico, BTG, Modalmais).",
    },
    RK.RV_DCA: {
        "o_que_comprar": [
            "ETFs comprados todo mês na mesma data, independente do preço (BOVA11, IVVB11)",
            "Carteira de 5-10 ações diversificadas com aportes mensais fixos",
            "FIIs com reinvestimento dos dividendos recebidos",
        ],
        "garantia": "Sem garantia.",
        "imposto":  "15% sobre ganho de capital. Isenção em vendas de ações até R$20k/mês.",
        "onde":     "Qualquer corretora.",
        "dica":     "DCA: compre mensalmente um valor fixo. Reduz o risco de entrar no pior momento.",
    },
    RK.RV_CRIPTO: {
        "o_que_comprar": [
            "80%+ em ações/ETFs diversificados (BOVA11, IVVB11, SMALL11)",
            "Até 15% em cripto via ETF regulamentado: HASH11 (diversificado), BITH11 (Bitcoin puro)",
            "Cripto diretamente apenas em exchange regulamentada e com carteira própria (cold wallet)",
        ],
        "garantia": "Sem garantia. Cripto: risco de perda total, sem FGC ou seguro.",
        "imposto":  "Ações/ETFs: 15% sobre ganho de capital. Cripto: 15% sobre ganho mensal acima de R$35k.",
        "onde":     "Corretoras para ações/ETFs. Exchanges regulamentadas (Mercado Bitcoin, Binance Brasil).",
    },
    RK.RV_COMPL: {
        "o_que_comprar": [
            "IVVB11 (diversificação internacional — complementa carteira já exposta ao Brasil)",
            "Small Caps (SMALL11) para maior potencial de crescimento como complemento",
        ],
        "garantia": "Sem garantia.",
        "imposto":  "15% sobre ganho de capital.",
        "onde":     "Qualquer corretora.",
    },
    RK.PREV_PGBL: {
        "o_que_comprar": [
            "PGBL com tabela regressiva (10% no longo prazo → máxima eficiência fiscal)",
            "Taxa de admin <1% a.a., ZERO taxa de carregamento",
            "Gestoras: Icatu, Zurich, XP Seguros, Brasilprev",
        ],
        "garantia": "Coberto pelo FGS (Fundo Garantidor de Seguros) para EAPC.",
        "imposto":  "10% sobre o VALOR TOTAL do resgate (longo prazo). IR incide sobre contribuições + ganhos.",
        "onde":     "XP, corretoras, plataformas de previdência.",
        "dica":     "PGBL só vale para quem declara IR pelo modelo COMPLETO. Dedução: até 12% da renda bruta anual.",
    },
    RK.PREV_VGBL: {
        "o_que_comprar": [
            "VGBL com tabela regressiva (10% sobre GANHOS no longo prazo)",
            "Taxa de admin <1% a.a., zero taxa de carregamento",
            "Gestoras: Icatu, Zurich, XP Seguros",
        ],
        "garantia": "Coberto pelo FGS.",
        "imposto":  "10% sobre os GANHOS apenas (longo prazo).",
        "onde":     "Corretoras e plataformas de previdência.",
    },
    RK.PREV_PGBL_RF: {
        "o_que_comprar": [
            "50-60% em PGBL com tabela regressiva (deduz até 12% da renda bruta no IR)",
            "40-50% em Tesouro IPCA+ com vencimento próximo da sua aposentadoria",
            "Taxa de admin PGBL <1% a.a., zero taxa de carregamento",
        ],
        "garantia": "FGS para previdência. Tesouro IPCA+: governo federal.",
        "imposto":  "PGBL: 10% sobre VALOR TOTAL do resgate. Tesouro IPCA+: 15% sobre ganhos.",
        "onde":     "tesourodireto.gov.br + corretoras com plataforma de previdência.",
        "dica":     "Válido apenas para quem declara IR pelo modelo COMPLETO.",
    },
    RK.PREV_VGBL_RF: {
        "o_que_comprar": [
            "50-60% em VGBL com tabela regressiva (IR só sobre os ganhos)",
            "40-50% em Tesouro IPCA+ com vencimento próximo da sua aposentadoria",
            "Taxa de admin VGBL <1% a.a., zero taxa de carregamento",
        ],
        "garantia": "FGS para previdência. Tesouro IPCA+: governo federal.",
        "imposto":  "VGBL: 10% sobre GANHOS. Tesouro IPCA+: 15% sobre ganhos.",
        "onde":     "tesourodireto.gov.br + corretoras com plataforma de previdência.",
    },
    RK.COE: {
        "o_que_comprar": [
            "COE de proteção total (100% capital garantido + participação em índice: S&P500, ouro, câmbio)",
            "COE de proteção parcial (80-95%) com maior potencial de retorno — leia o cenário de stress",
            "Prefira emissores com baixo risco de crédito (grandes bancos) — COE não tem FGC",
        ],
        "garantia": "SEM FGC. Garantia depende exclusivamente da solidez do banco emissor.",
        "imposto":  "IR regressivo sobre ganhos: 22,5% (<180d) → 15% (>720d). Igual à renda fixa.",
        "onde":     "XP, BTG, Genial, Órama. Compare no Yubb ou Investidor10.",
        "dica":     "Leia SEMPRE o cenário de stress. Capital mínimo típico: R$5.000-R$10.000.",
    },
    RK.ESTRUTURADOS: {
        "o_que_comprar": [
            "CRI (Certificado de Recebíveis Imobiliários) — isento de IR para PF",
            "CRA (Certificado de Recebíveis do Agronegócio) — isento de IR para PF",
            "Debêntures incentivadas de infraestrutura — isento de IR para PF (Lei 12.431/2011)",
            "Letra Financeira (LF) — emitida por bancos, sem FGC mas com taxas superiores ao CDB",
        ],
        "garantia": "SEM FGC. Risco de crédito do emissor. Verifique rating (AA, A, BBB).",
        "imposto":  "CRA/CRI/Debêntures incentivadas: ISENTO de IR para PF. LF: 15% sobre ganhos.",
        "onde":     "XP, BTG, Genial, Órama. Mínimo típico: R$1.000-R$5.000.",
        "dica":     "Isenção de IR equivale a ~3-4% de rentabilidade extra. Verifique liquidez: muitos sem mercado secundário.",
    },
    RK.CAMBIO: {
        "o_que_comprar": [
            "DOLLAR11 — ETF que replica o dólar americano na B3 (proteção cambial direta e simples)",
            "IVVB11 — ETF do S&P500 em BRL (dupla exposição: mercado americano + câmbio)",
            "Conta internacional (Nomad, Avenue, Wise) — invista em ETFs americanos (VOO, QQQ)",
            "BDRs de empresas globais (AAPL34, MSFT34, AMZO34) — negociados na B3 em reais",
        ],
        "garantia": "Sem FGC. ETFs B3: patrimônio separado. Conta internacional: SIPC (EUA) até USD 500k.",
        "imposto":  "DOLLAR11/ETFs B3: 15% sobre ganho de capital. Conta internacional: 15% declarado (GCME).",
        "onde":     "Qualquer corretora para ETFs B3. Nomad, Avenue ou Wise para conta internacional.",
        "dica":     "Câmbio é diversificação, não especulação. Mantenha entre 10-20% como proteção contra desvalorização do real.",
    },
    RK.OFERTAS: {
        "o_que_comprar": [
            "IPO: compra de ações antes da estreia na B3 — alto potencial, alto risco",
            "Follow-on: empresa já listada emite novas ações — geralmente com desconto",
            "Debêntures em emissão primária: título de dívida corporativa com taxa definida",
            "CRI/CRA em oferta primária: acesso a taxas melhores que no mercado secundário",
        ],
        "garantia": "Sem garantia. Lock-up pode impedir venda imediata pós-estreia.",
        "imposto":  "Ações: 15% sobre ganho de capital (isenção em vendas até R$20k/mês). Debêntures: conforme tipo.",
        "onde":     "XP, BTG, Itaú BBA — reserva via home broker ou assessor.",
        "dica":     "Leia o prospecto completo. Reserve apenas o que pode perder — IPOs podem cair forte nos primeiros dias.",
    },
}


def _aliq(rk: str) -> Tuple[float, bool]:
    if rk in (RK.PREV_PGBL, RK.PREV_PGBL_RF):   return IR_PGBL,  True
    if rk in (RK.PREV_VGBL, RK.PREV_VGBL_RF):   return IR_VGBL,  False
    if rk == RK.ESTRUTURADOS:                     return 0.0,      False
    if rk in (RK.RF_IPCA, RK.RF, RK.RF_LIQUIDEZ,
              RK.RF_SELIC_CDB, RK.RF_RESERVA,
              RK.RF_EQUILIBRIO, RK.FUNDOS_RF,
              RK.FUNDOS_RF_LIQ, RK.FUNDOS_MULTI,
              RK.FUNDOS, RK.FUNDOS_DIVERSIF):     return IR_RF,    False
    if rk in (RK.FIIS, RK.FIIS_DEL):             return IR_FII,   False
    return IR_ACOES, False


def _get_prod(rk: str) -> dict:
    """Lookup O(1) direto via chave RK."""
    return _PROD.get(rk, {
        "o_que_comprar": ["Consulte um assessor certificado (CFP/CEA/CNPI)."],
        "garantia": "Varia.", "imposto": "Varia.",
        "onde": "Corretoras regulamentadas pela CVM.",
    })


def _disp(rk: str) -> str:
    """Retorna o texto de exibição para uma chave RK."""
    return _RK_DISPLAY.get(rk, rk)