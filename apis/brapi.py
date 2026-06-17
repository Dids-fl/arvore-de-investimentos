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
from typing import Optional

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

    # ── Score com dados disponíveis no free ───────────────────────────────────

    def score_stock_free(self, ticker: str, perfil_risco: int,
                         preco_atual: Optional[float] = None) -> dict:
        """
        Pontuação de ação usando APENAS dados do plano gratuito da BRAPI:
          • P/L (da quote)
          • Dívida/PL (do balanço)
          • Consistência e volume de dividendos (de dividendsData)

        NÃO usa: ROE, margens, crescimento de receita (requer Startup+).
        Para análise completa, combine com StatusInvestClient.get_stock_indicators().

        perfil_risco: 1 = conservador | 2 = moderado | 3 = agressivo

        Retorna:
            score (0-100), apto (bool), motivos (list), indicadores (dict)
        """
        try:
            fund      = self.get_fundamentals(ticker)
            pl        = float(fund.get("priceEarnings", 0) or 0)
            eps       = float(fund.get("earningsPerShare", 0) or 0)
            mkt_cap   = float(fund.get("marketCap", 0) or 0)
            preco     = preco_atual or float(fund.get("regularMarketPrice", 0) or 0)

            bs        = fund.get("balanceSheetHistory", [])
            divs_data = fund.get("dividendsData", {})
            divs      = divs_data.get("cashDividends", [])
        except Exception as e:
            return {"score": 0, "apto": False,
                    "motivos": [f"Erro ao buscar dados: {e}"],
                    "indicadores": {}}

        # Dívida líquida / PL
        debt_equity = None
        if bs:
            u      = bs[0]
            divida = (float(u.get("loansAndFinancing", 0) or 0) +
                      float(u.get("longTermLoansAndFinancing", 0) or 0))
            caixa  = float(u.get("cash", 0) or 0)
            pl_val = float(u.get("shareholdersEquity", 0) or 0)
            if pl_val > 0:
                debt_equity = (divida - caixa) / pl_val

        # Dividendos 12 meses e consistência
        hoje  = date.today()
        d1a   = (hoje - timedelta(days=365)).isoformat()
        d5a   = (hoje - timedelta(days=365 * 5)).isoformat()
        div_1a = sum(d["rate"] for d in divs if d.get("paymentDate", "")[:10] >= d1a)
        dy_pct = (div_1a / preco * 100) if preco > 0 else 0
        anos_c = len({d["paymentDate"][:4] for d in divs
                      if d.get("paymentDate", "")[:10] >= d5a})
        consistente = anos_c >= 4

        indicadores = {
            "p_l":              round(pl, 1),
            "eps":              round(eps, 4),
            "div_yield_pct":    round(dy_pct, 2),
            "div_12m_por_acao": round(div_1a, 4),
            "dividendos_consistentes": consistente,
            "divida_liquida_pl": round(debt_equity, 2) if debt_equity is not None else None,
            "market_cap_bi":    round(mkt_cap / 1e9, 1),
        }

        score   = 0
        motivos = []

        # P/L
        if 0 < pl <= 10:
            score += 25; motivos.append(f"✅ P/L muito atrativo: {pl:.1f}")
        elif 10 < pl <= 18:
            score += 18; motivos.append(f"✅ P/L razoável: {pl:.1f}")
        elif 18 < pl <= 30:
            score += 8;  motivos.append(f"ℹ️  P/L elevado: {pl:.1f}")
        elif pl <= 0:
            motivos.append("❌ Lucro negativo (P/L inválido)")
        else:
            motivos.append(f"❌ P/L alto demais: {pl:.1f}")

        # Dividend Yield
        if perfil_risco == 1:
            if dy_pct >= 7:
                score += 30; motivos.append(f"✅ DY excelente: {dy_pct:.1f}%")
            elif dy_pct >= 5:
                score += 20; motivos.append(f"✅ DY bom: {dy_pct:.1f}%")
            elif dy_pct >= 3:
                score += 10; motivos.append(f"ℹ️  DY moderado: {dy_pct:.1f}%")
            else:
                motivos.append(f"❌ DY baixo para conservador: {dy_pct:.1f}%")
        elif perfil_risco == 2:
            if dy_pct >= 4:
                score += 20; motivos.append(f"✅ DY bom: {dy_pct:.1f}%")
            elif dy_pct >= 2:
                score += 10; motivos.append(f"ℹ️  DY moderado: {dy_pct:.1f}%")
        else:
            if dy_pct >= 3:
                score += 10; motivos.append(f"ℹ️  DY: {dy_pct:.1f}% (bônus)")

        # Consistência de dividendos
        if consistente:
            score += 20; motivos.append(f"✅ Pagou dividendos em {anos_c}/5 últimos anos")
        else:
            motivos.append(f"❌ Dividendos inconsistentes ({anos_c}/5 anos)")

        # Dívida
        if debt_equity is not None:
            if debt_equity < 0:
                score += 25; motivos.append(f"✅ Caixa líquido positivo (dívida líq./PL: {debt_equity:.2f})")
            elif debt_equity < 0.5:
                score += 20; motivos.append(f"✅ Dívida baixa: {debt_equity:.2f}x PL")
            elif debt_equity < 1.5:
                score += 10; motivos.append(f"ℹ️  Dívida moderada: {debt_equity:.2f}x PL")
            elif debt_equity < 3.0:
                score += 0;  motivos.append(f"⚠️  Dívida alta: {debt_equity:.2f}x PL")
            else:
                motivos.append(f"❌ Endividamento preocupante: {debt_equity:.2f}x PL")
        else:
            motivos.append("⚠️  Balanço não disponível para análise de dívida")

        score = min(score, 100)
        return {
            "score":       score,
            "apto":        score >= 55,
            "motivos":     motivos,
            "indicadores": indicadores,
            "nota":        "⚠️  Score parcial — sem ROE/margens (Startup+). "
                           "Combine com StatusInvestClient para análise completa.",
        }

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

    # ── Tesouro Direto ────────────────────────────────────────────────────────

    def get_treasury_bonds(self) -> list[dict]:
        """Lista títulos do Tesouro Direto disponíveis com taxa e vencimento."""
        try:
            data = self._get("v2/prime-rate", params={"country": "brazil"})
            return data.get("results", [])
        except Exception:
            return []

    # ── FIIs ──────────────────────────────────────────────────────────────────

    def get_fii_list(self) -> list[dict]:
        """Lista FIIs disponíveis na BRAPI com dados básicos."""
        try:
            data = self._get("quote/list", params={"type": "fund", "sortBy": "name"})
            return data.get("stocks", [])
        except Exception:
            return []