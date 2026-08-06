"""Audita rastreabilidade e integridade do registro de fontes oficiais."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import urlsplit

import requests

from validacao.tributacao import (
    validar_cripto_independente,
    validar_estruturados_independente,
    validar_fundos_independente,
    validar_previdencia_independente,
    validar_renda_fixa_independente,
    validar_renda_variavel_independente,
)

ARQUIVO_FONTES = Path(__file__).with_name("fontes_oficiais.json")
MODULOS = (
    validar_renda_fixa_independente,
    validar_fundos_independente,
    validar_previdencia_independente,
    validar_renda_variavel_independente,
    validar_estruturados_independente,
    validar_cripto_independente,
)
DOMINIOS_OFICIAIS = (
    "gov.br",
    "planalto.gov.br",
    "fazenda.gov.br",
    "b3.com.br",
)


def _dominio_oficial(url: str) -> bool:
    host = (urlsplit(url).hostname or "").casefold()
    return any(
        host == dominio or host.endswith(f".{dominio}") for dominio in DOMINIOS_OFICIAIS
    )


def carregar_registro(caminho: Path = ARQUIVO_FONTES) -> dict:
    return json.loads(caminho.read_text(encoding="utf-8"))


def fontes_utilizadas() -> dict[str, str]:
    usadas: dict[str, str] = {}
    for modulo in MODULOS:
        for identificador, url in modulo.FONTES.items():
            anterior = usadas.setdefault(identificador, url)
            if anterior != url:
                raise ValueError(f"Fonte {identificador!r} usa URLs conflitantes.")
    return usadas


def auditar_registro(
    registro: Mapping,
    *,
    hoje: date | None = None,
) -> dict:
    referencia = hoje or datetime.now(UTC).date()
    problemas: list[str] = []
    fontes = registro.get("fontes")
    if not isinstance(fontes, list) or not fontes:
        return {
            "valido": False,
            "problemas": ["Lista de fontes ausente."],
            "resumo": {"registradas": 0, "utilizadas": 0},
        }

    por_id: dict[str, Mapping] = {}
    for indice, fonte in enumerate(fontes):
        if not isinstance(fonte, Mapping):
            problemas.append(f"Fonte #{indice} não é um objeto.")
            continue
        faltantes = {
            "id",
            "autoridade",
            "url",
            "vigencia_inicio",
            "consultada_em",
            "escopo_regras",
            "revisao_humana",
        } - set(fonte)
        if faltantes:
            problemas.append(f"Fonte #{indice} sem campos: {sorted(faltantes)}.")
            continue
        identificador = str(fonte["id"])
        if identificador in por_id:
            problemas.append(f"ID de fonte duplicado: {identificador}.")
        por_id[identificador] = fonte
        url = str(fonte["url"])
        if urlsplit(url).scheme != "https" or not _dominio_oficial(url):
            problemas.append(f"Fonte não oficial ou sem HTTPS: {identificador}.")
        try:
            consultada = date.fromisoformat(str(fonte["consultada_em"]))
            date.fromisoformat(str(fonte["vigencia_inicio"]))
        except ValueError:
            problemas.append(f"Data inválida na fonte {identificador}.")
        else:
            if consultada > referencia:
                problemas.append(
                    f"Consulta futura na fonte {identificador}: {consultada}."
                )
        if fonte["revisao_humana"] not in {
            "pendente_revisao_profissional",
            "revisada_por_profissional",
        }:
            problemas.append(f"Estado de revisão inválido na fonte {identificador}.")

    utilizadas = fontes_utilizadas()
    for identificador, url in utilizadas.items():
        registrada = por_id.get(identificador)
        if registrada is None:
            problemas.append(f"Fonte utilizada sem registro: {identificador}.")
        elif registrada["url"] != url:
            problemas.append(f"URL divergente da fonte {identificador}.")

    return {
        "_schema_version": 1,
        "valido": not problemas,
        "problemas": problemas,
        "resumo": {
            "registradas": len(por_id),
            "utilizadas": len(utilizadas),
            "pendentes_revisao_profissional": sum(
                fonte.get("revisao_humana") == "pendente_revisao_profissional"
                for fonte in por_id.values()
            ),
        },
    }


def auditar_disponibilidade_online(
    registro: Mapping,
    *,
    timeout: float = 15.0,
    session=None,
) -> dict:
    """Consulta fontes e registra hash; não interpreta o conteúdo jurídico."""
    cliente = session or requests.Session()
    resultados = []
    for fonte in registro.get("fontes", []):
        identificador = str(fonte.get("id", "<sem-id>"))
        try:
            resposta = cliente.get(
                fonte["url"],
                timeout=timeout,
                allow_redirects=True,
                headers={"User-Agent": "arvore-investimentos-auditoria/1.0"},
            )
            resposta.raise_for_status()
        except requests.RequestException as exc:
            resultados.append(
                {
                    "id": identificador,
                    "ok": False,
                    "erro": str(exc),
                }
            )
            continue
        resultados.append(
            {
                "id": identificador,
                "ok": True,
                "status_http": resposta.status_code,
                "url_final": resposta.url,
                "etag": resposta.headers.get("ETag"),
                "last_modified": resposta.headers.get("Last-Modified"),
                "sha256_conteudo": hashlib.sha256(resposta.content).hexdigest(),
            }
        )
    return {
        "consultada_em": datetime.now(UTC).isoformat(),
        "total": len(resultados),
        "disponiveis": sum(item["ok"] for item in resultados),
        "indisponiveis": sum(not item["ok"] for item in resultados),
        "resultados": resultados,
        "aviso": (
            "Disponibilidade e hash não comprovam vigência, interpretação "
            "ou aplicabilidade jurídica."
        ),
    }


def _argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fontes", type=Path, default=ARQUIVO_FONTES)
    parser.add_argument("--saida", type=Path)
    parser.add_argument("--online", action="store_true")
    parser.add_argument("--timeout", type=float, default=15.0)
    return parser.parse_args()


def main() -> int:
    args = _argumentos()
    registro = carregar_registro(args.fontes)
    relatorio = auditar_registro(registro)
    if args.online:
        relatorio["disponibilidade_online"] = auditar_disponibilidade_online(
            registro,
            timeout=args.timeout,
        )
    texto = json.dumps(relatorio, ensure_ascii=False, indent=2) + "\n"
    if args.saida:
        args.saida.parent.mkdir(parents=True, exist_ok=True)
        args.saida.write_text(texto, encoding="utf-8")
    sys.stdout.write(texto)
    falha_online = bool(
        args.online and relatorio["disponibilidade_online"]["indisponiveis"]
    )
    return int(not relatorio["valido"] or falha_online)


if __name__ == "__main__":
    raise SystemExit(main())
