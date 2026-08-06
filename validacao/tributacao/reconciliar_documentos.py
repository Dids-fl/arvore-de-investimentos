"""Reconcilia saídas do motor com documentos reais previamente anonimizados."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any

from tributacao import ContextoTributario, calcular_tributacao

CHAVES_PESSOAIS_PROIBIDAS = {
    "cpf",
    "cnpj",
    "nome",
    "email",
    "endereco",
    "telefone",
    "conta",
    "agencia",
}


def _sha256(caminho: Path) -> str:
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


def _chaves_proibidas(valor: Any, prefixo: str = "") -> list[str]:
    encontradas: list[str] = []
    if isinstance(valor, Mapping):
        for chave, item in valor.items():
            caminho = f"{prefixo}.{chave}" if prefixo else str(chave)
            if str(chave).casefold() in CHAVES_PESSOAIS_PROIBIDAS:
                encontradas.append(caminho)
            encontradas.extend(_chaves_proibidas(item, caminho))
    elif isinstance(valor, list):
        for indice, item in enumerate(valor):
            encontradas.extend(_chaves_proibidas(item, f"{prefixo}[{indice}]"))
    return encontradas


def _contexto(dados: Mapping[str, Any]) -> ContextoTributario:
    entrada = dict(dados)
    entrada["data_aplicacao"] = date.fromisoformat(str(entrada["data_aplicacao"]))
    entrada["data_resgate"] = date.fromisoformat(str(entrada["data_resgate"]))
    return ContextoTributario(**entrada)


def reconciliar_caso(
    caso: Mapping[str, Any],
    *,
    tolerancia: float,
) -> dict[str, Any]:
    proibidas = _chaves_proibidas(caso)
    if proibidas:
        raise ValueError(
            "Remova dados pessoais antes da reconciliação: " + ", ".join(proibidas)
        )
    documento = caso.get("documento")
    observado = caso.get("observado")
    if not isinstance(documento, Mapping) or not isinstance(observado, Mapping):
        raise TypeError("Cada caso exige documento e observado.")
    campos_documento = {
        "tipo_documento",
        "emissor",
        "data_documento",
        "identificador_anonimizado",
    }
    if faltantes := campos_documento - set(documento):
        raise ValueError(f"Documento sem campos: {sorted(faltantes)}.")

    motor = calcular_tributacao(_contexto(caso["entrada"]))
    imposto_observado = observado.get("imposto")
    liquido_observado = observado.get("valor_liquido")
    if imposto_observado is None or liquido_observado is None:
        status = "DADOS_INSUFICIENTES"
        diferenca_imposto = None
        diferenca_liquido = None
    elif motor.imposto_estimado is None or motor.valor_liquido is None:
        status = "MOTOR_INDETERMINADO"
        diferenca_imposto = None
        diferenca_liquido = None
    else:
        diferenca_imposto = motor.imposto_estimado - float(imposto_observado)
        diferenca_liquido = motor.valor_liquido - float(liquido_observado)
        status = (
            "CONCILIADO"
            if abs(diferenca_imposto) <= tolerancia
            and abs(diferenca_liquido) <= tolerancia
            else "DIVERGENTE"
        )

    return {
        "caso_id": caso["id"],
        "status": status,
        "documento": dict(documento),
        "motor": {
            "imposto_estimado": motor.imposto_estimado,
            "valor_liquido": motor.valor_liquido,
            "aliquota_efetiva": motor.aliquota_efetiva,
            "precisao": motor.precisao.value,
            "regra_id": motor.regra_id,
            "fonte": motor.fonte,
            "vigencia": motor.vigencia.isoformat(),
        },
        "observado": dict(observado),
        "diferenca_imposto": diferenca_imposto,
        "diferenca_valor_liquido": diferenca_liquido,
    }


def reconciliar_documento(caminho: Path) -> dict[str, Any]:
    documento = json.loads(caminho.read_text(encoding="utf-8"))
    tolerancia = float(documento.get("tolerancia_monetaria", 0.01))
    resultados = [
        reconciliar_caso(caso, tolerancia=tolerancia) for caso in documento["casos"]
    ]
    contagens = {
        status: sum(item["status"] == status for item in resultados)
        for status in (
            "CONCILIADO",
            "DIVERGENTE",
            "DADOS_INSUFICIENTES",
            "MOTOR_INDETERMINADO",
        )
    }
    return {
        "_schema_version": 1,
        "arquivo_entrada_sha256": _sha256(caminho),
        "tolerancia_monetaria": tolerancia,
        "resumo": {"total": len(resultados), **contagens},
        "resultados": resultados,
        "aviso": (
            "Reconciliação técnica com dados anonimizados; não verifica a "
            "autenticidade do documento nem substitui revisão profissional."
        ),
    }


def _argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("entrada", type=Path)
    parser.add_argument("--saida", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = _argumentos()
    relatorio = reconciliar_documento(args.entrada)
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    args.saida.write_text(
        json.dumps(relatorio, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    sys.stdout.write(json.dumps(relatorio["resumo"], ensure_ascii=False) + "\n")
    return int(relatorio["resumo"]["DIVERGENTE"] > 0)


if __name__ == "__main__":
    raise SystemExit(main())
