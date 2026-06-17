"""
Financial Modeling Prep — https://financialmodelingprep.com
Plano gratuito: 250 req/dia, dados fundamentalistas, dividendos, DRE.

Cadastre-se em financialmodelingprep.com e defina FMP_API_KEY no .env.

Projetado para o futuro módulo recomendador_acoes.py:
    score_stock() já implementa a lógica de pontuação por perfil de risco.
"""

import os
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_URL = "https://financialmodelingprep.com/api/v3"

_http = requests.Session()
_retry = Retry(total=2, backoff_factor=0.3, status_forcelist=[429, 500, 502, 503, 504])
_http.mount("https://", HTTPAdapter(max_retries=_retry))


class FMPClient:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("FMP_API_KEY", "")
        if not self.api_key:
            raise ValueError(
                "FMP_API_KEY não definida. "
                "Cadastre-se em financialmodelingprep.com e adicione ao .env:\n"
                "    FMP_API_KEY=sua_chave_aqui"
            )

    def _get(self, endpoint: str, params: Optional[dict] = None, timeout=(4, 12)) -> dict | list:
        url = f"{BASE_URL}/{endpoint.lstrip('/')}"
        p = {"apikey": self.api_key}
        if params:
            p.update(params)
        r = _http.get(url, params=p,
                      headers={"User-Agent": "Mozilla/5.0"}, timeout=timeout)
        r.raise_for_status()
        return r.json()

    # ── Perfil da empresa ─────────────────────────────────────────────────────

    def get_profile(self, symbol: str) -> dict:
        """
        Perfil completo da empresa: setor, país, market cap, descrição, beta, etc.

        Retorna dict com:
            symbol, companyName, sector, industry, country,
            mktCap, beta, price, description, website

        Exemplo:
            client = FMPClient()
            perfil = client.get_profile("VALE3.SA")
            print(f"{perfil['companyName']} — Setor: {perfil['sector']}")
        """
        data = self._get(f"profile/{symbol.upper()}")
        if not data:
            raise ValueError(f"Empresa '{symbol}' não encontrada no FMP.")
        return data[0] if isinstance(data, list) else data

    # ── Demonstrações financeiras ─────────────────────────────────────────────

    def get_income_statement(self, symbol: str, years: int = 5) -> list[dict]:
        """
        Demonstração de Resultados (DRE) dos últimos N anos.

        Cada item contém:
            date, revenue, grossProfit, operatingIncome, netIncome,
            eps, ebitda, grossProfitRatio, netIncomeRatio

        Exemplo:
            dre = client.get_income_statement("ITUB4.SA", years=3)
            for ano in dre:
                print(f"{ano['date']}: Receita R${ano['revenue']:,.0f}")
        """
        data = self._get(f"income-statement/{symbol.upper()}", {"limit": years})
        return data if isinstance(data, list) else []

    def get_balance_sheet(self, symbol: str, years: int = 5) -> list[dict]:
        """
        Balanço Patrimonial dos últimos N anos.

        Campos chave:
            totalAssets, totalLiabilities, totalStockholdersEquity,
            totalDebt, cashAndCashEquivalents, netDebt
        """
        data = self._get(f"balance-sheet-statement/{symbol.upper()}", {"limit": years})
        return data if isinstance(data, list) else []

    def get_ratios(self, symbol: str, years: int = 5) -> list[dict]:
        """
        Indicadores calculados: P/L, P/VP, ROE, ROIC, Dividend Yield, etc.

        Exemplo:
            ratios = client.get_ratios("BBDC4.SA")
            print(f"P/L: {ratios[0]['priceEarningsRatio']:.1f}")
        """
        data = self._get(f"ratios/{symbol.upper()}", {"limit": years})
        return data if isinstance(data, list) else []

    # ── Dividendos ────────────────────────────────────────────────────────────

    def get_dividends(self, symbol: str) -> list[dict]:
        """
        Histórico completo de dividendos pagos.

        Cada item: {"date": "2024-03-15", "dividend": 0.85, "adjDividend": 0.85}

        Exemplo:
            divs = client.get_dividends("ITUB4.SA")
            total_12m = sum(d["dividend"] for d in divs[:4])  # últimos 4 tri
            print(f"Dividendos últimos 12m: R${total_12m:.2f}")
        """
        data = self._get(f"historical-price-full/stock_dividend/{symbol.upper()}")
        if isinstance(data, dict):
            return data.get("historical", [])
        return []

    def get_dividend_history_summary(self, symbol: str) -> dict:
        """
        Resumo do histórico de dividendos: total pago nos últimos 1, 3 e 5 anos.
        Útil para avaliar consistência de pagamentos antes de recomendar.
        """
        divs = self.get_dividends(symbol)
        if not divs:
            return {"ultimo_1a": 0, "ultimo_3a": 0, "ultimo_5a": 0, "consistente": False}

        from datetime import date, timedelta
        hoje   = date.today()
        d1a    = (hoje - timedelta(days=365)).isoformat()
        d3a    = (hoje - timedelta(days=365 * 3)).isoformat()
        d5a    = (hoje - timedelta(days=365 * 5)).isoformat()

        t1 = sum(d["dividend"] for d in divs if d["date"] >= d1a)
        t3 = sum(d["dividend"] for d in divs if d["date"] >= d3a)
        t5 = sum(d["dividend"] for d in divs if d["date"] >= d5a)

        # Considera consistente se pagou pelo menos 1x por ano nos últimos 5 anos
        anos_com_div = len({d["date"][:4] for d in divs if d["date"] >= d5a})
        consistente  = anos_com_div >= 4

        return {
            "ultimo_1a":   round(t1, 4),
            "ultimo_3a":   round(t3, 4),
            "ultimo_5a":   round(t5, 4),
            "consistente": consistente,
        }

    # ── Score de ação por perfil ──────────────────────────────────────────────

    def score_stock(self, symbol: str, perfil_risco: int) -> dict:
        """
        Pontuação de uma ação baseada no perfil de risco do investidor.
        Projetado para o futuro módulo recomendador_acoes.py.

        perfil_risco: 1 = conservador | 2 = moderado | 3 = agressivo

        Retorna:
            score       — 0 a 100 (quanto maior, mais adequado ao perfil)
            apto        — bool (True se score >= 60)
            motivos     — list[str] com justificativas
            indicadores — dict com os principais números usados

        Pesos por perfil:
            Conservador (1): prioriza DY alto, dívida baixa, lucro estável
            Moderado    (2): equilibra crescimento e dividendos
            Agressivo   (3): prioriza crescimento de receita e margens

        Exemplo:
            fmp = FMPClient()
            resultado = fmp.score_stock("ITUB4.SA", perfil_risco=1)
            if resultado["apto"]:
                print(f"Score {resultado['score']}/100 — {resultado['motivos']}")
        """
        try:
            ratios_list = self.get_ratios(symbol, years=1)
            ratios      = ratios_list[0] if ratios_list else {}

            income_list = self.get_income_statement(symbol, years=3)
            income      = income_list[0] if income_list else {}

            div_summary = self.get_dividend_history_summary(symbol)
        except Exception as e:
            return {
                "score": 0, "apto": False,
                "motivos": [f"Erro ao buscar dados: {e}"],
                "indicadores": {},
            }

        # ── Extrai indicadores ────────────────────────────────────────────────
        pl            = float(ratios.get("priceEarningsRatio",   0) or 0)
        roe           = float(ratios.get("returnOnEquity",       0) or 0) * 100
        margem_liq    = float(ratios.get("netProfitMargin",      0) or 0) * 100
        div_yield     = float(ratios.get("dividendYield",        0) or 0) * 100
        div_payout    = float(ratios.get("payoutRatio",          0) or 0) * 100
        debt_equity   = float(ratios.get("debtEquityRatio",      0) or 0)
        receita_atual = float(income.get("revenue",              0) or 0)

        # Crescimento de receita (último ano vs anterior)
        receita_cresc = 0.0
        if len(income_list) >= 2:
            r0 = float(income_list[0].get("revenue", 0) or 0)
            r1 = float(income_list[1].get("revenue", 0) or 0)
            if r1 > 0:
                receita_cresc = ((r0 / r1) - 1) * 100

        indicadores = {
            "p_l":              round(pl, 1),
            "roe_pct":          round(roe, 1),
            "margem_liquida":   round(margem_liq, 1),
            "dividend_yield":   round(div_yield, 1),
            "payout_pct":       round(div_payout, 1),
            "divida_patrimonio": round(debt_equity, 2),
            "crescimento_receita_pct": round(receita_cresc, 1),
            "dividendos_consistentes": div_summary["consistente"],
        }

        # ── Pontuação por perfil ──────────────────────────────────────────────
        score   = 0
        motivos = []

        if perfil_risco == 1:  # Conservador — prioriza estabilidade e renda
            if div_yield >= 5:
                score += 25; motivos.append(f"✅ DY alto: {div_yield:.1f}%")
            elif div_yield >= 3:
                score += 12; motivos.append(f"ℹ️  DY moderado: {div_yield:.1f}%")
            else:
                motivos.append(f"❌ DY baixo: {div_yield:.1f}% (mínimo 3%)")

            if div_summary["consistente"]:
                score += 20; motivos.append("✅ Histórico consistente de dividendos")
            else:
                motivos.append("❌ Dividendos inconsistentes")

            if debt_equity < 1.0:
                score += 20; motivos.append(f"✅ Dívida/Patrimônio baixa: {debt_equity:.2f}")
            elif debt_equity < 2.0:
                score += 10; motivos.append(f"⚠️  Dívida/Patrimônio moderada: {debt_equity:.2f}")
            else:
                motivos.append(f"❌ Dívida alta: {debt_equity:.2f}")

            if 0 < pl <= 15:
                score += 20; motivos.append(f"✅ P/L atrativo: {pl:.1f}")
            elif 15 < pl <= 25:
                score += 10; motivos.append(f"ℹ️  P/L razoável: {pl:.1f}")
            else:
                motivos.append(f"❌ P/L elevado ou negativo: {pl:.1f}")

            if margem_liq >= 10:
                score += 15; motivos.append(f"✅ Margem líquida sólida: {margem_liq:.1f}%")
            elif margem_liq >= 5:
                score += 8

        elif perfil_risco == 2:  # Moderado — equilíbrio crescimento/dividendos
            if roe >= 15:
                score += 25; motivos.append(f"✅ ROE alto: {roe:.1f}%")
            elif roe >= 10:
                score += 12; motivos.append(f"ℹ️  ROE moderado: {roe:.1f}%")
            else:
                motivos.append(f"❌ ROE baixo: {roe:.1f}%")

            if receita_cresc >= 10:
                score += 20; motivos.append(f"✅ Crescimento receita: +{receita_cresc:.1f}%")
            elif receita_cresc >= 5:
                score += 12; motivos.append(f"ℹ️  Crescimento moderado: +{receita_cresc:.1f}%")
            else:
                motivos.append(f"ℹ️  Receita estável/queda: {receita_cresc:.1f}%")

            if div_yield >= 3:
                score += 15; motivos.append(f"✅ DY: {div_yield:.1f}%")

            if 0 < pl <= 20:
                score += 20; motivos.append(f"✅ P/L: {pl:.1f}")
            elif pl <= 30:
                score += 10

            if margem_liq >= 10:
                score += 20; motivos.append(f"✅ Margem líquida: {margem_liq:.1f}%")
            elif margem_liq >= 5:
                score += 10

        else:  # Agressivo — prioriza crescimento
            if receita_cresc >= 20:
                score += 30; motivos.append(f"✅ Crescimento acelerado: +{receita_cresc:.1f}%")
            elif receita_cresc >= 10:
                score += 18; motivos.append(f"ℹ️  Bom crescimento: +{receita_cresc:.1f}%")
            else:
                motivos.append(f"❌ Crescimento fraco: {receita_cresc:.1f}%")

            if roe >= 20:
                score += 25; motivos.append(f"✅ ROE excelente: {roe:.1f}%")
            elif roe >= 12:
                score += 15; motivos.append(f"ℹ️  ROE bom: {roe:.1f}%")

            if margem_liq >= 15:
                score += 25; motivos.append(f"✅ Margem líquida alta: {margem_liq:.1f}%")
            elif margem_liq >= 8:
                score += 12

            if debt_equity < 1.5:
                score += 20; motivos.append(f"✅ Dívida controlada: {debt_equity:.2f}")
            elif debt_equity >= 3:
                motivos.append(f"❌ Endividamento preocupante: {debt_equity:.2f}")

        score = min(score, 100)

        return {
            "score":        score,
            "apto":         score >= 60,
            "motivos":      motivos,
            "indicadores":  indicadores,
        }