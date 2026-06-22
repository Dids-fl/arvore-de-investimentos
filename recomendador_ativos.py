"""
Traduz o portfólio em sugestões de ativos específicos por classe.

Classes suportadas e fonte dos dados
─────────────────────────────────────
  acoes  → Status Invest API (principal) → BRAPI → FMP → Fundamentus (fallback)
  etf    → ETFs recomendados para iniciantes/perfil moderado (BOVA11, IVVB11, SMALL11)
  fiis   → Status Invest API  — top 100, score dinâmico por perfil
  cripto → CoinGecko API      — top 20,  score dinâmico por perfil
  rf     → apis/rf_mercado.py — taxas derivadas de SELIC/IPCA/CDI reais,
                                filtradas e rankeadas por perfil
  fundos → apis/rf_mercado.py — retorno líquido real estimado por cenário,
                                filtrados e rankeados por perfil

Filtros por perfil (RF e Fundos)
─────────────────────────────────
  Conservador: produtos com FGC ou garantia governo, liquidez >= diária/1a
  Moderado:    todos os produtos RF + fundos DI/multi/debn
  Agressivo:   foca em maior retorno real — IPCA+, CRI/CRA, long biased, IVVB11
"""

from categorias import RK
from screener import top_acoes, top_fiis, top_cripto, _score_acao
from apis.rf_mercado import calcular_rf, calcular_fundos
from utils.logging_config import get_logger

logger = get_logger(__name__)

# ── Mapeamento rk → classe ────────────────────────────────────────────────────

_CLASSE: dict[str, str] = {
    # Ações / ETFs
    RK.RV:               "acoes",
    RK.RV_DCA:           "acoes",
    RK.RV_COMPL:         "acoes",
    RK.FUNDOS_ACOES:     "acoes",
    RK.FUNDOS_ACOES_ETF: "etf",   # <--- CORRIGIDO: agora mapeia para "etf"
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
    "acoes":  "AÇÕES / ETFs",
    "etf":    "ETFs (Fundos de Índice)",  # <--- NOVO
    "fiis":   "FIIs",
    "cripto": "CRIPTO",
    "rf":     "RENDA FIXA",
    "fundos": "FUNDOS",
}

MIN_PCT = 5   # alocação mínima no portfólio para gerar sugestão da classe


# ── Filtros de RF por perfil ──────────────────────────────────────────────────

# Tickers permitidos por perfil (subset da lista completa de calcular_rf)
_RF_PERFIL: dict[int, list[str]] = {
    1: ["SELIC", "CDB-DI", "LCI/LCA"],           # só com FGC ou governo, liquidez alta
    2: ["SELIC", "CDB-DI", "LCI/LCA", "IPCA+", "DEBN"],   # adiciona IPCA+ e debn
    3: ["IPCA+", "DEBN", "CRI/CRA", "CDB-DI"],   # maior retorno real; mantém CDB como âncora
}

# Tickers permitidos por perfil para fundos
_FUNDOS_PERFIL: dict[int, list[str]] = {
    1: ["FDO-RF", "FDO-PREV"],                          # baixo risco, sem exposição a crédito privado
    2: ["FDO-MULTI", "FDO-DEBN", "FDO-RF", "FDO-PREV"], # equilíbrio
    3: ["FDO-LONG", "IVVB11", "FDO-MULTI", "FDO-DEBN"], # crescimento e diversificação global
}


def _filtrar_rf_por_perfil(
    todos: list[dict], perfil: int, n: int
) -> list[dict]:
    """
    Filtra e ordena os produtos de RF calculados por rf_mercado.py
    de acordo com o perfil de risco, retornando os top N.
    """
    permitidos = set(_RF_PERFIL.get(perfil, _RF_PERFIL[2]))
    filtrados  = [p for p in todos if p.get("ticker") in permitidos]
    # já vêm ordenados por score de rf_mercado; mantém a ordem
    return filtrados[:n]


def _filtrar_fundos_por_perfil(
    todos: list[dict], perfil: int, n: int
) -> list[dict]:
    """
    Filtra e ordena os fundos calculados por rf_mercado.py
    de acordo com o perfil de risco, retornando os top N.
    """
    permitidos = set(_FUNDOS_PERFIL.get(perfil, _FUNDOS_PERFIL[2]))
    filtrados  = [f for f in todos if f.get("ticker") in permitidos]
    return filtrados[:n]


def _recomendar_etfs(perfil: int, n: int = 3, ibov_cagr: float = None) -> list[dict]:
    """
    Recomenda ETFs (BOVA11, IVVB11, SMALL11) com base no perfil de risco.
    """
    ibov = ibov_cagr if ibov_cagr else 0.13
    etfs = [
        {
            "ticker": "BOVA11",
            "nome": "ETF Ibovespa (B3)",
            "preco": 0,
            "score": 70 if ibov > 0.10 else 50,
            "motivos": [
                f"✅ Exposição às maiores empresas do Brasil",
                "✅ Taxa de administração ~0.3% a.a.",
                "✅ Ideal para iniciantes (diversificação automática)",
                f"📈 Retorno histórico estimado: {ibov*100:.1f}% a.a."
            ]
        },
        {
            "ticker": "IVVB11",
            "nome": "ETF S&P 500 (BRL)",
            "preco": 0,
            "score": 75,
            "motivos": [
                "✅ Diversificação internacional (500 maiores dos EUA)",
                "✅ Proteção cambial (dólar)",
                "✅ Taxa de administração ~0.24% a.a.",
                "📈 Retorno histórico S&P500 ~10% a.a. + câmbio"
            ]
        },
        {
            "ticker": "SMALL11",
            "nome": "ETF Small Caps Brasil",
            "preco": 0,
            "score": 55,
            "motivos": [
                "✅ Exposição a empresas menores com maior potencial de crescimento",
                "⚠️  Maior volatilidade que BOVA11",
                "📈 Indicado para pequena parcela (até 20% da carteira de ações)"
            ]
        }
    ]
    # Ajusta score conforme perfil
    if perfil == 1:  # conservador
        etfs[0]["score"] += 5  # BOVA11 mais seguro
        etfs[2]["score"] -= 10 # SMALL11 muito volátil
    elif perfil == 3:  # agressivo
        etfs[2]["score"] += 10 # SMALL11 ganha peso
    return sorted(etfs, key=lambda x: -x["score"])[:n]


# ── Função principal ──────────────────────────────────────────────────────────

def recomendar_por_portfolio(
    portfolio:   dict,
    perfil_risco: int,
    n:           int   = 5,
    selic:       float = 0.1425,
    ipca:        float = 0.044,
    ibov_cagr:   float | None = None,
) -> dict[str, list]:
    """
    Recebe o portfólio completo e retorna os top N ativos de cada classe
    que tiver alocação >= MIN_PCT no portfólio.

    RF e Fundos usam as taxas reais passadas (selic, ipca, ibov_cagr)
    para calcular retorno líquido real e rankear dinamicamente.

    Retorna dict com chaves: "rf", "fundos", "fiis", "acoes", "cripto", "etf"
    (apenas as classes presentes no portfólio).
    """
    classes: set[str] = {
        _CLASSE[rk]
        for rk, pct in portfolio.items()
        if pct >= MIN_PCT and rk in _CLASSE
    }

    if not classes:
        return {}

    ordem    = ["rf", "fundos", "fiis", "acoes", "etf", "cripto"]
    resultado: dict[str, list] = {}

    for classe in ordem:
        if classe not in classes:
            continue
        try:
            if classe == "acoes":
                # Tenta as fontes principais (Status Invest → BRAPI → FMP)
                acoes = top_acoes(perfil_risco, n=n)
                
                # ── Fallback para Fundamentus se as principais falharem ──
                if not acoes:
                    logger.info("Ações: fallback para Fundamentus via scraping")
                    try:
                        from apis.fundamentus import search_stocks as fundamentus_search
                        universo_fund = fundamentus_search(limit=100)
                        if universo_fund:
                            candidatos = []
                            for item in universo_fund:
                                # Adiciona campos extras que _score_acao espera
                                item['mktcap_proxy'] = 0
                                item['cotacao'] = item.get('cotacao', 0)
                                item['liquidez'] = item.get('liquidez', 0)
                                item['pvp'] = item.get('pvp', 0)
                                item['pl'] = item.get('pl', 0)
                                item['roe'] = item.get('roe', 0)
                                item['dy'] = item.get('dy', 0)
                                
                                score, motivos = _score_acao(item, perfil_risco)
                                candidatos.append({
                                    "ticker": item.get("ticker", ""),
                                    "nome": item.get("nome", ""),
                                    "preco": float(item.get("cotacao", 0)),
                                    "score": score,
                                    "motivos": motivos[:4],
                                    "dy": item.get("dy", 0),
                                    "roe": item.get("roe", 0),
                                    "pl": item.get("pl", 0),
                                    "confianca": 1.0,
                                })
                            acoes = sorted(candidatos, key=lambda x: -x["score"])[:n]
                            logger.info(f"Fundamentus retornou {len(acoes)} ativos")
                    except ImportError:
                        logger.warning("BeautifulSoup4 não instalado. Fundamentus indisponível.")
                    except Exception as e:
                        logger.error(f"Erro no fallback do Fundamentus: {e}")
                
                resultado["acoes"] = acoes

            elif classe == "etf":
                # Recomenda ETFs fixos com base no perfil
                resultado["etf"] = _recomendar_etfs(perfil_risco, n=min(n, 3), ibov_cagr=ibov_cagr)

            elif classe == "fiis":
                resultado["fiis"]   = top_fiis(perfil_risco, n=n)

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
                "ticker":  "ERRO",
                "score":   0,
                "preco":   0,
                "nome":    "",
                "motivos": [f"Falha ao buscar dados: {e}"],
            }]

    return resultado


# ── Versão legada (compatibilidade) ──────────────────────────────────────────

def recomendar_ativos(
    rec_key:     str,
    perfil_risco: int,
    n:           int   = 5,
    selic:       float = 0.1425,
    ipca:        float = 0.044,
    ibov_cagr:   float | None = None,
) -> list[dict] | None:
    """Versão legada — prefira recomendar_por_portfolio()."""
    classe = _CLASSE.get(rec_key)
    if classe is None:
        return None
    try:
        if classe == "acoes":
            return top_acoes(perfil_risco, n=n)
        if classe == "etf":
            return _recomendar_etfs(perfil_risco, n=min(n, 3), ibov_cagr=ibov_cagr)
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