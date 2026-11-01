"""
Motor de score para Criptomoedas.
Usa CoinGecko para obter dados de market cap, volume e retorno.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from acoes_fiis.ativos import CRIPTO_TOP_N, PESOS_CRIPTO, REF_CRIPTO
from utils.logging_config import get_logger

from .apis.coingecko import CoinGeckoClient

logger = get_logger(__name__)

# ── Normalização ──────────────────────────────────────────────────────────────

def norm(valor: float, bom: float, ruim: float) -> float:
    if abs(bom - ruim) < 1e-9:
        return 0.5
    return max(0.0, min(1.0, (valor - ruim) / (bom - ruim)))

# ── Score de cripto ───────────────────────────────────────────────────────────

def _score_cripto(ind: dict, perfil: int) -> tuple[float, list[str]]:
    pesos  = PESOS_CRIPTO[perfil]
    refs   = REF_CRIPTO
    score  = 0.0
    motivos: list[str] = []

    mc = float(ind.get("market_cap", 0) or 0)
    score += pesos["market_cap"] * norm(mc, refs["market_cap"]["bom"], refs["market_cap"]["ruim"])
    if perfil == 1:
        label = "✅" if mc > 500_000_000_000 else "ℹ️ "
        motivos.append(f"{label} Market cap: R${mc/1e9:.0f}B {'(reserva de valor)' if mc > 500_000_000_000 else ''}")
    else:
        motivos.append(f"Market cap: R${mc/1e9:.0f}B")

    vol = float(ind.get("volume", 0) or 0)
    score += pesos["volume"] * norm(vol, refs["volume"]["bom"], refs["volume"]["ruim"])

    ret = float(ind.get("retorno_12m", 0) or 0)
    score += pesos["retorno_12m"] * norm(ret, refs["retorno_12m"]["bom"], refs["retorno_12m"]["ruim"])
    if perfil == 3:
        label = "✅" if ret > 80 else ("ℹ️ " if ret > 20 else "⚠️ ")
        motivos.append(f"{label} Retorno 12m: {ret:+.1f}% ← critério principal")
    else:
        label = "✅" if ret > 50 else ("ℹ️ " if ret > 0 else "⚠️ ")
        motivos.append(f"{label} Retorno 12m: {ret:+.1f}%")

    vol_a = float(ind.get("volatilidade_anual", 0) or 0)
    if vol_a > 0:
        if perfil == 1:
            motivos.append(f"{'✅' if vol_a < 60 else '⚠️ '} Volatilidade: {vol_a:.0f}%/ano")
        else:
            motivos.append(f"Volatilidade anual: {vol_a:.0f}%")

    return round(score * 100, 1), motivos[:4]

# ── Universo elegível ───────────────────────────────────────────────────────────

# Categorias da CoinGecko que não representam exposição a cripto: moedas
# atreladas ao dólar, versões "embrulhadas"/de staking de outra moeda (seriam
# a mesma posição duas vezes) e ouro tokenizado. Ativos atrelados que não
# estejam nessas categorias são pegos por _parece_atrelada().
CATEGORIAS_EXCLUIDAS = (
    "stablecoins",
    "wrapped-tokens",
    "liquid-staking-tokens",
    "tokenized-gold",
)
# Margem do universo bruto: parte das maiores moedas é excluída pelo filtro.
_UNIVERSO_BRUTO = 60


def _parece_atrelada(item: dict) -> bool:
    """Detecta moedas sem oscilação relevante (ex.: stablecoin não categorizada)."""
    var_1a = item.get("price_change_percentage_1y_in_currency")
    var_30d = item.get("price_change_percentage_30d_in_currency")
    if var_1a is None or var_30d is None:
        return False
    return abs(float(var_1a)) < 5 and abs(float(var_30d)) < 1.5


def _ids_excluidos(cg: CoinGeckoClient) -> set[str]:
    excluidos: set[str] = set()
    for categoria in CATEGORIAS_EXCLUIDAS:
        try:
            excluidos |= cg.get_ids_categoria(categoria)
        except (requests.exceptions.RequestException, ValueError, TypeError, KeyError) as exc:
            logger.warning("Categoria %s indisponível na CoinGecko: %s", categoria, exc)
    return excluidos


# ── Top Cripto ─────────────────────────────────────────────────────────────────

def top_cripto(perfil: int, n: int = 4) -> list[dict]:
    """
    Busca as maiores criptos por market cap na CoinGecko e rankeia pelo perfil.

    O retorno de 12 meses vem da própria listagem de mercado (uma chamada);
    o histórico diário, mais caro na API gratuita, só é buscado para os
    finalistas, para informar a volatilidade.
    """
    try:
        cg = CoinGeckoClient()
        mkt = cg.get_markets_top(top_n=_UNIVERSO_BRUTO)
    except (requests.exceptions.RequestException, ValueError, TypeError, RuntimeError) as e:
        logger.error(f"Erro ao buscar cripto: {e}")
        return []

    excluidos = _ids_excluidos(cg)
    universo = [
        item
        for item in mkt
        if isinstance(item, dict)
        and item.get("id") not in excluidos
        and not _parece_atrelada(item)
    ][:CRIPTO_TOP_N]

    resultados = []
    for item in universo:
        retorno = item.get("price_change_percentage_1y_in_currency")
        ind = {
            "market_cap":         item.get("market_cap",   0),
            "volume":             item.get("total_volume", 0),
            "retorno_12m":        retorno if retorno is not None else 0.0,
            "volatilidade_anual": 0.0,
        }
        score, motivos = _score_cripto(ind, perfil)
        if retorno is None:
            motivos.append("⚠️  Sem 12 meses de histórico")
        resultados.append({
            "id":          item.get("id"),
            "ticker":      item.get("symbol", "").upper(),
            "nome":        item.get("name", ""),
            "preco":       item.get("current_price", 0),
            "score":       score,
            "motivos":     motivos,
            "retorno_12m": ind["retorno_12m"],
            "market_cap":  ind["market_cap"],
        })

    finalistas = sorted(resultados, key=lambda x: -x["score"])[:n]

    with ThreadPoolExecutor(max_workers=2) as ex:
        futuros = {
            ex.submit(cg.get_retorno_e_volatilidade, ativo["id"]): ativo
            for ativo in finalistas
        }
        for fut in as_completed(futuros):
            ativo = futuros[fut]
            try:
                volatilidade = fut.result().get("volatilidade_anual") or 0.0
            except (requests.exceptions.RequestException, ValueError, TypeError, RuntimeError, AttributeError) as exc:
                logger.debug("Falha ao buscar volatilidade de %s: %s", ativo["id"], exc)
                continue
            if volatilidade > 0:
                ativo["volatilidade_anual"] = volatilidade
                ativo["motivos"].append(f"Volatilidade anual: {volatilidade:.0f}%")

    for ativo in finalistas:
        ativo.pop("id", None)
    return finalistas
