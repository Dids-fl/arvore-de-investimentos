"""Catálogo de produtos, nomes de exibição e enquadramento tributário."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from config import (
    IR_ACOES,
    IR_CRIPTO,
    IR_FII,
    IR_PGBL,
    IR_PREVIDENCIA_REGRESSIVO,
    IR_RF,
    IR_RF_REGRESSIVO,
    IR_VGBL,
)
from core.categorias import RK, _RK_DISPLAY
from tributacao import PrecisaoTributaria


TaxRule = Callable[[float], float]


class AliquotaIR(float):
    """
    Float compatível com o código legado, com regra opcional por prazo.

    calculos._vf_liquido detecta ``para_prazo`` e tributa cada aporte pelo
    próprio tempo de permanência.
    """

    def __new__(
        cls,
        valor_longo_prazo: float,
        regra: TaxRule | None = None,
    ) -> "AliquotaIR":
        objeto = super().__new__(cls, valor_longo_prazo)
        objeto._regra = regra
        return objeto

    def para_prazo(self, anos: float) -> float:
        regra = getattr(self, "_regra", None)
        return float(self) if regra is None else float(regra(anos))


def _aliquota_rf_por_prazo(anos: float) -> float:
    dias = max(0, int(round(float(anos) * 365.25)))
    for limite_dias, aliquota in IR_RF_REGRESSIVO:
        if limite_dias is None or dias <= limite_dias:
            return float(aliquota)
    return IR_RF


def _aliquota_previdencia_por_prazo(anos: float) -> float:
    prazo = max(0.0, float(anos))
    for limite_anos, aliquota in IR_PREVIDENCIA_REGRESSIVO:
        if limite_anos is None or prazo <= limite_anos:
            return float(aliquota)
    return IR_PGBL


IR_RF_DINAMICO = AliquotaIR(IR_RF, _aliquota_rf_por_prazo)
IR_PREV_PGBL_DINAMICO = AliquotaIR(
    IR_PGBL,
    _aliquota_previdencia_por_prazo,
)
IR_PREV_VGBL_DINAMICO = AliquotaIR(
    IR_VGBL,
    _aliquota_previdencia_por_prazo,
)


def _disp(rk: str) -> str:
    """Nome amigável; uma chave desconhecida continua visível."""
    return _RK_DISPLAY.get(rk, str(rk))


_RF_TRIBUTADA = {
    RK.RF,
    RK.RF_LIQUIDEZ,
    RK.RF_RESERVA,
    RK.RF_IPCA,
    RK.RF_SELIC_CDB,
    RK.RF_REAVALIE,
    RK.RF_EQUILIBRIO,
    RK.FUNDOS_RF,
    RK.FUNDOS_RF_LIQ,
    RK.FUNDOS,
    RK.FUNDOS_DIVERSIF,
    RK.FUNDOS_MULTI,
    RK.COE,
    # A classe mistura títulos isentos e tributados. A simulação usa o
    # tratamento conservador; o ranker deve informar o regime de cada ativo.
    RK.ESTRUTURADOS,
}

_ACOES_E_FUNDOS = {
    RK.FUNDOS_ACOES,
    RK.FUNDOS_ACOES_ETF,
    RK.FUNDOS_ACOES_DCA,
    RK.RV,
    RK.RV_DCA,
    RK.RV_COMPL,
    RK.CAMBIO,
    RK.OFERTAS,
}

_ALIQ_PRODUTO: dict[str, tuple[AliquotaIR, bool]] = {
    **{
        categoria: (IR_RF_DINAMICO, False)
        for categoria in _RF_TRIBUTADA
    },
    **{
        categoria: (AliquotaIR(IR_ACOES), False)
        for categoria in _ACOES_E_FUNDOS
    },
    RK.FUNDOS_CRIPTO: (AliquotaIR(IR_ACOES), False),
    RK.RV_CRIPTO: (AliquotaIR(IR_CRIPTO), False),
    RK.FIIS: (AliquotaIR(IR_FII), False),
    RK.FIIS_DEL: (AliquotaIR(IR_FII), False),
    RK.PREV_PGBL: (IR_PREV_PGBL_DINAMICO, True),
    RK.PREV_PGBL_RF: (IR_PREV_PGBL_DINAMICO, True),
    RK.PREV_VGBL: (IR_PREV_VGBL_DINAMICO, False),
    RK.PREV_VGBL_RF: (IR_PREV_VGBL_DINAMICO, False),
}


def _aliq(
    rk: str,
    anos: float | None = None,
) -> tuple[float, bool]:
    """
    Retorna ``(alíquota, tributa_saldo_total)``.

    Sem ``anos``, a alíquota preserva uma regra dinâmica consumida por
    calculos._vf_liquido. Com prazo explícito, retorna a alíquota pontual.
    """
    aliquota, pgbl = _ALIQ_PRODUTO.get(
        rk,
        (IR_RF_DINAMICO, False),
    )
    if anos is None:
        return aliquota, pgbl
    return aliquota.para_prazo(anos), pgbl


@dataclass(frozen=True)
class TratamentoTributarioCategoria:
    """
    Enquadramento que liga uma categoria ampla ao motor tributário.

    ``precisao_maxima`` limita a precisão declarada pelo cálculo. Por exemplo,
    uma regra de CDB pode ser exata para as premissas, mas uma categoria que
    mistura CDB, LCI e LCA só pode produzir uma estimativa enquanto o ativo
    concreto não for informado.
    """

    tipo_produto: str
    precisao_maxima: PrecisaoTributaria
    premissas: tuple[str, ...] = ()

    def como_dict(self) -> dict[str, Any]:
        return {
            "tipo_produto": self.tipo_produto,
            "precisao_maxima": self.precisao_maxima.value,
            "premissas": list(self.premissas),
        }


def _tratamento(
    tipo_produto: str,
    precisao: PrecisaoTributaria,
    *premissas: str,
) -> TratamentoTributarioCategoria:
    return TratamentoTributarioCategoria(
        tipo_produto=tipo_produto,
        precisao_maxima=precisao,
        premissas=tuple(premissas),
    )


_TRIBUTACAO_CATEGORIA: dict[str, TratamentoTributarioCategoria] = {
    RK.RF: _tratamento(
        "cdb",
        PrecisaoTributaria.ESTIMADA,
        (
            "Categoria ampla de renda fixa tratada como CDB tributável; "
            "LCI/LCA e outros títulos isentos precisam ser identificados "
            "individualmente."
        ),
    ),
    RK.RF_LIQUIDEZ: _tratamento(
        "cdb",
        PrecisaoTributaria.EXATA_PARA_PREMISSAS,
        "Tesouro Selic e CDB foram enquadrados na tabela regressiva de renda fixa.",
    ),
    RK.RF_RESERVA: _tratamento(
        "cdb",
        PrecisaoTributaria.EXATA_PARA_PREMISSAS,
        "Reserva tratada como Tesouro Selic/CDB tributável.",
    ),
    RK.RF_IPCA: _tratamento(
        "tesouro",
        PrecisaoTributaria.EXATA_PARA_PREMISSAS,
        "Classe tratada como Tesouro IPCA+/CDB tributável.",
    ),
    RK.RF_SELIC_CDB: _tratamento(
        "cdb",
        PrecisaoTributaria.EXATA_PARA_PREMISSAS,
        "Classe tratada como Tesouro Selic/CDB tributável.",
    ),
    RK.RF_REAVALIE: _tratamento(
        "tesouro",
        PrecisaoTributaria.EXATA_PARA_PREMISSAS,
        "Alocação temporária tratada como Tesouro Selic.",
    ),
    RK.RF_EQUILIBRIO: _tratamento(
        "cdb",
        PrecisaoTributaria.ESTIMADA,
        "Classe mista tratada conservadoramente como renda fixa tributável.",
    ),
    RK.FUNDOS_RF: _tratamento(
        "fundo_longo_prazo",
        PrecisaoTributaria.ESTIMADA,
        "Fundo de renda fixa tratado como fundo de longo prazo.",
    ),
    RK.FUNDOS_RF_LIQ: _tratamento(
        "fundo_longo_prazo",
        PrecisaoTributaria.ESTIMADA,
        "Fundo DI/renda fixa tratado como fundo de longo prazo.",
    ),
    RK.FUNDOS: _tratamento(
        "fundo_longo_prazo",
        PrecisaoTributaria.ESTIMADA,
        "Fundo sem subtipo tratado como fundo de longo prazo.",
    ),
    RK.FUNDOS_DIVERSIF: _tratamento(
        "fundo_longo_prazo",
        PrecisaoTributaria.ESTIMADA,
        "Fundo diversificado tratado como fundo de longo prazo.",
    ),
    RK.FUNDOS_MULTI: _tratamento(
        "fundo_longo_prazo",
        PrecisaoTributaria.ESTIMADA,
        "Multimercado tratado como fundo de longo prazo.",
    ),
    RK.FUNDOS_ACOES: _tratamento(
        "fundo_acoes",
        PrecisaoTributaria.ESTIMADA,
        "Veículo tratado como fundo de ações.",
    ),
    RK.FUNDOS_ACOES_ETF: _tratamento(
        "fundo_etf_acoes",
        PrecisaoTributaria.ESTIMADA,
        "Classe tratada como fundo/ETF de ações sem isenção mensal.",
    ),
    RK.FUNDOS_ACOES_DCA: _tratamento(
        "fundo_acoes",
        PrecisaoTributaria.ESTIMADA,
        "Aportes periódicos tratados como cotas de fundo de ações.",
    ),
    RK.FUNDOS_CRIPTO: _tratamento(
        "fundo_etf_acoes",
        PrecisaoTributaria.ESTIMADA,
        (
            "Exposição a cripto tratada como fundo/ETF regulado; compra "
            "direta de cripto exige outro enquadramento."
        ),
    ),
    RK.FIIS: _tratamento(
        "fii",
        PrecisaoTributaria.ESTIMADA,
        "Projeção considera ganho na alienação das cotas.",
    ),
    RK.FIIS_DEL: _tratamento(
        "fii",
        PrecisaoTributaria.ESTIMADA,
        "Projeção considera ganho na alienação das cotas.",
    ),
    RK.RV: _tratamento(
        "acao",
        PrecisaoTributaria.ESTIMADA,
        "Renda variável ampla tratada como operação comum com ações.",
    ),
    RK.RV_DCA: _tratamento(
        "acao",
        PrecisaoTributaria.ESTIMADA,
        "Aportes em renda variável tratados como operações comuns com ações.",
    ),
    RK.RV_CRIPTO: _tratamento(
        "cripto",
        PrecisaoTributaria.ESTIMADA,
        "Classe tratada como compra direta de criptoativos.",
    ),
    RK.RV_COMPL: _tratamento(
        "acao",
        PrecisaoTributaria.ESTIMADA,
        "Complemento de renda variável tratado como ações.",
    ),
    RK.PREV_PGBL: _tratamento(
        "pgbl",
        PrecisaoTributaria.ESTIMADA,
        "O regime regressivo ou progressivo deve ser informado.",
    ),
    RK.PREV_PGBL_RF: _tratamento(
        "pgbl",
        PrecisaoTributaria.ESTIMADA,
        "A classe combinada foi tratada integralmente como PGBL.",
    ),
    RK.PREV_VGBL: _tratamento(
        "vgbl",
        PrecisaoTributaria.ESTIMADA,
        "O regime regressivo ou progressivo deve ser informado.",
    ),
    RK.PREV_VGBL_RF: _tratamento(
        "vgbl",
        PrecisaoTributaria.ESTIMADA,
        "A classe combinada foi tratada integralmente como VGBL.",
    ),
    RK.COE: _tratamento(
        "coe",
        PrecisaoTributaria.EXATA_PARA_PREMISSAS,
        "COE enquadrado na tabela regressiva de renda fixa.",
    ),
    RK.ESTRUTURADOS: _tratamento(
        "estruturado",
        PrecisaoTributaria.INDETERMINADA,
        "Informe COE, CRI, CRA ou o tipo de debênture para calcular.",
    ),
    RK.CAMBIO: _tratamento(
        "etf",
        PrecisaoTributaria.ESTIMADA,
        "Exposição cambial tratada como ETF sem isenção mensal.",
    ),
    RK.OFERTAS: _tratamento(
        "oferta_publica",
        PrecisaoTributaria.INDETERMINADA,
        "A tributação depende do ativo distribuído na oferta.",
    ),
}

_TRIBUTACAO_DESCONHECIDA = _tratamento(
    "produto_nao_mapeado",
    PrecisaoTributaria.INDETERMINADA,
    "Categoria sem enquadramento tributário explícito.",
)


def _tipo_tributario(rk: str) -> TratamentoTributarioCategoria:
    """Retorna o enquadramento explícito, sem alíquota genérica de fallback."""
    return _TRIBUTACAO_CATEGORIA.get(rk, _TRIBUTACAO_DESCONHECIDA)


def _prod(
    o_que_comprar: list[str],
    garantia: str,
    imposto: str,
    onde: str,
) -> dict[str, Any]:
    return {
        "o_que_comprar": tuple(o_que_comprar),
        "garantia": garantia,
        "imposto": imposto,
        "onde": onde,
    }


_FGC = (
    "FGC dentro dos limites vigentes por CPF/CNPJ e instituição; "
    "confirme a cobertura do título"
)
_IR_REGRESSIVO_RF = (
    "IR regressivo sobre os rendimentos: 22,5% até 180 dias, "
    "20% até 360, 17,5% até 720 e 15% acima de 720 dias"
)
_IR_ACOES_SWING = (
    "15% sobre ganho líquido em operações comuns; day trade possui regra "
    "própria. A isenção mensal de vendas aplica-se a ações, não a ETFs"
)
_IR_FII_TXT = (
    "Ganho líquido na venda/resgate: 20%. Rendimentos distribuídos podem "
    "ser isentos para pessoa física somente quando os requisitos legais "
    "forem atendidos"
)
_CORRETORAS = "Corretora ou instituição habilitada para distribuir o produto"


_CATALOGO: dict[str, dict[str, Any]] = {
    RK.RF: _prod(
        ["Tesouro Selic", "CDB", "LCI/LCA", "fundo de renda fixa"],
        "Tesouro Nacional no Tesouro Direto; CDB/LCI/LCA podem ter FGC",
        _IR_REGRESSIVO_RF + "; LCI/LCA possuem regra de isenção para PF",
        "Tesouro Direto, banco ou corretora",
    ),
    RK.RF_LIQUIDEZ: _prod(
        ["Tesouro Selic", "CDB com liquidez diária"],
        "Tesouro Nacional ou " + _FGC,
        _IR_REGRESSIVO_RF,
        "Tesouro Direto, banco ou corretora",
    ),
    RK.RF_RESERVA: _prod(
        ["Tesouro Selic", "CDB com liquidez diária e cobertura do FGC"],
        "Tesouro Nacional ou " + _FGC,
        _IR_REGRESSIVO_RF,
        "Tesouro Direto, banco ou corretora",
    ),
    RK.RF_IPCA: _prod(
        ["Tesouro IPCA+ compatível com o prazo", "CDB indexado ao IPCA"],
        "Tesouro Nacional ou " + _FGC,
        _IR_REGRESSIVO_RF,
        "Tesouro Direto, banco ou corretora",
    ),
    RK.RF_SELIC_CDB: _prod(
        ["Tesouro Selic", "CDB de liquidez diária próximo ou acima do CDI"],
        "Tesouro Nacional ou " + _FGC,
        _IR_REGRESSIVO_RF,
        "Tesouro Direto, banco ou corretora",
    ),
    RK.RF_REAVALIE: _prod(
        ["Tesouro Selic enquanto o horizonte é redefinido"],
        "Tesouro Nacional",
        _IR_REGRESSIVO_RF,
        "Tesouro Direto",
    ),
    RK.RF_EQUILIBRIO: _prod(
        ["Tesouro IPCA+", "renda fixa de boa qualidade de crédito"],
        "Depende do emissor; verifique Tesouro ou FGC",
        _IR_REGRESSIVO_RF,
        "Tesouro Direto, banco ou corretora",
    ),
    RK.FUNDOS_RF: _prod(
        ["Fundos de renda fixa de baixo custo e prazo compatível"],
        "Sem FGC; patrimônio do fundo é regulado e segregado",
        "Regra de fundos, normalmente com come-cotas e ajuste no resgate",
        "Banco, seguradora ou corretora",
    ),
    RK.FUNDOS_RF_LIQ: _prod(
        ["Fundos DI/renda fixa com liquidez diária e taxa baixa"],
        "Sem FGC; patrimônio do fundo é regulado e segregado",
        "Regra de fundos, normalmente com come-cotas",
        "Banco ou corretora",
    ),
    RK.FUNDOS: _prod(
        ["Fundos multimercado ou de renda fixa diversificados"],
        "Sem FGC; patrimônio do fundo é regulado e segregado",
        "Depende da classe; fundos de longo prazo podem ter come-cotas",
        "Banco ou corretora",
    ),
    RK.FUNDOS_DIVERSIF: _prod(
        ["Fundos com estratégia diferente da carteira já existente"],
        "Sem FGC; patrimônio do fundo é regulado e segregado",
        "Depende da classe do fundo",
        "Banco ou corretora",
    ),
    RK.FUNDOS_MULTI: _prod(
        ["Fundos multimercado com risco, liquidez e taxa conhecidos"],
        "Sem FGC; patrimônio do fundo é regulado e segregado",
        "Regra de fundos multimercado, normalmente com come-cotas",
        "Banco ou corretora",
    ),
    RK.FUNDOS_ACOES: _prod(
        ["Fundos de ações com histórico e taxa compatíveis"],
        "Sem FGC; patrimônio do fundo é regulado e segregado",
        "15% sobre o ganho no resgate, sem come-cotas",
        "Banco ou corretora",
    ),
    RK.FUNDOS_ACOES_ETF: _prod(
        ["ETFs diversificados de ações adequados ao objetivo"],
        "Sem FGC; cotas negociadas em bolsa",
        "15% sobre ganho; ETFs não usam a isenção mensal de ações",
        _CORRETORAS,
    ),
    RK.FUNDOS_ACOES_DCA: _prod(
        ["Fundo de ações ou ETF para aportes periódicos"],
        "Sem FGC; sujeito a risco de mercado",
        "15% sobre ganho; detalhes dependem do veículo",
        "Banco ou corretora",
    ),
    RK.FUNDOS_CRIPTO: _prod(
        ["ETF ou fundo regulado com exposição limitada a criptoativos"],
        "Sem FGC; alta volatilidade e risco de mercado",
        "Depende do veículo; ETF e fundo não seguem a compra direta",
        "Corretora habilitada",
    ),
    RK.FIIS: _prod(
        ["FIIs líquidos e diversificados após análise de risco e preço"],
        "Sem FGC; cotas negociadas em bolsa",
        _IR_FII_TXT,
        _CORRETORAS,
    ),
    RK.FIIS_DEL: _prod(
        ["FIIs ou fundo de fundos com gestão e custos avaliados"],
        "Sem FGC; cotas negociadas em bolsa",
        _IR_FII_TXT,
        "Corretora ou serviço de gestão autorizado",
    ),
    RK.RV: _prod(
        ["Ações selecionadas por fundamentos e diversificação"],
        "Sem FGC; risco de perda de capital",
        _IR_ACOES_SWING,
        _CORRETORAS,
    ),
    RK.RV_DCA: _prod(
        ["Ações ou ETFs diversificados com aportes programados"],
        "Sem FGC; risco de mercado",
        _IR_ACOES_SWING,
        _CORRETORAS,
    ),
    RK.RV_CRIPTO: _prod(
        ["Criptoativos com posição limitada ou ETF regulado"],
        "Sem FGC; alta volatilidade, custódia e regulação específicas",
        "A tributação depende do veículo, localização e volume das operações",
        "Corretora de criptoativos ou corretora B3 para ETFs",
    ),
    RK.RV_COMPL: _prod(
        ["Ações ou ETFs que reduzam a concentração da carteira atual"],
        "Sem FGC; risco de mercado",
        _IR_ACOES_SWING,
        _CORRETORAS,
    ),
    RK.PREV_PGBL: _prod(
        ["PGBL de taxa baixa e fundo compatível com o perfil"],
        "Sem FGC; fiscalizado pela SUSEP, com patrimônio do fundo segregado",
        "IR sobre o saldo resgatado; regime depende da opção tributária",
        "Seguradora, banco ou plataforma que distribua previdência",
    ),
    RK.PREV_PGBL_RF: _prod(
        ["PGBL conservador ou de renda fixa e taxa baixa"],
        "Sem FGC; fiscalizado pela SUSEP",
        "IR sobre o saldo resgatado; regime depende da opção tributária",
        "Seguradora, banco ou plataforma de previdência",
    ),
    RK.PREV_VGBL: _prod(
        ["VGBL de taxa baixa e fundo compatível com o perfil"],
        "Sem FGC; fiscalizado pela SUSEP",
        "IR normalmente sobre os rendimentos; confirme o regime escolhido",
        "Seguradora, banco ou plataforma que distribua previdência",
    ),
    RK.PREV_VGBL_RF: _prod(
        ["VGBL conservador ou de renda fixa e taxa baixa"],
        "Sem FGC; fiscalizado pela SUSEP",
        "IR normalmente sobre os rendimentos; confirme o regime escolhido",
        "Seguradora, banco ou plataforma de previdência",
    ),
    RK.COE: _prod(
        ["COE apenas após ler cenário, barreiras, custos e risco do emissor"],
        "Sem FGC; risco de crédito do emissor",
        _IR_REGRESSIVO_RF,
        "Banco ou corretora distribuidora",
    ),
    RK.ESTRUTURADOS: _prod(
        ["CRA/CRI ou debênture após análise de emissor, lastro e liquidez"],
        "Sem FGC; risco de crédito e baixa liquidez",
        (
            "CRA/CRI e debêntures incentivadas podem ser isentos para PF; "
            "debêntures comuns e outros títulos podem ser tributados"
        ),
        _CORRETORAS,
    ),
    RK.CAMBIO: _prod(
        ["ETF ou fundo com exposição internacional/cambial transparente"],
        "Sem FGC; risco cambial e de mercado",
        "Depende do veículo; ETFs não usam a isenção mensal de ações",
        _CORRETORAS,
    ),
    RK.OFERTAS: _prod(
        ["Oferta pública somente após prospecto e análise de preço/risco"],
        "Sem FGC; depende do ativo e do emissor",
        "Depende do ativo ofertado",
        "Corretora participante da oferta",
    ),
}

_DEFAULT_PROD = _prod(
    ["Categoria sem detalhamento; consulte documentação e instituição."],
    "Verifique a garantia e o risco de crédito antes de investir.",
    "Verifique o regime tributário do produto específico.",
    _CORRETORAS,
)


def _get_prod(rk: str) -> dict[str, Any]:
    """Devolve uma cópia para impedir mutação acidental do catálogo global."""
    produto = _CATALOGO.get(rk, _DEFAULT_PROD)
    tributacao = _tipo_tributario(rk)
    return {
        "o_que_comprar": list(produto["o_que_comprar"]),
        "garantia": produto["garantia"],
        "imposto": produto["imposto"],
        "onde": produto["onde"],
        "tributacao": tributacao.como_dict(),
    }
