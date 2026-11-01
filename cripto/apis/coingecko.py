"""
CoinGecko — https://coingecko.com/api
API oficial, gratuita, sem cadastro necessário.
Limite: 30 req/min no plano free.

Cobre: market cap, volume, retorno histórico, preço atual.
"""


import json
import threading
import time
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_URL = "https://api.coingecko.com/api/v3"

_http = requests.Session()
# A API gratuita responde 429 com Retry-After de até ~60 s. Esperar por isso
# trava a interface; uma nova tentativa curta basta e o resto vem do cache.
_retry = Retry(
    total=1,
    backoff_factor=1.0,
    status_forcelist=[429, 500, 502, 503, 504],
    respect_retry_after_header=False,
)
_http.mount("https://", HTTPAdapter(max_retries=_retry))

# Dados opcionais (volatilidade): sem nova tentativa, para não gastar a cota.
_http_opcional = requests.Session()
_http_opcional.mount("https://", HTTPAdapter(max_retries=Retry(total=0)))

_CACHE_DIR = Path.home() / ".cache" / "arvore_investimentos"
_TTL_MERCADO_S = 10 * 60
_TTL_CATEGORIA_S = 7 * 24 * 60 * 60
_cache_memoria: dict[str, tuple[float, object]] = {}
_cache_lock = threading.Lock()


def _ler_cache(chave: str, ttl: float) -> object | None:
    with _cache_lock:
        item = _cache_memoria.get(chave)
    if item and time.time() - item[0] <= ttl:
        return item[1]
    arquivo = _CACHE_DIR / f"coingecko_{chave}.json"
    try:
        salvo = json.loads(arquivo.read_text(encoding="utf-8"))
        if time.time() - float(salvo["ts"]) <= ttl:
            with _cache_lock:
                _cache_memoria[chave] = (float(salvo["ts"]), salvo["dados"])
            return salvo["dados"]
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def _gravar_cache(chave: str, dados: object) -> None:
    agora = time.time()
    with _cache_lock:
        _cache_memoria[chave] = (agora, dados)
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        destino = _CACHE_DIR / f"coingecko_{chave}.json"
        temporario = destino.with_suffix(".tmp")
        temporario.write_text(json.dumps({"ts": agora, "dados": dados}), encoding="utf-8")
        temporario.replace(destino)
    except OSError:
        pass

_HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}


class CoinGeckoClient:

    def _get(
        self,
        endpoint: str,
        params: dict | None = None,
        timeout=(4, 12),
        *,
        opcional: bool = False,
    ) -> dict | list:
        url = f"{BASE_URL}/{endpoint.lstrip('/')}"
        sessao = _http_opcional if opcional else _http
        r = sessao.get(url, params=params, headers=_HEADERS, timeout=timeout)
        r.raise_for_status()
        return r.json()

    def get_markets_top(self, top_n: int = 20, vs_currency: str = "brl") -> list[dict]:
        """
        Top N criptos por market cap — universo dinâmico, sem lista fixa.

        Exemplo:
            top20 = CoinGeckoClient().get_markets_top(20)
            for c in top20:
                print(f"{c['name']}: R${c['current_price']:,.2f}")
        """
        chave = f"mercado_{vs_currency}_{top_n}"
        em_cache = _ler_cache(chave, _TTL_MERCADO_S)
        if isinstance(em_cache, list):
            return em_cache
        dados = self._get(
            "coins/markets",
            params={
                "vs_currency":             vs_currency,
                "order":                   "market_cap_desc",
                "per_page":                top_n,
                "page":                    1,
                "sparkline":               "false",
                "price_change_percentage": "24h,7d,30d,1y",
            },
        )
        if isinstance(dados, list) and dados:
            _gravar_cache(chave, dados)
        return dados

    def get_ids_categoria(self, categoria: str, vs_currency: str = "brl") -> set[str]:
        """IDs das moedas de uma categoria da CoinGecko (ex.: "stablecoins").

        Uma chamada por categoria; usado para excluir do ranking ativos que
        não são investimento em cripto propriamente dito.
        """
        chave = f"categoria_{categoria}"
        em_cache = _ler_cache(chave, _TTL_CATEGORIA_S)
        if isinstance(em_cache, list):
            return set(em_cache)
        dados = self._get(
            "coins/markets",
            params={
                "vs_currency": vs_currency,
                "category": categoria,
                "order": "market_cap_desc",
                "per_page": 250,
                "page": 1,
                "sparkline": "false",
            },
        )
        ids = {item["id"] for item in dados if isinstance(item, dict) and "id" in item}
        if ids:
            _gravar_cache(chave, sorted(ids))
        return ids

    def get_markets(self, ids: list[str], vs_currency: str = "brl") -> list[dict]:
        """
        Dados de mercado de uma lista de moedas.

        ids: lista de coin_id da CoinGecko (ex: ["bitcoin", "ethereum"])

        Cada item retorna:
            id, symbol, name, current_price, market_cap, total_volume,
            price_change_percentage_24h, price_change_percentage_7d_in_currency,
            price_change_percentage_30d_in_currency,
            ath (all-time high), atl (all-time low)

        Exemplo:
            cg = CoinGeckoClient()
            dados = cg.get_markets(["bitcoin", "ethereum"])
            for c in dados:
                print(f"{c['name']}: R${c['current_price']:,.2f}  "
                      f"MCap: R${c['market_cap']/1e9:.1f}B")
        """
        return self._get(
            "coins/markets",
            params={
                "vs_currency":                    vs_currency,
                "ids":                            ",".join(ids),
                "order":                          "market_cap_desc",
                "sparkline":                      "false",
                "price_change_percentage":        "24h,7d,30d",
                "locale":                         "pt",
            },
        )

    def get_coin_history(self, coin_id: str, days: int = 365,
                         vs_currency: str = "brl") -> dict:
        """
        Histórico de preços para calcular retorno e volatilidade.

        Retorna dict com:
            prices       — [[timestamp, preco], ...]
            market_caps  — [[timestamp, mktcap], ...]
            total_volumes — [[timestamp, volume], ...]

        Exemplo:
            hist = CoinGeckoClient().get_coin_history("bitcoin", days=365)
            precos = [p[1] for p in hist["prices"]]
        """
        return self._get(
            f"coins/{coin_id}/market_chart",
            params={"vs_currency": vs_currency, "days": days, "interval": "daily"},
            opcional=True,
        )

    def get_retorno_e_volatilidade(self, coin_id: str) -> dict:
        """
        Calcula retorno 12m e volatilidade anualizada a partir do histórico.

        Retorna:
            retorno_12m_pct   — retorno percentual nos últimos 365 dias
            volatilidade_anual — desvio padrão anualizado (proxy de risco)

        Exemplo:
            rv = CoinGeckoClient().get_retorno_e_volatilidade("ethereum")
            print(f"Retorno 12m: {rv['retorno_12m_pct']:.1f}%  "
                  f"Volatilidade: {rv['volatilidade_anual']:.1f}%")
        """
        import math
        try:
            hist   = self.get_coin_history(coin_id, days=365)
            precos = [p[1] for p in hist.get("prices", []) if p[1] > 0]
            if len(precos) < 30:
                return {"retorno_12m_pct": 0.0, "volatilidade_anual": 0.0}

            retorno_12m = (precos[-1] / precos[0] - 1) * 100

            # Retornos diários para volatilidade
            retornos_d = [(precos[i] / precos[i - 1] - 1)
                          for i in range(1, len(precos))]
            media = sum(retornos_d) / len(retornos_d)
            var   = sum((r - media) ** 2 for r in retornos_d) / len(retornos_d)
            vol_d = math.sqrt(var)
            vol_a = vol_d * math.sqrt(365) * 100  # anualizada em %

            return {
                "retorno_12m_pct":   round(retorno_12m, 2),
                "volatilidade_anual": round(vol_a, 2),
            }
        except (requests.exceptions.RequestException, ValueError, TypeError, KeyError, ZeroDivisionError, AttributeError):
            return {"retorno_12m_pct": 0.0, "volatilidade_anual": 0.0}
