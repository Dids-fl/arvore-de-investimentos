"""
Traduz o portfólio em sugestões de ativos específicos por classe.

Classes suportadas e fonte dos dados
─────────────────────────────────────
  acoes          → acoes_fiis.screener.top_acoes()        (Fundamentus + BRAPI)
  etf            → etfs.screener_etf.top_etfs()            (BRAPI /api/v2/tickers + yfinance)
  fiis           → acoes_fiis.screener.top_fiis()           (Fundamentus + fallback Status Invest)
  cripto         → cripto.screener_cripto.top_cripto()      (CoinGecko)
  rf             → renda_fixa.ranker.rankear_rf()            (Tesouro Direto + Selic/CDI via BCB SGS)
  fundos         → fundos.ranker_fundos.rankear_fundos()     (CVM: cadastro + informe diário, com Sharpe/Sortino)
  estruturados   → produtos_estruturados.ranker.rankear_estruturados()
                   (CRA/CRI/Debêntures via B3, biblioteca `mercados`)

NOTA DE MANUTENÇÃO (2026):
Este arquivo importava anteriormente de `rf_fundos.rf_mercado` e
`rf_fundos.rf_dynamic` — módulos que não existem mais no repositório
(sobra de uma refatoração anterior). As classes "rf" e "fundos" foram
corrigidas para usar os módulos reais e atuais: `renda_fixa.ranker` e
`fundos.ranker_fundos`. Esses módulos já fazem sua própria busca de
Selic/CDI/indicadores internamente, então os parâmetros `selic`, `ipca`
e `ibov_cagr` de `recomendar_por_portfolio()` são mantidos apenas por
compatibilidade com as chamadas existentes em `main.py`/`app.py` — hoje
eles não são mais repassados a "rf"/"fundos"/"estruturados".
"""

from core.categorias import RK
from acoes_fiis.screener import top_acoes, top_fiis, _score_acao
from cripto.screener_cripto import top_cripto
from etfs.screener_etf import top_etfs
from renda_fixa.ranker import rankear_rf
from fundos.ranker_fundos import rankear_fundos
from produtos_estruturados.ranker import rankear_estruturados
from utils.logging_config import get_logger
from utils.exceptions import DadosIndisponiveisError

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
    RK.RF_REAVALIE:      "rf",
    RK.RF_EQUILIBRIO:    "rf",
    RK.FUNDOS_RF:        "rf",
    RK.FUNDOS_RF_LIQ:    "rf",
    # Fundos
    RK.FUNDOS:           "fundos",
    RK.FUNDOS_DIVERSIF:  "fundos",
    RK.FUNDOS_MULTI:     "fundos",
    # Produtos Estruturados (CRA / CRI / Debêntures)
    RK.ESTRUTURADOS:     "estruturados",
}

_LABEL: dict[str, str] = {
    "acoes":        "AÇÕES",
    "etf":          "ETFs (Ranking Dinâmico)",
    "fiis":         "FIIs",
    "cripto":       "CRIPTO",
    "rf":           "RENDA FIXA",
    "fundos":       "FUNDOS",
    "estruturados": "PRODUTOS ESTRUTURADOS (CRA/CRI/Debêntures)",
}

MIN_PCT = 5   # alocação mínima no portfólio para gerar sugestão da classe

# Ordem de exibição/busca. "estruturados" fica perto de "fundos" por ter
# risco/complexidade parecida (RK.ESTRUTURADOS tem nível de risco 2, mas
# normalmente só aparece para perfil com conhecimento avançado — ver
# recomendador.py).
_ORDEM: list[str] = ["rf", "fundos", "estruturados", "fiis", "acoes", "etf", "cripto"]


# ── Função principal ──────────────────────────────────────────────────────────

def recomendar_por_portfolio(
    portfolio: dict,
    perfil_risco: int,
    n: int = 5,
    selic: float | None = None,
    ipca: float | None = None,
    ibov_cagr: float | None = None,
) -> dict[str, list]:
    """
    Recebe o portfólio completo e retorna os top N ativos de cada classe
    que tiver alocação >= MIN_PCT no portfólio.

      rf           → renda_fixa.ranker.rankear_rf() — Tesouro Direto, com
                      Selic/CDI buscados dinamicamente via BCB SGS.
      fundos       → fundos.ranker_fundos.rankear_fundos() — pipeline
                      interseção → pré-filtro → Sharpe/Sortino sobre dados
                      reais da CVM.
      estruturados → produtos_estruturados.ranker.rankear_estruturados() —
                      CRA/CRI/Debêntures via B3 (biblioteca `mercados`).

    `selic`, `ipca` e `ibov_cagr` são aceitos apenas por compatibilidade
    com chamadas existentes (main.py/app.py); os rankers atuais buscam
    seus próprios indicadores internamente e não usam esses argumentos.
    """
    classes: set[str] = {
        _CLASSE[rk]
        for rk, pct in portfolio.items()
        if pct >= MIN_PCT and rk in _CLASSE
    }

    if not classes:
        return {}

    resultado, indisponiveis = _buscar_classes(classes, perfil_risco, n)
    resultado["_indisponiveis"] = indisponiveis
    return resultado


def _buscar_classes(
    classes: set[str], perfil_risco: int, n: int
) -> tuple[dict[str, list], dict[str, str]]:
    """
    Busca cada classe solicitada em sua fonte online real.

    Não há mock nem fallback: se uma fonte falhar (`DadosIndisponiveisError`
    ou qualquer exceção), a classe correspondente NÃO aparece na lista de
    ativos (nunca é preenchida com um item fake tipo "ERRO"). Em vez disso,
    é registrada em `indisponiveis` com o motivo, para que a camada de
    apresentação (CLI/webapp) mostre um aviso claro e separado dos ativos
    de verdade.
    """
    resultado: dict[str, list] = {}
    indisponiveis: dict[str, str] = {}

    for classe in _ORDEM:
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
                resultado["rf"] = rankear_rf(perfil=perfil_risco, limite=n)

            elif classe == "fundos":
                resultado["fundos"] = rankear_fundos(perfil=perfil_risco, limite=n)

            elif classe == "estruturados":
                resultado["estruturados"] = rankear_estruturados(perfil=perfil_risco, limite=n)

        except DadosIndisponiveisError as e:
            logger.warning(f"Classe {classe} indisponível: {e}")
            indisponiveis[classe] = str(e)
        except Exception as e:
            logger.error(f"Erro ao buscar classe {classe}: {e}")
            indisponiveis[classe] = f"Falha inesperada ao buscar dados: {e}"

    return resultado, indisponiveis


# ── Versão legada (compatibilidade) ──────────────────────────────────────────

def recomendar_ativos(
    rec_key: str,
    perfil_risco: int,
    n: int = 5,
    selic: float | None = None,
    ipca: float | None = None,
    ibov_cagr: float | None = None,
) -> list[dict] | None:
    """
    Versão legada — prefira recomendar_por_portfolio().

    `selic`, `ipca` e `ibov_cagr` aceitos apenas por compatibilidade (ver
    nota em recomendar_por_portfolio).

    Sem mock/fallback: se a fonte falhar, propaga a exceção para o
    chamador em vez de devolver um item fake "ERRO" na lista.
    """
    classe = _CLASSE.get(rec_key)
    if classe is None:
        return None
    if classe == "acoes":
        return top_acoes(perfil_risco, n=n)
    if classe == "etf":
        return top_etfs(perfil_risco, n=min(n, 5))
    if classe == "fiis":
        return top_fiis(perfil_risco, n=n)
    if classe == "cripto":
        return top_cripto(perfil_risco, n=min(n, 4))
    if classe == "rf":
        return rankear_rf(perfil=perfil_risco, limite=n)
    if classe == "fundos":
        return rankear_fundos(perfil=perfil_risco, limite=n)
    if classe == "estruturados":
        return rankear_estruturados(perfil=perfil_risco, limite=n)
    return None