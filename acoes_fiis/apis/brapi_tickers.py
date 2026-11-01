"""Lista pública e gratuita de ativos da B3 na BRAPI (/api/v2/tickers).

Não exige token. Traz símbolo, nome e tipo (ação, FII, ETF, BDR, unit) de
todos os ativos listados; é usada para montar o universo de ETFs e para dar
nome aos FIIs, que o Fundamentus não informa.
"""

from __future__ import annotations

import threading
import time

import requests

from utils.logging_config import get_logger

logger = get_logger(__name__)

_URL = "https://brapi.dev/api/v2/tickers"
_TTL_S = 60 * 60
_cache: dict = {"ts": 0.0, "dados": None}
_trava = threading.Lock()


def _baixar_lista() -> dict[str, dict]:
    ativos: dict[str, dict] = {}
    pagina = 1
    while True:
        try:
            resposta = requests.get(
                _URL,
                params={"limit": 200, "page": pagina},
                timeout=10,
                headers={"User-Agent": "arvore-de-investimentos/1.0"},
            )
            resposta.raise_for_status()
            dados = resposta.json()
        except (requests.RequestException, TypeError, ValueError) as exc:
            logger.warning("BRAPI /api/v2/tickers falhou na página %s: %s", pagina, exc)
            break

        for item in dados.get("results", []):
            simbolo = str(item.get("symbol", "")).strip().upper().replace(".SA", "")
            if simbolo:
                ativos.setdefault(simbolo, item)

        if not dados.get("pagination", {}).get("hasNextPage", False):
            break
        pagina += 1
        time.sleep(0.3)
    return ativos


def listar_tickers() -> dict[str, dict]:
    """``{símbolo: item}`` de todos os ativos, com cache de uma hora."""
    with _trava:
        if _cache["dados"] and time.time() - _cache["ts"] < _TTL_S:
            return dict(_cache["dados"])
        dados = _baixar_lista()
        if dados:
            _cache.update(ts=time.time(), dados=dados)
        return dict(dados)


def nome_do_ativo(simbolo: str, ativos: dict[str, dict] | None = None) -> str:
    """Nome do ativo na BRAPI, ou texto vazio se não encontrado."""
    item = (ativos if ativos is not None else listar_tickers()).get(
        str(simbolo).strip().upper()
    )
    if not item:
        return ""
    return str(item.get("name") or item.get("longName") or "").strip()
