"""Orquestra os rankings reais de ativos usados em cada classe da carteira."""

from __future__ import annotations

import importlib
import math
from collections.abc import Mapping, Set
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from config import MAX_WORKERS_ATIVOS
from core.categorias import RK
from utils.exceptions import DadosIndisponiveisError
from utils.logging_config import get_logger

logger = get_logger(__name__)


_CLASSE: dict[str, str] = {
    RK.RV: "acoes",
    RK.RV_DCA: "acoes",
    RK.RV_COMPL: "acoes",
    RK.FUNDOS_ACOES: "acoes",
    RK.FUNDOS_ACOES_ETF: "etf",
    RK.FUNDOS_ACOES_DCA: "acoes",
    RK.FIIS: "fiis",
    RK.FIIS_DEL: "fiis",
    RK.RV_CRIPTO: "cripto",
    RK.FUNDOS_CRIPTO: "cripto",
    RK.RF: "rf",
    RK.RF_LIQUIDEZ: "rf",
    RK.RF_SELIC_CDB: "rf",
    RK.RF_IPCA: "rf",
    RK.RF_RESERVA: "rf",
    RK.RF_REAVALIE: "rf",
    RK.RF_EQUILIBRIO: "rf",
    RK.FUNDOS_RF: "rf",
    RK.FUNDOS_RF_LIQ: "rf",
    RK.FUNDOS: "fundos",
    RK.FUNDOS_DIVERSIF: "fundos",
    RK.FUNDOS_MULTI: "fundos",
    RK.ESTRUTURADOS: "estruturados",
}

_LABEL: dict[str, str] = {
    "acoes": "AÇÕES",
    "etf": "ETFs (Ranking Dinâmico)",
    "fiis": "FIIs",
    "cripto": "CRIPTO",
    "rf": "RENDA FIXA",
    "fundos": "FUNDOS",
    "estruturados": "PRODUTOS ESTRUTURADOS (CRA/CRI/Debêntures)",
}

MIN_PCT = 5
_ORDEM = (
    "rf",
    "fundos",
    "estruturados",
    "fiis",
    "acoes",
    "etf",
    "cripto",
)


def _validar_perfil(perfil_risco: object) -> int:
    if isinstance(perfil_risco, bool):
        raise TypeError("perfil_risco deve ser inteiro.")
    try:
        perfil = int(perfil_risco)
    except (TypeError, ValueError) as exc:
        raise TypeError("perfil_risco deve ser inteiro.") from exc
    if perfil != perfil_risco or perfil not in {1, 2, 3}:
        raise ValueError("perfil_risco deve ser 1, 2 ou 3.")
    return perfil


def _validar_limite(n: object) -> int:
    if isinstance(n, bool):
        raise TypeError("n deve ser inteiro.")
    try:
        limite = int(n)
    except (TypeError, ValueError) as exc:
        raise TypeError("n deve ser inteiro.") from exc
    if limite != n or not 1 <= limite <= 50:
        raise ValueError("n deve estar entre 1 e 50.")
    return limite


def _percentual(chave: str, valor: object) -> float:
    if isinstance(valor, bool):
        raise TypeError(f"O percentual de {chave!r} não pode ser booleano.")
    try:
        numero = float(valor)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"O percentual de {chave!r} deve ser numérico.") from exc
    if not math.isfinite(numero) or numero < 0:
        raise ValueError(f"O percentual de {chave!r} deve ser finito e positivo.")
    return numero


def _modulo(nome: str):
    """Importa uma integração somente quando sua classe for solicitada."""
    return importlib.import_module(nome)


def _executar_classe(
    classe: str,
    perfil_risco: int,
    n: int,
) -> list[dict[str, Any]]:
    if classe == "acoes":
        funcao = _modulo("acoes_fiis.screener").top_acoes
        ativos = funcao(perfil_risco, n=n)
    elif classe == "etf":
        funcao = _modulo("etfs.screener_etf").top_etfs
        ativos = funcao(perfil_risco, n=min(n, 5))
    elif classe == "fiis":
        funcao = _modulo("acoes_fiis.screener").top_fiis
        ativos = funcao(perfil_risco, n=n)
    elif classe == "cripto":
        funcao = _modulo("cripto.screener_cripto").top_cripto
        ativos = funcao(perfil_risco, n=min(n, 4))
    elif classe == "rf":
        funcao = _modulo("renda_fixa.ranker").rankear_rf
        ativos = funcao(perfil=perfil_risco, limite=n)
    elif classe == "fundos":
        funcao = _modulo("fundos.ranker_fundos").rankear_fundos
        ativos = funcao(perfil=perfil_risco, limite=n)
    elif classe == "estruturados":
        funcao = _modulo(
            "produtos_estruturados.ranker"
        ).rankear_estruturados
        ativos = funcao(perfil=perfil_risco, limite=n)
    else:
        raise ValueError(f"Classe de ativos desconhecida: {classe!r}.")

    if ativos is None:
        raise RuntimeError("A fonte respondeu sem uma lista de ativos.")
    if not isinstance(ativos, list):
        try:
            ativos = list(ativos)
        except TypeError as exc:
            raise TypeError(
                "O ranker deve retornar uma coleção de ativos."
            ) from exc
    return ativos


def _buscar_classes(
    classes: Set[str],
    perfil_risco: int,
    n: int,
) -> tuple[dict[str, list], dict[str, str]]:
    """Consulta as classes em paralelo e mantém falhas fora das listas."""
    desconhecidas = set(classes) - set(_ORDEM)
    if desconhecidas:
        raise ValueError(
            "Classes desconhecidas: " + ", ".join(sorted(desconhecidas))
        )
    if not classes:
        return {}, {}

    temporario: dict[str, list] = {}
    falhas: dict[str, str] = {}
    trabalhadores = min(MAX_WORKERS_ATIVOS, len(classes))

    with ThreadPoolExecutor(max_workers=trabalhadores) as executor:
        futuros = {
            executor.submit(
                _executar_classe,
                classe,
                perfil_risco,
                n,
            ): classe
            for classe in classes
        }
        for futuro in as_completed(futuros):
            classe = futuros[futuro]
            try:
                temporario[classe] = futuro.result()
            except DadosIndisponiveisError as exc:
                logger.warning("Classe %s indisponível: %s", classe, exc)
                falhas[classe] = str(exc)
            except ModuleNotFoundError as exc:
                logger.error("Integração ausente para %s: %s", classe, exc)
                falhas[classe] = (
                    "Integração necessária não instalada: "
                    f"{exc.name or exc}"
                )
            except Exception as exc:
                logger.exception("Erro ao buscar classe %s", classe)
                falhas[classe] = (
                    "Falha inesperada ao buscar dados: "
                    f"{type(exc).__name__}: {exc}"
                )

    resultado = {
        classe: temporario[classe]
        for classe in _ORDEM
        if classe in temporario
    }
    indisponiveis = {
        classe: falhas[classe]
        for classe in _ORDEM
        if classe in falhas
    }
    return resultado, indisponiveis


def recomendar_por_portfolio(
    portfolio: dict,
    perfil_risco: int,
    n: int = 5,
    selic: float | None = None,
    ipca: float | None = None,
    ibov_cagr: float | None = None,
) -> dict[str, list]:
    """
    Retorna rankings para classes com pelo menos ``MIN_PCT`` de alocação.

    Os três indicadores são mantidos na assinatura por compatibilidade. Cada
    ranker continua responsável por buscar e validar seus dados de mercado.
    """
    del selic, ipca, ibov_cagr
    if not isinstance(portfolio, Mapping):
        raise TypeError("portfolio deve ser um mapeamento de percentuais.")
    perfil = _validar_perfil(perfil_risco)
    limite = _validar_limite(n)

    percentuais = {
        chave: _percentual(chave, percentual)
        for chave, percentual in portfolio.items()
    }
    classes = {
        _CLASSE[chave]
        for chave, percentual in percentuais.items()
        if (
            chave in _CLASSE
            and percentual >= MIN_PCT
        )
    }
    if not classes:
        return {}

    resultado, indisponiveis = _buscar_classes(classes, perfil, limite)
    resultado["_indisponiveis"] = indisponiveis
    return resultado


def recomendar_ativos(
    rec_key: str,
    perfil_risco: int,
    n: int = 5,
    selic: float | None = None,
    ipca: float | None = None,
    ibov_cagr: float | None = None,
) -> list[dict] | None:
    """Compatibilidade: busca apenas a classe da recomendação informada."""
    del selic, ipca, ibov_cagr
    perfil = _validar_perfil(perfil_risco)
    limite = _validar_limite(n)
    classe = _CLASSE.get(rec_key)
    if classe is None:
        return None
    return _executar_classe(classe, perfil, limite)