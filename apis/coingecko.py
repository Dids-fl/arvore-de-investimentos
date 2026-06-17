"""
CoinGecko — https://coingecko.com/api
API oficial, gratuita, sem cadastro necessário.
Limite: 30 req/min no plano free.

Cobre: market cap, volume, retorno histórico, preço atual.
"""

from typing import Optional
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_URL = "https://api.coingecko.com/api/v3"

_http = requests.Session()
_retry = Retry(total=2, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])
_http.mount("https://", HTTPAdapter(max_retries=_retry))

_HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}


class CoinGeckoClient:

    def _get(self, endpoint: str, params: Optional[dict] = None, timeout=(4, 12)) -> dict | list:
        url = f"{BASE_URL}/{endpoint.lstrip('/')}"
        r = _http.get(url, params=params, headers=_HEADERS, timeout=timeout)
        r.raise_for_status()
        return r.json()

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
        except Exception:
            return {"retorno_12m_pct": 0.0, "volatilidade_anual": 0.0}