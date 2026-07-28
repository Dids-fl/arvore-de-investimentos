# core/catalogo.py
"""
Catálogo de produtos por categoria (RK).

Este módulo era importado por main.py, app.py e core/__init__.py
(`from core.catalogo import _get_prod, _disp, _aliq`) mas não existia no
repositório — o projeto não rodava sem ele. Reconstruído aqui de forma
consistente com o restante do código (config.py para alíquotas de IR,
core/categorias.py para nomes de exibição e nível de risco).

Funções expostas
─────────────────
  _disp(rk)     → nome de exibição amigável de uma categoria (str)
  _get_prod(rk) → dict com orientação prática: o que comprar, garantia,
                   tributação e onde abrir, para a categoria informada
  _aliq(rk)     → (aliquota_ir: float, pgbl: bool) aplicável na categoria,
                   usado por calculos.py para simular o valor líquido no
                   resgate (`_vf_liquido`)
"""

from typing import Dict, Tuple

from core.categorias import RK, _RK_DISPLAY
from config import IR_RF, IR_ACOES, IR_VGBL, IR_PGBL, IR_LCI, IR_FII


# ── Nome de exibição ──────────────────────────────────────────────────────────

def _disp(rk: str) -> str:
    """Nome de exibição amigável de uma categoria. Sem entrada conhecida,
    devolve a própria chave (nunca quebra)."""
    return _RK_DISPLAY.get(rk, rk)


# ── Alíquota de IR aplicável por categoria ────────────────────────────────────
# (aliquota, pgbl) — pgbl=True significa que o IR incide sobre o valor bruto
# total no resgate (não só sobre o ganho), como ocorre no regime regressivo/
# progressivo do PGBL, já que as contribuições foram deduzidas na declaração.

_ALIQ_PRODUTO: Dict[str, Tuple[float, bool]] = {
    # Renda fixa tributada (IR regressivo sobre o ganho)
    RK.RF:              (IR_RF, False),
    RK.RF_LIQUIDEZ:      (IR_RF, False),
    RK.RF_RESERVA:       (IR_RF, False),
    RK.RF_IPCA:          (IR_RF, False),
    RK.RF_SELIC_CDB:     (IR_RF, False),
    RK.RF_REAVALIE:      (IR_RF, False),
    RK.RF_EQUILIBRIO:    (IR_RF, False),
    RK.FUNDOS_RF:        (IR_RF, False),
    RK.FUNDOS_RF_LIQ:    (IR_RF, False),
    # Fundos (tratados como RF para fins de simulação de IR — "come-cotas")
    RK.FUNDOS:           (IR_RF, False),
    RK.FUNDOS_DIVERSIF:  (IR_RF, False),
    RK.FUNDOS_MULTI:     (IR_RF, False),
    # Renda variável / ações / ETFs / cripto
    RK.FUNDOS_ACOES:     (IR_ACOES, False),
    RK.FUNDOS_ACOES_ETF: (IR_ACOES, False),
    RK.FUNDOS_ACOES_DCA: (IR_ACOES, False),
    RK.FUNDOS_CRIPTO:    (IR_ACOES, False),
    RK.RV:               (IR_ACOES, False),
    RK.RV_DCA:           (IR_ACOES, False),
    RK.RV_CRIPTO:        (IR_ACOES, False),
    RK.RV_COMPL:         (IR_ACOES, False),
    # FIIs — isentos de IR sobre dividendos mensais (pessoa física, com
    # regras de negociação), mas para fins de simulação de valor futuro
    # usa-se a alíquota sobre ganho de capital na venda de cotas.
    RK.FIIS:             (IR_FII, False),
    RK.FIIS_DEL:         (IR_FII, False),
    # Previdência privada
    RK.PREV_PGBL:        (IR_PGBL, True),
    RK.PREV_PGBL_RF:     (IR_PGBL, True),
    RK.PREV_VGBL:        (IR_VGBL, False),
    RK.PREV_VGBL_RF:     (IR_VGBL, False),
    # Outros
    RK.COE:              (IR_RF, False),
    RK.ESTRUTURADOS:     (IR_LCI, False),   # CRA/CRI/Debêntures incentivadas: isentos de IR para PF
    RK.CAMBIO:           (IR_ACOES, False),
    RK.OFERTAS:          (IR_ACOES, False),
}


def _aliq(rk: str) -> Tuple[float, bool]:
    """Alíquota de IR (decimal) e flag PGBL aplicáveis à categoria.
    Sem entrada conhecida, assume o tratamento conservador de renda fixa."""
    return _ALIQ_PRODUTO.get(rk, (IR_RF, False))


# ── Catálogo prático: o que comprar / garantia / imposto / onde ──────────────

def _prod(o_que_comprar, garantia, imposto, onde) -> dict:
    return {
        "o_que_comprar": o_que_comprar,
        "garantia": garantia,
        "imposto": imposto,
        "onde": onde,
    }


_FGC = "FGC até R$ 250 mil por CPF/instituição (limite de R$ 1 milhão a cada 4 anos)"
_IR_REGRESSIVO_RF = "IR regressivo sobre o ganho: 22,5% (até 180d) a 15% (acima de 720d)"
_IR_ACOES_SWING = "15% sobre o ganho em operações comuns (day trade: 20%); isenção até R$20 mil/mês vendidos em ações"
_IR_FII_TXT = "Isento sobre dividendos mensais (PF, cotas negociadas em bolsa); 20% sobre ganho de capital na venda"
_CORRETORAS = "Qualquer corretora de valores habilitada na B3 (ex.: corretoras de bancos ou independentes)"

_CATALOGO: Dict[str, dict] = {
    RK.RF: _prod(
        ["Tesouro Selic", "CDB de banco/corretora com liquidez diária", "Fundos DI"],
        _FGC + " (exceto Tesouro Direto, que tem garantia do Tesouro Nacional)",
        _IR_REGRESSIVO_RF,
        "Tesouro Direto (tesourodireto.com.br) ou qualquer corretora",
    ),
    RK.RF_LIQUIDEZ: _prod(
        ["Tesouro Selic", "CDB com liquidez diária"],
        "Tesouro Nacional (Tesouro Selic) ou " + _FGC,
        _IR_REGRESSIVO_RF,
        "Tesouro Direto ou corretora",
    ),
    RK.RF_RESERVA: _prod(
        ["Tesouro Selic 100% (prioridade: montar reserva de emergência)"],
        "Garantia do Tesouro Nacional",
        _IR_REGRESSIVO_RF,
        "Tesouro Direto (tesourodireto.com.br)",
    ),
    RK.RF_IPCA: _prod(
        ["Tesouro IPCA+", "CDB indexado ao IPCA com cupom semestral"],
        "Tesouro Nacional / " + _FGC,
        _IR_REGRESSIVO_RF,
        "Tesouro Direto ou corretora",
    ),
    RK.RF_SELIC_CDB: _prod(
        ["Tesouro Selic", "CDB 100%+ do CDI com liquidez diária"],
        "Tesouro Nacional / " + _FGC,
        _IR_REGRESSIVO_RF,
        "Tesouro Direto ou corretora",
    ),
    RK.RF_REAVALIE: _prod(
        ["Tesouro Selic (enquanto reavalia seu horizonte de investimento)"],
        "Garantia do Tesouro Nacional",
        _IR_REGRESSIVO_RF,
        "Tesouro Direto",
    ),
    RK.RF_EQUILIBRIO: _prod(
        ["Tesouro IPCA+ ou prefixado", "Fundos multimercado moderados"],
        "Tesouro Nacional / " + _FGC,
        _IR_REGRESSIVO_RF,
        "Tesouro Direto ou corretora",
    ),
    RK.FUNDOS_RF: _prod(
        ["Fundos de renda fixa (CDI/IPCA) de baixo custo"],
        "Sem FGC — garantia dos ativos do fundo (regulados pela CVM)",
        "Come-cotas semestral + IR regressivo no resgate",
        "Corretora ou banco que distribua fundos de terceiros",
    ),
    RK.FUNDOS_RF_LIQ: _prod(
        ["Fundos DI com liquidez diária"],
        "Sem FGC — regulados pela CVM",
        "Come-cotas semestral + IR regressivo no resgate",
        "Corretora ou banco",
    ),
    RK.FUNDOS: _prod(
        ["Fundos multimercado ou renda fixa diversificados"],
        "Sem FGC — regulados pela CVM",
        "Come-cotas semestral + IR regressivo no resgate",
        "Corretora ou banco que distribua fundos de terceiros",
    ),
    RK.FUNDOS_DIVERSIF: _prod(
        ["Fundos multimercado para diversificar a carteira atual"],
        "Sem FGC — regulados pela CVM",
        "Come-cotas semestral + IR regressivo no resgate",
        "Corretora ou banco",
    ),
    RK.FUNDOS_MULTI: _prod(
        ["Fundos multimercado com estratégias mistas (juros, moedas, bolsa)"],
        "Sem FGC — regulados pela CVM",
        "Come-cotas semestral + IR regressivo no resgate",
        "Corretora ou banco",
    ),
    RK.FUNDOS_ACOES: _prod(
        ["Fundos de ações ativos ou passivos"],
        "Sem FGC — regulados pela CVM",
        "15% sobre o ganho no resgate (sem come-cotas)",
        "Corretora ou banco",
    ),
    RK.FUNDOS_ACOES_ETF: _prod(
        ["ETFs de ações (ex.: BOVA11, IVVB11) via ranking dinâmico"],
        "Sem FGC — cotas negociadas em bolsa (B3), regulados pela CVM",
        _IR_ACOES_SWING + " (ETFs não têm a isenção de R$20 mil)",
        "Qualquer corretora habilitada na B3",
    ),
    RK.FUNDOS_ACOES_DCA: _prod(
        ["Fundos de ações com aportes mensais programados (DCA)"],
        "Sem FGC — regulados pela CVM",
        "15% sobre o ganho no resgate",
        "Corretora ou banco",
    ),
    RK.FUNDOS_CRIPTO: _prod(
        ["ETFs/fundos de criptomoedas listados na B3 (ex.: HASH11, BITH11)"],
        "Sem FGC — cotas negociadas em bolsa",
        _IR_ACOES_SWING,
        "Qualquer corretora habilitada na B3",
    ),
    RK.FIIS: _prod(
        ["FIIs de tijolo/papel/fundo de fundos, selecionados por dividend yield e liquidez"],
        "Sem FGC — cotas negociadas em bolsa (B3)",
        _IR_FII_TXT,
        "Qualquer corretora habilitada na B3",
    ),
    RK.FIIS_DEL: _prod(
        ["FIIs geridos por gestoras profissionais (fundos de fundos)"],
        "Sem FGC — cotas negociadas em bolsa",
        _IR_FII_TXT,
        "Corretora ou plataforma de gestão delegada",
    ),
    RK.RV: _prod(
        ["Ações individuais selecionadas por fundamentos (ranking dinâmico)"],
        "Sem FGC — ativos negociados em bolsa (B3)",
        _IR_ACOES_SWING,
        "Qualquer corretora habilitada na B3",
    ),
    RK.RV_DCA: _prod(
        ["Ações com aportes mensais programados (DCA)"],
        "Sem FGC — ativos negociados em bolsa",
        _IR_ACOES_SWING,
        "Qualquer corretora habilitada na B3",
    ),
    RK.RV_CRIPTO: _prod(
        ["Criptomoedas via corretora de cripto ou ETFs cripto na B3"],
        "Sem FGC — ativo de alta volatilidade, sem garantia",
        "15% sobre o ganho mensal acima de R$35 mil em vendas (pessoa física)",
        "Corretora de criptoativos (compra direta) ou corretora B3 (ETFs cripto)",
    ),
    RK.RV_COMPL: _prod(
        ["Ações ou ETFs como complemento de uma carteira moderada"],
        "Sem FGC — ativos negociados em bolsa",
        _IR_ACOES_SWING,
        "Qualquer corretora habilitada na B3",
    ),
    RK.PREV_PGBL: _prod(
        ["Previdência privada PGBL (dedutível até 12% da renda tributável no IR completo)"],
        "Sem FGC — patrimônio segregado da seguradora, fiscalizado pela SUSEP",
        "IR sobre o valor bruto total no resgate (regressivo ou progressivo, à escolha)",
        "Bancos e seguradoras (ex.: distribuído por corretoras de investimento)",
    ),
    RK.PREV_PGBL_RF: _prod(
        ["PGBL com fundo de renda fixa/conservador"],
        "Sem FGC — fiscalizado pela SUSEP",
        "IR sobre o valor bruto total no resgate",
        "Bancos e seguradoras",
    ),
    RK.PREV_VGBL: _prod(
        ["Previdência privada VGBL (sem dedução no IR — indicado para IR simplificado/isento)"],
        "Sem FGC — fiscalizado pela SUSEP",
        "IR apenas sobre o ganho no resgate (regressivo ou progressivo)",
        "Bancos e seguradoras",
    ),
    RK.PREV_VGBL_RF: _prod(
        ["VGBL com fundo de renda fixa/conservador"],
        "Sem FGC — fiscalizado pela SUSEP",
        "IR apenas sobre o ganho no resgate",
        "Bancos e seguradoras",
    ),
    RK.COE: _prod(
        ["Certificado de Operações Estruturadas (estratégia definida pelo banco emissor)"],
        "Sem FGC — risco de crédito do emissor",
        _IR_REGRESSIVO_RF,
        "Bancos e corretoras que emitem COE",
    ),
    RK.ESTRUTURADOS: _prod(
        ["CRA/CRI e Debêntures Incentivadas selecionadas via ranking (B3)"],
        "Sem FGC — risco de crédito do emissor/lastro; verifique rating",
        "Isento de IR para pessoa física (CRA/CRI/Debêntures incentivadas)",
        "Qualquer corretora habilitada na B3",
    ),
    RK.CAMBIO: _prod(
        ["ETFs cambiais (ex.: USDB11) ou fundos com exposição internacional"],
        "Sem FGC — exposição a variação cambial",
        _IR_ACOES_SWING,
        "Qualquer corretora habilitada na B3",
    ),
    RK.OFERTAS: _prod(
        ["IPOs, follow-ons e emissões de debêntures em oferta pública"],
        "Sem FGC — risco de mercado do ativo ofertado",
        _IR_ACOES_SWING + " (ou isenção, se debênture incentivada)",
        "Corretora habilitada a participar de ofertas públicas (B3)",
    ),
}

_DEFAULT_PROD = _prod(
    ["Categoria sem detalhamento específico no catálogo — consulte sua corretora."],
    "Verifique a garantia específica do produto antes de investir.",
    _IR_REGRESSIVO_RF,
    _CORRETORAS,
)


def _get_prod(rk: str) -> dict:
    """Informações práticas (o que comprar, garantia, imposto, onde abrir)
    para a categoria informada. Nunca lança erro — cai num registro
    genérico e sinaliza isso claramente, para nunca travar a exibição."""
    return _CATALOGO.get(rk, _DEFAULT_PROD)
