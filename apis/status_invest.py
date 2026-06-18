"""
Status Invest — https://statusinvest.com.br
API não oficial. Excelente para FIIs e ações brasileiras.

⚠️  Por ser não oficial, os endpoints podem mudar sem aviso.
    Se parar de funcionar, verifique os headers e URLs na aba Network do browser.

Não requer token/cadastro.
"""

import time
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_URL = "https://statusinvest.com.br"

# Headers que simulam um browser real (necessário para a API não oficial)
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "pt-BR,pt;q=0.9",
    "Referer":         "https://statusinvest.com.br/",
    "Origin":          "https://statusinvest.com.br",
}

_http = requests.Session()
_retry = Retry(total=2, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])
_http.mount("https://", HTTPAdapter(max_retries=_retry))


class StatusInvestClient:

    def _get(self, path: str, params: Optional[dict] = None, timeout=(5, 15)) -> dict:
        url = f"{BASE_URL}/{path.lstrip('/')}"
        r = _http.get(url, params=params, headers=_HEADERS, timeout=timeout)
        r.raise_for_status()
        return r.json()

    # ── FIIs ─────────────────────────────────────────────────────────────────

    def get_fii_indicators(self, ticker: str) -> dict:
        """
        Indicadores detalhados de um FII específico.

        Retorna dict com:
            dy          — Dividend Yield 12 meses (%)
            p_vp        — Preço / Valor Patrimonial
            vacancia    — Taxa de vacância (%)
            tipo        — "Tijolo" | "Papel" | "Híbrido" | "FOF"
            liquidez    — Liquidez diária média (R$)
            cotacao     — Cotação atual
            patrimonio  — Patrimônio líquido (R$)
            ticker      — Ticker
            nome        — Nome do fundo

        Exemplo:
            client = StatusInvestClient()
            dados = client.get_fii_indicators("HGLG11")
            print(f"DY: {dados['dy']}%  P/VP: {dados['p_vp']}")
        """
        try:
            data = self._get(f"fundos-imobiliarios/{ticker.upper()}")
            return {
                "ticker":     ticker.upper(),
                "nome":       data.get("companyName", ""),
                "cotacao":    data.get("price", 0),
                "dy":         data.get("dy", 0),
                "p_vp":       data.get("p_vp", 0),
                "vacancia":   data.get("vacancyRate", 0),
                "tipo":       data.get("segment", ""),
                "liquidez":   data.get("liquidityAvg", 0),
                "patrimonio": data.get("patrimonioLiquido", 0),
            }
        except Exception as e:
            raise RuntimeError(f"Erro ao buscar dados do FII '{ticker}': {e}")

    def search_fiis(self, tipo: Optional[str] = None, dy_min: float = 0.0,
                    p_vp_max: float = 9.99, limit: int = 100) -> list[dict]:
        """
        Busca FIIs com filtros básicos.

        tipo:     "Tijolo" | "Papel" | "Híbrido" | "FOF" | None (todos)
        dy_min:   Dividend Yield mínimo (%)
        p_vp_max: P/VP máximo
        limit:    Número máximo de resultados

        Retorna lista de dicts com os mesmos campos de get_fii_indicators.

        Exemplo — top FIIs de papel com DY > 10%:
            fiis = client.search_fiis(tipo="Papel", dy_min=10.0)
        """
        try:
            search = {}
            if tipo:
                search["Segment"] = tipo
            data = self._get(
                "category/advancedsearchresultpaginated",
                params={
                    "search":       str(search).replace("'", '"'),
                    "categoryType": "2",
                    "types":        "2",
                    "take":         limit,
                    "skip":         0,
                    "sortField":    "dy",
                    "sortOrder":    "-1",
                },
            )
            items = data.get("list", [])
            result = []
            for item in items:
                dy  = float(item.get("dy",    0) or 0)
                pv  = float(item.get("p_vp",  0) or 0)
                liq = float(
                    item.get("liquidityAvg") or
                    item.get("liquidity") or
                    item.get("avgDailyLiquidity") or
                    item.get("vol") or 0
                )
                if dy >= dy_min and pv <= p_vp_max:
                    result.append({
                        "ticker":   item.get("ticker", ""),
                        "nome":     item.get("companyName", ""),
                        "cotacao":  float(item.get("price", 0) or 0),
                        "dy":       dy,
                        "pvp":      pv,
                        "vacancia": float(item.get("vacancyRate", 0) or 0),
                        "tipo":     item.get("segment", ""),
                        "liquidez": liq,
                    })
            return result[:limit]
            return result[:limit]
        except Exception as e:
            raise RuntimeError(f"Erro ao buscar FIIs: {e}")

    def get_top_fiis(self, n: int = 10) -> list[dict]:
        """
        Retorna os N FIIs com maior DY, excluindo os com P/VP > 1.5 (sobrevalorizados).

        Uso prático: enriquecer a recomendação de RK.FIIS com dados reais.

        Exemplo:
            top = client.get_top_fiis(5)
            for f in top:
                print(f"{f['ticker']}: DY {f['dy']:.1f}%  P/VP {f['p_vp']:.2f}")
        """
        return self.search_fiis(dy_min=5.0, p_vp_max=1.5, limit=n)

    # ── Ações ─────────────────────────────────────────────────────────────────

    def get_stock_indicators(self, ticker: str) -> dict:
        """
        Indicadores fundamentalistas de uma ação brasileira.

        Retorna dict com:
            ticker, nome, cotacao, dy (%), p_l, p_vp, roe (%), roic (%),
            margem_liquida (%), divida_patrimonio, crescimento_receita_5a (%)

        Exemplo:
            dados = client.get_stock_indicators("ITUB4")
            print(f"P/L: {dados['p_l']}  ROE: {dados['roe']}%")
        """
        try:
            data = self._get(f"acoes/{ticker.upper()}")
            return {
                "ticker":                  ticker.upper(),
                "nome":                    data.get("companyName", ""),
                "cotacao":                 data.get("price", 0),
                "dy":                      data.get("dy", 0),
                "p_l":                     data.get("p_l", 0),
                "p_vp":                    data.get("p_vp", 0),
                "roe":                     data.get("roe", 0),
                "roic":                    data.get("roic", 0),
                "margem_liquida":          data.get("margemLiquida", 0),
                "divida_patrimonio":       data.get("liquidezCorrente", 0),
                "crescimento_receita_5a":  data.get("cagr5AnosReceita", 0),
            }
        except Exception as e:
            raise RuntimeError(f"Erro ao buscar dados da ação '{ticker}': {e}")

    def search_stocks(self, dy_min: float = 0.0, p_l_max: float = 999.0,
                      roe_min: float = 0.0, limit: int = 150) -> list[dict]:
        """
        Busca ações com filtros básicos. Padrão: universo amplo ordenado por DY.
        Retorna campos: ticker, nome, cotacao, dy, pl, pvp, roe, liquidez.

        Exemplo — universo completo (sem filtro):
            acoes = client.search_stocks(limit=150)

        Exemplo — ações baratas com boa rentabilidade:
            acoes = client.search_stocks(dy_min=5.0, roe_min=15.0)
        """
        try:
            data = self._get(
                "category/advancedsearchresultpaginated",
                params={
                    "search":       "{}",
                    "categoryType": "1",
                    "types":        "1,2",
                    "take":         limit,
                    "skip":         0,
                    "sortField":    "dy",
                    "sortOrder":    "-1",
                },
            )
            items = data.get("list", [])
            result = []
            for item in items:
                dy  = float(item.get("dy",  0) or 0)
                pl  = float(item.get("p_l", 0) or 0)
                roe = float(item.get("roe", 0) or 0)
                liq = float(
                    item.get("liquidityAvg") or
                    item.get("liquidity") or
                    item.get("avgDailyLiquidity") or
                    item.get("vol") or 0
                )
                if dy >= dy_min and roe >= roe_min:
                    result.append({
                        "ticker":   item.get("ticker", ""),
                        "nome":     item.get("companyName", ""),
                        "cotacao":  float(item.get("price", 0) or 0),
                        "dy":       dy,
                        "pl":       pl,
                        "pvp":      float(item.get("p_vp", 0) or 0),
                        "roe":      roe,
                        "liquidez": liq,
                    })
            return result
        except Exception as e:
            raise RuntimeError(f"Erro ao buscar ações: {e}")