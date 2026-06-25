"""
Traduz o portfólio em sugestões de ativos específicos por classe.

Classes suportadas e fonte dos dados
─────────────────────────────────────
  acoes  → acoes_fiis.screener.top_acoes() (Fundamentus + BRAPI)
  etf    → etfs.screener_etf.top_etfs()   (BRAPI /api/v2/tickers + yfinance)
  fiis   → acoes_fiis.screener.top_fiis() (Fundamentus + fallback Status Invest)
  cripto → cripto.screener_cripto.top_cripto() (CoinGecko)
  rf     → rf_fundos.rf_mercado.calcular_rf() (SELIC/IPCA/CDI)
  fundos → rf_fundos.rf_mercado.calcular_fundos() (taxas e spreads)
"""

from core.categorias import RK
from acoes_fiis.screener import top_acoes, top_fiis, _score_acao
from cripto.screener_cripto import top_cripto
from rf_fundos.rf_mercado import calcular_rf, calcular_fundos
from etfs.screener_etf import top_etfs
from utils.logging_config import get_logger

logger = get_logger(__name__)

# ── Mapeamento rk → classe ────────────────────────────────────────────────────

_CLASSE: dict[str, str] = {
    # Ações / ETFs
    RK.RV:               "acoes",
    RK.RV_DCA:           "acoes",
    RK.RV_COMPL:         "acoes",
    RK.FUNDOS_ACOES:     "acoes",
    RK.FUNDOS_ACOES_ETF: "etf",
    RK.FUNDOS_ACOES_DCA: "acoes",
    # FIIs
    RK.FIIS:             "fiis",
    RK.FIIS_DEL:         "fiis",
    # Cripto
    RK.RV_CRIPTO:        "cripto",
    RK.FUNDOS_CRIPTO:    "cripto",
    # Renda Fixa
    RK.RF:               "rf",
    RK.RF_LIQUIDEZ:      "rf",
    RK.RF_SELIC_CDB:     "rf",
    RK.RF_IPCA:          "rf",
    RK.RF_RESERVA:       "rf",
    RK.FUNDOS_RF:        "rf",
    RK.FUNDOS_RF_LIQ:    "rf",
    # Fundos
    RK.FUNDOS:           "fundos",
    RK.FUNDOS_DIVERSIF:  "fundos",
    RK.FUNDOS_MULTI:     "fundos",
}

_LABEL: dict[str, str] = {
    "acoes":  "AÇÕES",
    "etf":    "ETFs (Ranking Dinâmico)",
    "fiis":   "FIIs",
    "cripto": "CRIPTO",
    "rf":     "RENDA FIXA",
    "fundos": "FUNDOS",
}

MIN_PCT = 5   # alocação mínima no portfólio para gerar sugestão da classe


# ── Filtros de RF por perfil ──────────────────────────────────────────────────

_RF_PERFIL: dict[int, list[str]] = {
    1: ["SELIC", "CDB-DI", "LCI/LCA"],
    2: ["SELIC", "CDB-DI", "LCI/LCA", "IPCA+", "DEBN"],
    3: ["IPCA+", "DEBN", "CRI/CRA", "CDB-DI"],
}

_FUNDOS_PERFIL: dict[int, list[str]] = {
    1: ["FDO-RF", "FDO-PREV"],
    2: ["FDO-MULTI", "FDO-DEBN", "FDO-RF", "FDO-PREV"],
    3: ["FDO-LONG", "IVVB11", "FDO-MULTI", "FDO-DEBN"],
}


def _filtrar_rf_por_perfil(todos: list[dict], perfil: int, n: int) -> list[dict]:
    permitidos = set(_RF_PERFIL.get(perfil, _RF_PERFIL[2]))
    filtrados = [p for p in todos if p.get("ticker") in permitidos]
    return filtrados[:n]


def _filtrar_fundos_por_perfil(todos: list[dict], perfil: int, n: int) -> list[dict]:
    permitidos = set(_FUNDOS_PERFIL.get(perfil, _FUNDOS_PERFIL[2]))
    filtrados = [f for f in todos if f.get("ticker") in permitidos]
    return filtrados[:n]


# ── Função principal ──────────────────────────────────────────────────────────

def recomendar_por_portfolio(
    portfolio: dict,
    perfil_risco: int,
    n: int = 5,
    selic: float = 0.1425,
    ipca: float = 0.044,
    ibov_cagr: float | None = None,
) -> dict[str, list]:
    """
    Recebe o portfólio completo e retorna os top N ativos de cada classe
    que tiver alocação >= MIN_PCT no portfólio.

    RF e Fundos usam as taxas reais passadas (selic, ipca, ibov_cagr)
    para calcular retorno líquido real e rankear dinamicamente.

    ETFs são rankeados com base em performance histórica (yfinance) e
    pré-seleção via BRAPI (liquidez e retorno 12m).

    Retorna dict com chaves: "rf", "fundos", "fiis", "acoes", "etf", "cripto"
    (apenas as classes presentes no portfólio).
    """
    classes: set[str] = {
        _CLASSE[rk]
        for rk, pct in portfolio.items()
        if pct >= MIN_PCT and rk in _CLASSE
    }

    if not classes:
        return {}

    ordem = ["rf", "fundos", "fiis", "acoes", "etf", "cripto"]
    resultado: dict[str, list] = {}

    for classe in ordem:
        if classe not in classes:
            continue
        try:
            if classe == "acoes":
                resultado["acoes"] = top_acoes(perfil_risco, n=n)

            elif classe == "etf":
                resultado["etf"] = top_etfs(perfil_risco, n=min(n, 5))

            elif classe == "fiis":
                resultado["fiis"] = top_fiis(perfil_risco, n=n)

            elif classe == "cripto":
                resultado["cripto"] = top_cripto(perfil_risco, n=min(n, 4))

            elif classe == "rf":
                todos_rf = calcular_rf(selic, ipca, ibov_cagr)
                resultado["rf"] = _filtrar_rf_por_perfil(todos_rf, perfil_risco, n)

            elif classe == "fundos":
                todos_fundos = calcular_fundos(selic, ipca, ibov_cagr)
                resultado["fundos"] = _filtrar_fundos_por_perfil(todos_fundos, perfil_risco, n)

        except Exception as e:
            logger.error(f"Erro ao buscar classe {classe}: {e}")
            resultado[classe] = [{
                "ticker": "ERRO",
                "score": 0,
                "preco": 0,
                "nome": "",
                "motivos": [f"Falha ao buscar dados: {e}"],
            }]

    return resultado


# ── Versão legada (compatibilidade) ──────────────────────────────────────────

def recomendar_ativos(
    rec_key: str,
    perfil_risco: int,
    n: int = 5,
    selic: float = 0.1425,
    ipca: float = 0.044,
    ibov_cagr: float | None = None,
) -> list[dict] | None:
    """
    Versão legada — prefira recomendar_por_portfolio().
    """
    classe = _CLASSE.get(rec_key)
    if classe is None:
        return None
    try:
        if classe == "acoes":
            return top_acoes(perfil_risco, n=n)
        if classe == "etf":
            return top_etfs(perfil_risco, n=min(n, 5))
        if classe == "fiis":
            return top_fiis(perfil_risco, n=n)
        if classe == "cripto":
            return top_cripto(perfil_risco, n=min(n, 4))
        if classe == "rf":
            return _filtrar_rf_por_perfil(calcular_rf(selic, ipca), perfil_risco, n)
        if classe == "fundos":
            return _filtrar_fundos_por_perfil(calcular_fundos(selic, ipca, ibov_cagr), perfil_risco, n)
    except Exception as e:
        return [{"ticker": "ERRO", "score": 0, "preco": 0,
                 "nome": "", "motivos": [f"Falha: {e}"]}]
    return None