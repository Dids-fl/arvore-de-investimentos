"""
BRAPI — https://brapi.dev
Cobre ações, FIIs, Tesouro Direto e índices brasileiros.

Plano gratuito confirmado:
  ✅ quote base    — preço, P/L, EPS, market cap
  ✅ summaryProfile — setor, indústria, descrição, CNPJ
  ✅ balanceSheetHistory — balanço anual (ativos, dívida, PL, caixa)
  ✅ dividendsData  — histórico completo de dividendos e JCP
  ❌ incomeStatementHistory — receita/lucro (Startup+)
  ❌ financialData  — ROE, margens, ROIC (Pro+)

Cadastre-se em brapi.dev e defina BRAPI_TOKEN no .env para aumentar o rate limit.
Sem token: 15 req/min. Com token gratuito: limite maior.
"""

import os
from datetime import date, timedelta
from typing import Optional, List, Dict, Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_URL = "https://brapi.dev/api"

_http = requests.Session()
_retry = Retry(total=2, backoff_factor=0.3, status_forcelist=[429, 500, 502, 503, 504])
_http.mount("https://", HTTPAdapter(max_retries=_retry))


class BrapiClient:
    def __init__(self, token: Optional[str] = None):
        self.token = token or os.getenv("BRAPI_TOKEN", "")

    def _params(self, extra: Optional[dict] = None) -> dict:
        p = {}
        if self.token:
            p["token"] = self.token
        if extra:
            p.update(extra)
        return p

    def _get(self, endpoint: str, params: Optional[dict] = None, timeout=(4, 12)) -> dict:
        url = f"{BASE_URL}/{endpoint.lstrip('/')}"
        r = _http.get(url, params=self._params(params),
                      headers={"User-Agent": "Mozilla/5.0"}, timeout=timeout)
        r.raise_for_status()
        return r.json()

    # ── Cotação base ──────────────────────────────────────────────────────────

    def get_quote(self, ticker: str) -> dict:
        """
        Cotação atual + P/L + EPS + market cap.

        Campos úteis no retorno:
            regularMarketPrice, priceEarnings (P/L),
            earningsPerShare (LPA), marketCap,
            fiftyTwoWeekHigh, fiftyTwoWeekLow, logourl, longName

        Exemplo:
            q = BrapiClient().get_quote("PETR4")
            print(f"Preço: R${q['regularMarketPrice']}  P/L: {q['priceEarnings']}")
        """
        data = self._get(f"quote/{ticker.upper()}")
        results = data.get("results", [])
        if not results:
            raise ValueError(f"Ticker '{ticker}' não encontrado.")
        return results[0]

    def get_quotes(self, tickers: list[str]) -> list[dict]:
        """Cotação de múltiplos tickers em uma só chamada."""
        joined = ",".join(t.upper() for t in tickers)
        data = self._get(f"quote/{joined}")
        return data.get("results", [])

    # ── Dados fundamentalistas (free) ─────────────────────────────────────────

    def get_fundamentals(self, ticker: str) -> dict:
        """
        Busca em uma só chamada:
          • quote base (preço, P/L, EPS, market cap)
          • summaryProfile (setor, indústria, descrição, CNPJ)
          • balanceSheetHistory (balanço dos últimos ~10 anos)
          • dividendsData (histórico completo de proventos)

        Retorna o dict results[0] completo da BRAPI com todos esses campos.

        Exemplo:
            f = BrapiClient().get_fundamentals("ITUB4")
            print(f["summaryProfile"]["sector"])       # "Financeiro"
            print(f["balanceSheetHistory"][0]["cash"]) # caixa mais recente
        """
        data = self._get(
            f"quote/{ticker.upper()}",
            params={
                "modules":  "summaryProfile,balanceSheetHistory",
                "dividends": "true",
            },
        )
        results = data.get("results", [])
        if not results:
            raise ValueError(f"Ticker '{ticker}' não encontrado.")
        return results[0]

    def get_balance_sheet(self, ticker: str) -> list[dict]:
        """
        Balanço patrimonial anual dos últimos ~10 anos.

        Campos mais úteis por ano:
            endDate, cash, totalAssets, totalLiab, shareholdersEquity,
            currentLiabilities, nonCurrentLiabilities,
            loansAndFinancing (dívida CP), longTermLoansAndFinancing (dívida LP),
            inventory, netReceivables

        Exemplo:
            bs = BrapiClient().get_balance_sheet("VALE3")
            ultimo = bs[0]
            divida = ultimo["loansAndFinancing"] + ultimo["longTermLoansAndFinancing"]
            pl     = ultimo["shareholdersEquity"]
            print(f"Dívida/PL: {divida / pl:.2f}")
        """
        fund = self.get_fundamentals(ticker)
        return fund.get("balanceSheetHistory", [])

    def get_dividends(self, ticker: str) -> list[dict]:
        """
        Histórico completo de dividendos e JCP.

        Cada item:
            paymentDate, rate (valor por ação), label (DIVIDENDO/JCP/RENDIMENTO),
            lastDatePrior (data com/sem)

        Exemplo:
            divs = BrapiClient().get_dividends("PETR4")
            # últimos 12 meses
            corte = (date.today() - timedelta(days=365)).isoformat()
            total_12m = sum(d["rate"] for d in divs if d["paymentDate"][:10] >= corte)
            print(f"Proventos últimos 12m: R${total_12m:.4f}/ação")
        """
        fund = self.get_fundamentals(ticker)
        dd = fund.get("dividendsData", {})
        return dd.get("cashDividends", [])

    def get_dividend_summary(self, ticker: str) -> dict:
        """
        Resumo de proventos: total pago em 1a, 3a e 5a, e se é consistente.

        Exemplo:
            s = BrapiClient().get_dividend_summary("ITUB4")
            print(f"DY 12m: R${s['ultimo_1a']:.2f}  Consistente: {s['consistente']}")
        """
        divs   = self.get_dividends(ticker)
        hoje   = date.today()
        d1a    = (hoje - timedelta(days=365)).isoformat()
        d3a    = (hoje - timedelta(days=365 * 3)).isoformat()
        d5a    = (hoje - timedelta(days=365 * 5)).isoformat()

        t1 = sum(d["rate"] for d in divs if d.get("paymentDate", "")[:10] >= d1a)
        t3 = sum(d["rate"] for d in divs if d.get("paymentDate", "")[:10] >= d3a)
        t5 = sum(d["rate"] for d in divs if d.get("paymentDate", "")[:10] >= d5a)

        anos_com_div = len({d["paymentDate"][:4] for d in divs
                            if d.get("paymentDate", "")[:10] >= d5a})
        consistente  = anos_com_div >= 4

        return {
            "ultimo_1a":   round(t1, 4),
            "ultimo_3a":   round(t3, 4),
            "ultimo_5a":   round(t5, 4),
            "consistente": consistente,
        }

    def get_debt_equity(self, ticker: str) -> Optional[float]:
        """
        Dívida Líquida / Patrimônio Líquido do balanço mais recente.
        Calculado com: (dívida CP + dívida LP - caixa) / PL

        Retorna None se não houver dados suficientes.
        """
        bs = self.get_balance_sheet(ticker)
        if not bs:
            return None
        u = bs[0]
        divida = (float(u.get("loansAndFinancing", 0) or 0) +
                  float(u.get("longTermLoansAndFinancing", 0) or 0))
        caixa  = float(u.get("cash", 0) or 0)
        pl     = float(u.get("shareholdersEquity", 0) or 0)
        if pl <= 0:
            return None
        return round((divida - caixa) / pl, 3)

    # ── Histórico de preços ───────────────────────────────────────────────────

    def get_historical(self, ticker: str, range_: str = "5y",
                       interval: str = "1mo") -> list[dict]:
        """
        Histórico de preços.
        range_:   1d | 5d | 1mo | 3mo | 6mo | 1y | 2y | 5y | 10y | ytd | max
        interval: 1d | 1wk | 1mo
        """
        data = self._get(
            f"quote/{ticker.upper()}",
            params={"range": range_, "interval": interval, "history": "true"},
        )
        results = data.get("results", [])
        if not results:
            return []
        return results[0].get("historicalDataPrice", [])

    def get_ibovespa_cagr(self, years: int = 10) -> Optional[float]:
        """CAGR do Ibovespa nos últimos N anos. Substitui o yfinance."""
        try:
            hist = self.get_historical("^BVSP", range_=f"{years}y", interval="1mo")
            if len(hist) < 12:
                return None
            c0 = float(hist[0]["close"])
            c1 = float(hist[-1]["close"])
            anos = len(hist) / 12.0
            if c0 <= 0:
                return None
            return (c1 / c0) ** (1.0 / anos) - 1
        except Exception:
            return None

    # ── FIIs ──────────────────────────────────────────────────────────────────

    def get_fii_list(self) -> list[dict]:
        """Lista FIIs disponíveis na BRAPI com dados básicos."""
        try:
            data = self._get("quote/list", params={"type": "fund", "sortBy": "name"})
            return data.get("stocks", [])
        except Exception:
            return []

    # ── NOVOS MÉTODOS: ENRIQUECIMENTO EM LOTE ────────────────────────────────

    def get_complete_data(self, ticker: str) -> Dict[str, Any]:
        """
        Retorna um dicionário consolidado com dados da BRAPI para um ticker:
          - market_cap (int)
          - balance_sheet (list de dicts)
          - dividend_consistency (bool)
          - historical_prices (list de dicts, últimos 5 anos)
        """
        try:
            fund = self.get_fundamentals(ticker)
            quote = fund  # já contém quote, perfil, balanço, dividendos

            market_cap = quote.get("marketCap", 0)
            balance_sheet = quote.get("balanceSheetHistory", [])
            div_summary = self.get_dividend_summary(ticker)
            historical = self.get_historical(ticker, range_="5y", interval="1mo")

            return {
                "market_cap": market_cap,
                "balance_sheet": balance_sheet,
                "dividend_consistency": div_summary.get("consistente", False),
                "dividend_summary": div_summary,
                "historical_prices": historical,
            }
        except Exception as e:
            # Retorna vazio em caso de erro
            return {
                "market_cap": 0,
                "balance_sheet": [],
                "dividend_consistency": False,
                "dividend_summary": {},
                "historical_prices": [],
            }

    def get_complete_data_batch(self, tickers: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Retorna um dicionário {ticker: dados_completos} para uma lista de tickers.
        Utiliza ThreadPoolExecutor para paralelizar as requisições.
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        results = {}
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_ticker = {executor.submit(self.get_complete_data, t): t for t in tickers}
            for future in as_completed(future_to_ticker):
                ticker = future_to_ticker[future]
                try:
                    results[ticker] = future.result()
                except Exception:
                    results[ticker] = {}
        return results