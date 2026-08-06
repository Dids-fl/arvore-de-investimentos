"""Infraestrutura compartilhada sem fórmulas tributárias de produção."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import date
from pathlib import Path
from typing import Any

from tributacao import ContextoTributario, calcular_tributacao

RAIZ_PROJETO = Path(__file__).resolve().parents[2]
FIXTURES_DIR = RAIZ_PROJETO / "tests" / "fixtures" / "tributacao"
RELATORIOS_DIR = Path(__file__).resolve().parent

VALIDADO_CALCULO = "VALIDADO_CALCULO"
VALIDADO_GUARDRAIL = "VALIDADO_GUARDRAIL"
PENDENTE_EVIDENCIA = "PENDENTE_EVIDENCIA"
DIVERGENTE = "DIVERGENTE"
FORA_ESCOPO = "FORA_DO_ESCOPO"

# Compatibilidade com integrações que ainda importam os nomes anteriores.
VALIDADO = VALIDADO_CALCULO
PENDENTE = PENDENTE_EVIDENCIA

STATUS_VALIDACAO = (
    VALIDADO_CALCULO,
    VALIDADO_GUARDRAIL,
    PENDENTE_EVIDENCIA,
    FORA_ESCOPO,
    DIVERGENTE,
)

Calculadora = Callable[[Mapping[str, Any]], dict[str, Any]]


def ganho(entrada: Mapping[str, Any]) -> float:
    """Retorna o ganho positivo usado pelos modelos simplificados."""
    return max(
        0.0,
        float(entrada["valor_bruto"]) - float(entrada["principal"]),
    )


def resultado_calculado(
    entrada: Mapping[str, Any],
    *,
    imposto: float,
    aliquota: float,
    precisao: str,
    regra_id: str,
    pendencias: tuple[str, ...] = (),
    fundamentos: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Monta um resultado independente com o mesmo contrato comparável."""
    imposto_valido = min(max(0.0, float(imposto)), float(entrada["valor_bruto"]))
    return {
        "imposto_estimado": imposto_valido,
        "valor_liquido": float(entrada["valor_bruto"]) - imposto_valido,
        "aliquota_efetiva": max(0.0, float(aliquota)),
        "precisao": precisao,
        "regra_id": regra_id,
        "pendencias": list(pendencias),
        "fundamentos": list(fundamentos),
        "fora_escopo": False,
    }


def resultado_indeterminado(
    *,
    regra_id: str,
    motivo: str,
    fundamentos: tuple[str, ...] = (),
    fora_escopo: bool = False,
) -> dict[str, Any]:
    """Representa recusa segura por falta de dado ou por escopo declarado."""
    return {
        "imposto_estimado": None,
        "valor_liquido": None,
        "aliquota_efetiva": None,
        "precisao": "indeterminada",
        "regra_id": regra_id,
        "pendencias": [motivo],
        "fundamentos": list(fundamentos),
        "fora_escopo": fora_escopo,
    }


def _contexto(entrada: Mapping[str, Any]) -> ContextoTributario:
    dados = dict(entrada)
    dados["data_aplicacao"] = date.fromisoformat(str(dados["data_aplicacao"]))
    dados["data_resgate"] = date.fromisoformat(str(dados["data_resgate"]))
    return ContextoTributario(**dados)


def _resultado_motor(entrada: Mapping[str, Any]) -> dict[str, Any]:
    resultado = calcular_tributacao(_contexto(entrada))
    return {
        "imposto_estimado": resultado.imposto_estimado,
        "valor_liquido": resultado.valor_liquido,
        "aliquota_efetiva": resultado.aliquota_efetiva,
        "precisao": resultado.precisao.value,
        "regra_id": resultado.regra_id,
        "fonte": resultado.fonte,
        "vigencia": resultado.vigencia.isoformat(),
    }


def _numero_confere(
    obtido: float | None,
    esperado: float | None,
    tolerancia: float,
) -> bool:
    if esperado is None:
        return obtido is None
    if obtido is None:
        return False
    return abs(float(obtido) - float(esperado)) <= tolerancia


def _resultado_confere(
    resultado: Mapping[str, Any],
    independente: Mapping[str, Any],
    tolerancias: Mapping[str, float],
) -> bool:
    return all(
        (
            _numero_confere(
                resultado["imposto_estimado"],
                independente["imposto_estimado"],
                float(tolerancias["monetaria"]),
            ),
            _numero_confere(
                resultado["valor_liquido"],
                independente["valor_liquido"],
                float(tolerancias["monetaria"]),
            ),
            _numero_confere(
                resultado["aliquota_efetiva"],
                independente["aliquota_efetiva"],
                float(tolerancias["aliquota"]),
            ),
            resultado["precisao"] == independente["precisao"],
            resultado["regra_id"] == independente["regra_id"],
        )
    )


def _diferenca(
    valor: float | None,
    referencia: float | None,
) -> float | None:
    if valor is None or referencia is None:
        return None
    return float(valor) - float(referencia)


def validar_categoria(
    categoria: str,
    calculadora: Calculadora,
    *,
    fontes_oficiais: Mapping[str, str],
    saida_dir: Path | None = None,
) -> dict[str, Any]:
    """Compara fórmula independente, fixture e motor para uma categoria."""
    fixture_path = FIXTURES_DIR / f"{categoria}.json"
    documento = json.loads(fixture_path.read_text(encoding="utf-8"))
    tolerancias = documento["tolerancias"]
    resultados = []

    for caso in documento["casos"]:
        independente = calculadora(caso["entrada"])
        motor = _resultado_motor(caso["entrada"])
        fixture = caso["esperado"]
        confere_motor = _resultado_confere(motor, independente, tolerancias)
        confere_fixture = _resultado_confere(
            fixture,
            independente,
            tolerancias,
        )

        if not confere_motor or not confere_fixture:
            status = DIVERGENTE
        elif independente["fora_escopo"]:
            status = FORA_ESCOPO
        elif independente["precisao"] == "indeterminada":
            status = VALIDADO_GUARDRAIL
        elif independente["pendencias"]:
            status = PENDENTE_EVIDENCIA
        else:
            status = VALIDADO_CALCULO

        resultados.append(
            {
                "caso_id": caso["id"],
                "status": status,
                "independente": {
                    chave: independente[chave]
                    for chave in (
                        "imposto_estimado",
                        "valor_liquido",
                        "aliquota_efetiva",
                        "precisao",
                        "regra_id",
                    )
                },
                "motor": motor,
                "fixture": fixture,
                "confere_motor": confere_motor,
                "confere_fixture": confere_fixture,
                "diferenca_imposto_motor": _diferenca(
                    motor["imposto_estimado"],
                    independente["imposto_estimado"],
                ),
                "pendencias": independente["pendencias"],
                "fundamentos": independente["fundamentos"],
            }
        )

    contagens = {
        status: sum(item["status"] == status for item in resultados)
        for status in STATUS_VALIDACAO
    }
    relatorio = {
        "_schema_version": 2,
        "categoria": categoria,
        "independente_do_motor": True,
        "fontes_oficiais": dict(fontes_oficiais),
        "resumo": {"total": len(resultados), **contagens},
        "resultados": resultados,
        "aviso": (
            "Validação técnica do escopo modelado; não substitui apuração "
            "fiscal oficial nem revisão profissional."
        ),
    }

    diretorio = saida_dir or RELATORIOS_DIR
    diretorio.mkdir(parents=True, exist_ok=True)
    destino = diretorio / f"relatorio_{categoria}_independente.json"
    destino.write_text(
        json.dumps(relatorio, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    relatorio["arquivo"] = str(destino)
    return relatorio


def imprimir_resumo(relatorio: Mapping[str, Any]) -> None:
    resumo = relatorio["resumo"]
    print(f"VALIDAÇÃO INDEPENDENTE — {relatorio['categoria'].upper()}")
    print(f"Total: {resumo['total']}")
    print(f"Cálculos validados: {resumo[VALIDADO_CALCULO]}")
    print(f"Guardrails validados: {resumo[VALIDADO_GUARDRAIL]}")
    print(f"Pendentes por evidência: {resumo[PENDENTE_EVIDENCIA]}")
    print(f"Fora do escopo: {resumo[FORA_ESCOPO]}")
    print(f"Divergentes: {resumo[DIVERGENTE]}")
    print(f"Relatório: {relatorio['arquivo']}")


def codigo_saida(relatorio: Mapping[str, Any]) -> int:
    return int(relatorio["resumo"][DIVERGENTE] > 0)
