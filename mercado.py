import time
import json
import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import FB_SELIC, FB_IPCA, FB_IBOV

# ── Sessão HTTP com retry automático ─────────────────────────────────────────
_HTTP   = requests.Session()
_retry  = Retry(total=2, backoff_factor=0.2, status_forcelist=[429, 500, 502, 503, 504])
_HTTP.mount("https://", HTTPAdapter(max_retries=_retry))
_HTTP.mount("http://",  HTTPAdapter(max_retries=_retry))

# ── yfinance (opcional) ───────────────────────────────────────────────────────
try:
    import yfinance as yf
    _YFINANCE = True
except ImportError:
    _YFINANCE = False

# ── Cache em disco ────────────────────────────────────────────────────────────
CACHE_FILE        = Path.home() / ".cache" / "recomendador_investimentos_market.json"
CACHE_TTL_SECONDS = 6 * 60 * 60


def _json_get(url: str, timeout=(3, 8)):
    r = _HTTP.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    return r.json()


def _load_market_cache():
    try:
        if not CACHE_FILE.exists():
            return None
        if time.time() - CACHE_FILE.stat().st_mtime > CACHE_TTL_SECONDS:
            return None
        with CACHE_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        required = ("selic", "focus_selic", "ipca", "ibov_cagr", "data_ref", "fontes", "avisos")
        if not all(k in data for k in required):
            return None
        return data
    except Exception:
        return None


def _save_market_cache(payload: dict):
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with CACHE_FILE.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
    except Exception:
        pass


def _fetch_sgs_value(serie: int) -> Tuple[float, str]:
    url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{serie}/dados/ultimos/5?formato=json"
    data = _json_get(url)
    if not data:
        raise RuntimeError(f"SGS série {serie}: resposta vazia")
    for item in data:
        raw = str(item.get("valor", "")).strip()
        if raw:
            try:
                return float(raw.replace(",", ".")) / 100.0, str(item.get("data", ""))
            except (ValueError, KeyError):
                continue
    raise RuntimeError(f"SGS série {serie}: nenhum valor válido nos últimos registros")


def _fetch_focus_selic() -> Optional[float]:
    """
    [FIX-2] Se o ano atual não tiver estimativa Focus (ex: início de ano),
    tenta o ano anterior como fallback.
    """
    for ano in (datetime.date.today().year, datetime.date.today().year - 1):
        try:
            url = (
                "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/"
                f"ExpectativaMercadoAnuais?$filter=Indicador eq 'Selic' and DataReferencia eq '{ano}'"
                "&$orderby=Data desc&$top=1&$format=json&$select=Mediana"
            )
            data = _json_get(url)
            values = data.get("value", [])
            if values:
                return float(values[0]["Mediana"]) / 100
        except Exception:
            continue
    return None


def _fetch_ibov_cagr_10a() -> Optional[float]:
    """Retorna CAGR real, incluindo negativos. Piso seguro está em SPREAD_ALT_MIN."""
    if not _YFINANCE:
        return None
    try:
        hist = yf.Ticker("^BVSP").history(period="10y", auto_adjust=False)
        if hist is None or len(hist) < 200:
            return None
        c0 = float(hist["Close"].iloc[0])
        c1 = float(hist["Close"].iloc[-1])
        anos = len(hist) / 252.0
        if c0 <= 0:
            return None
        return (c1 / c0) ** (1.0 / anos) - 1
    except Exception:
        return None


def load_market_data() -> dict:
    cached = _load_market_cache()
    if cached:
        return cached

    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = {
            ex.submit(_fetch_sgs_value, 432):   "selic",
            ex.submit(_fetch_sgs_value, 13522): "ipca",
            ex.submit(_fetch_focus_selic):      "focus_selic",
            ex.submit(_fetch_ibov_cagr_10a):    "ibov_cagr",
        }
        results = {}
        for fut in as_completed(futures):
            key = futures[fut]
            try:
                results[key] = fut.result()
            except Exception:
                results[key] = None

    selic_raw = results.get("selic")
    ipca_raw  = results.get("ipca")
    focus_val = results.get("focus_selic")
    ibov_raw  = results.get("ibov_cagr")

    selic_val, data_ref = selic_raw if selic_raw is not None else (FB_SELIC, datetime.date.today().strftime("%d/%m/%Y"))
    ipca_val,  _        = ipca_raw  if ipca_raw  is not None else (FB_IPCA,  data_ref)
    ibov_val            = ibov_raw  if ibov_raw  is not None else FB_IBOV

    fontes = [
        f"SELIC {selic_val*100:.2f}% a.a. — BCB/SGS série 432 (ref. {data_ref})",
        f"IPCA 12m {ipca_val*100:.2f}% a.a. — BCB/SGS série 13522",
    ]
    avisos = []

    if focus_val is not None:
        fontes.append(f"Previsão SELIC Focus {focus_val*100:.2f}% a.a. — BCB/Olinda")
    else:
        avisos.append("⚠️  Focus indisponível; usando SELIC atual sem média de expectativa.")

    if ibov_raw is not None:
        fontes.append(f"Ibovespa CAGR 10a {ibov_val*100:.1f}% a.a. — Yahoo Finance/yfinance")
    else:
        avisos.append(f"⚠️  Ibovespa CAGR: fallback histórico {FB_IBOV*100:.1f}% a.a.")

    payload = {
        "selic":       selic_val,
        "focus_selic": focus_val,
        "ipca":        ipca_val,
        "ibov_cagr":   ibov_val,
        "data_ref":    data_ref,
        "fontes":      fontes,
        "avisos":      avisos,
    }
    _save_market_cache(payload)
    return payload