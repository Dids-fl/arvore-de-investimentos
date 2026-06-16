from typing import Dict


class RK:
    RF              = "rf"
    RF_LIQUIDEZ     = "rf_liq"
    RF_RESERVA      = "rf_reserva"
    RF_IPCA         = "rf_ipca"
    RF_SELIC_CDB    = "rf_selic_cdb"
    RF_REAVALIE     = "rf_reavalie"
    RF_EQUILIBRIO   = "rf_equilibrio"
    FUNDOS          = "fundos"
    FUNDOS_DIVERSIF = "fundos_div"
    FUNDOS_MULTI    = "fundos_multi"
    FUNDOS_RF       = "fundos_rf"
    FUNDOS_RF_LIQ   = "fundos_rf_liq"
    FUNDOS_ACOES    = "fundos_acoes"
    FUNDOS_ACOES_ETF= "fundos_etf"
    FUNDOS_ACOES_DCA= "fundos_dca"
    FUNDOS_CRIPTO   = "fundos_cripto"
    FIIS            = "fiis"
    FIIS_DEL        = "fiis_del"
    RV              = "rv"
    RV_DCA          = "rv_dca"
    RV_CRIPTO       = "rv_cripto"
    RV_COMPL        = "rv_compl"
    PREV_PGBL       = "prev_pgbl"
    PREV_VGBL       = "prev_vgbl"
    PREV_PGBL_RF    = "prev_pgbl_rf"
    PREV_VGBL_RF    = "prev_vgbl_rf"
    COE             = "coe"
    ESTRUTURADOS    = "estruturados"
    CAMBIO          = "cambio"
    OFERTAS         = "ofertas"


RISK_LEVEL: Dict[str, int] = {
    RK.RF:              1,
    RK.RF_LIQUIDEZ:     1,
    RK.RF_RESERVA:      1,
    RK.RF_IPCA:         1,
    RK.RF_SELIC_CDB:    1,
    RK.RF_REAVALIE:     1,
    RK.RF_EQUILIBRIO:   2,
    RK.FUNDOS_RF:       1,
    RK.FUNDOS_RF_LIQ:   1,
    RK.FUNDOS:          2,
    RK.FUNDOS_DIVERSIF: 2,
    RK.FUNDOS_MULTI:    2,
    RK.FUNDOS_ACOES:    3,
    RK.FUNDOS_ACOES_ETF:3,
    RK.FUNDOS_ACOES_DCA:3,
    RK.FUNDOS_CRIPTO:   3,
    RK.FIIS:            2,
    RK.FIIS_DEL:        2,
    RK.RV:              3,
    RK.RV_DCA:          3,
    RK.RV_CRIPTO:       3,
    RK.RV_COMPL:        3,
    RK.PREV_PGBL:       2,
    RK.PREV_VGBL:       2,
    RK.PREV_PGBL_RF:    1,
    RK.PREV_VGBL_RF:    1,
    RK.COE:             2,
    RK.ESTRUTURADOS:    2,
    RK.CAMBIO:          2,
    RK.OFERTAS:         3,
}


def _risco(rk: str) -> int:
    """Nível de risco canônico de um produto. Fallback conservador (1) para chaves desconhecidas."""
    return RISK_LEVEL.get(rk, 1)


_ARRISCADAS: set = {rk for rk, nivel in RISK_LEVEL.items() if nivel >= 3}

_RK_DISPLAY: Dict[str, str] = {
    RK.RF:              "Renda Fixa",
    RK.RF_LIQUIDEZ:     "Renda Fixa (com liquidez)",
    RK.RF_RESERVA:      "Renda Fixa (Tesouro Selic) — construa sua reserva primeiro",
    RK.RF_IPCA:         "Renda Fixa (Tesouro IPCA+ / CDB com cupom semestral)",
    RK.RF_SELIC_CDB:    "Tesouro Selic / CDB com liquidez diária",
    RK.RF_REAVALIE:     "Renda Fixa (reavalie seu prazo)",
    RK.RF_EQUILIBRIO:   "Renda Fixa / Fundos Moderados (para equilibrar carteira arrojada)",
    RK.FUNDOS:          "Fundos de Investimento",
    RK.FUNDOS_DIVERSIF: "Fundos de Investimento (para diversificar sua carteira atual)",
    RK.FUNDOS_MULTI:    "Fundos Multimercado",
    RK.FUNDOS_RF:       "Fundos de Renda Fixa / Previdência",
    RK.FUNDOS_RF_LIQ:   "Fundos de Renda Fixa (liquidez diária)",
    RK.FUNDOS_ACOES:    "Fundos de Ações",
    RK.FUNDOS_ACOES_ETF:"Fundos de Ações / ETFs",
    RK.FUNDOS_ACOES_DCA:"Fundos de Ações (aportes mensais — DCA)",
    RK.FUNDOS_CRIPTO:   "Fundos/ETFs de Cripto",
    RK.FIIS:            "FIIs / Fundos de Renda Passiva",
    RK.FIIS_DEL:        "FIIs / Fundos de Renda Passiva (gestão delegada)",
    RK.RV:              "Renda Variável",
    RK.RV_DCA:          "Renda Variável (com aportes mensais — DCA)",
    RK.RV_CRIPTO:       "Renda Variável / Cripto",
    RK.RV_COMPL:        "Renda Variável (complemento à sua carteira moderada)",
    RK.PREV_PGBL:       "Previdência Privada — PGBL",
    RK.PREV_VGBL:       "Previdência Privada — VGBL",
    RK.PREV_PGBL_RF:    "Previdência Privada (PGBL) + Renda Fixa",
    RK.PREV_VGBL_RF:    "Previdência Privada (VGBL) + Renda Fixa",
    RK.COE:             "COE (Certificado de Operações Estruturadas)",
    RK.ESTRUTURADOS:    "Produtos Estruturados (CRA / CRI / Debêntures Incentivadas)",
    RK.CAMBIO:          "Câmbio / Diversificação Internacional",
    RK.OFERTAS:         "Ofertas Públicas (IPO / Follow-on / Debêntures em emissão)",
}