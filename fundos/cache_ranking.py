"""Cache em disco dos rankings de fundos e previdência.

Calcular o ranking leva cerca de um minuto (milhares de fundos, Sharpe e
Sortino de cada um). Os dados de entrada só mudam quando a CVM publica um novo
dia de informe, então o ranking é guardado com a data do último informe do
banco local e reaproveitado até ela mudar (ou por no máximo um dia).
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CACHE_DIR = Path.home() / ".cache" / "arvore_investimentos" / "rankings"
TTL_SEGUNDOS = 24 * 60 * 60


def _ultima_data_informe() -> str | None:
    try:
        from .informe_diario_coletor import get_informe_coletor

        linha = get_informe_coletor().conn.execute(
            "SELECT MAX(Data_Competencia) FROM informe_diario"
        ).fetchone()
        return linha[0] if linha else None
    except Exception as exc:  # noqa: BLE001 — sem cache, apenas recalcula
        logger.debug("Não foi possível ler a data do último informe: %s", exc)
        return None


def _chave(nome: str, parametros: dict[str, Any], data_informe: str) -> str:
    texto = json.dumps(
        {"nome": nome, "parametros": parametros, "informe": data_informe},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:32]


def com_cache(
    nome: str,
    parametros: dict[str, Any],
    calcular: Callable[[], list[dict]],
) -> list[dict]:
    """Devolve o ranking em cache para os mesmos parâmetros e dados, ou calcula."""
    data_informe = _ultima_data_informe()
    if data_informe is None:
        return calcular()
    arquivo = CACHE_DIR / f"{nome}_{_chave(nome, parametros, data_informe)}.json"
    try:
        if arquivo.is_file() and time.time() - arquivo.stat().st_mtime < TTL_SEGUNDOS:
            return json.loads(arquivo.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.debug("Cache de ranking ilegível (%s): %s", arquivo.name, exc)

    ranking = calcular()
    if ranking:
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            temporario = arquivo.with_suffix(".tmp")
            temporario.write_text(
                json.dumps(ranking, ensure_ascii=False, default=str), encoding="utf-8"
            )
            temporario.replace(arquivo)
            for antigo in CACHE_DIR.glob(f"{nome}_*.json"):
                if time.time() - antigo.stat().st_mtime > TTL_SEGUNDOS:
                    antigo.unlink(missing_ok=True)
        except OSError as exc:
            logger.debug("Não foi possível gravar o cache de ranking: %s", exc)
    return ranking
