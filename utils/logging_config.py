"""Configuração centralizada de logging da aplicação."""

from __future__ import annotations

import logging
import sys
from typing import Final


LOG_FORMAT: Final = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
DATE_FORMAT: Final = "%Y-%m-%d %H:%M:%S"

# Bibliotecas que geram mensagens INFO de baixo valor para o usuário final.
_LOGGERS_EXTERNOS: Final = (
    "httpx",
    "httpcore",
    "urllib3",
    "requests",
    "yfinance",
)

_HANDLER_MARKER: Final = "_arvore_investimentos_handler"


def _normalizar_nivel(level: int | str) -> int:
    """Converte nomes como ``INFO`` em um nível aceito pelo logging."""
    if isinstance(level, int):
        return level

    if isinstance(level, str):
        nivel = logging.getLevelNamesMapping().get(level.strip().upper())
        if isinstance(nivel, int):
            return nivel

    raise ValueError(f"Nível de logging inválido: {level!r}")


def setup_logging(level: int | str = logging.INFO) -> None:
    """
    Configura o logger raiz de forma idempotente.

    Chamadas repetidas atualizam o nível sem adicionar handlers duplicados.
    Logs das bibliotecas HTTP ficam em WARNING, enquanto os logs da aplicação
    continuam respeitando o nível informado.
    """
    nivel = _normalizar_nivel(level)
    root = logging.getLogger()
    root.setLevel(nivel)

    handler_aplicacao = next(
        (
            handler
            for handler in root.handlers
            if getattr(handler, _HANDLER_MARKER, False)
        ),
        None,
    )

    if handler_aplicacao is None:
        handler_aplicacao = logging.StreamHandler(sys.stdout)
        setattr(handler_aplicacao, _HANDLER_MARKER, True)
        root.addHandler(handler_aplicacao)

    handler_aplicacao.setLevel(nivel)
    handler_aplicacao.setFormatter(
        logging.Formatter(
            LOG_FORMAT,
            datefmt=DATE_FORMAT,
        )
    )

    for nome in _LOGGERS_EXTERNOS:
        logging.getLogger(nome).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Retorna um logger nomeado para o módulo chamador."""
    return logging.getLogger(name)