"""Validação independente dos casos tributários críticos de criptoativos.

Este arquivo não importa o pacote ``tributacao`` nem reutiliza suas tabelas.
Ele implementa uma primeira camada de conferência diretamente a partir das
fontes oficiais declaradas abaixo. O resultado não substitui revisão contábil
ou jurídica e não transforma premissa ausente em conclusão tributária.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any

CENTAVO = Decimal("0.01")
ZERO = Decimal(0)
UM = Decimal(1)
ALIQUOTA_EXTERIOR = Decimal("0.15")

FAIXAS_GANHO_CAPITAL = (
    (Decimal(5000000), Decimal("0.15")),
    (Decimal(10000000), Decimal("0.175")),
    (Decimal(30000000), Decimal("0.20")),
    (None, Decimal("0.225")),
)

CASOS_ALVO = {
    "cripto_exterior_ganho_1000",
    "cripto_ganho_acumulado_cruza_5_milhoes",
    "cripto_ganho_total_5_milhoes",
    "cripto_ganho_total_12_milhoes",
}

FONTES_OFICIAIS = {
    "receita_aliquotas_ganho_capital": (
        "https://www.gov.br/receitafederal/pt-br/assuntos/"
        "meu-imposto-de-renda/pagamento/ganhos-de-capital/aliquotas"
    ),
    "lei_13259_2016": (
        "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2016/"
        "lei/l13259.htm"
    ),
    "lei_14754_2023": (
        "https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2023/"
        "lei/l14754.htm"
    ),
    "in_rfb_2180_2024": (
        "https://normas.receita.fazenda.gov.br/sijut2consulta/"
        "link.action?idAto=136603"
    ),
    "manual_mir_eventos_patrimonio": (
        "https://www.gov.br/receitafederal/pt-br/assuntos/"
        "meu-imposto-de-renda/preenchimento/manual-mir/patrimonio/"
        "eventos-do-patrimonio"
    ),
}


@dataclass(frozen=True)
class ResultadoValidacao:
    """Resultado auditável de um caso recalculado fora do motor."""

    caso_id: str
    status: str
    jurisdicao: str
    ganho_atual: float
    base_acumulada_informada: float | None
    imposto_independente: float | None
    valor_liquido_independente: float | None
    aliquota_efetiva_independente: float | None
    imposto_motor: float | None
    diferenca_imposto: float | None
    confere_aritmetica: bool | None
    premissas_pendentes: tuple[str, ...]
    fundamentos: tuple[str, ...]
    observacoes: tuple[str, ...]


def _decimal(nome: str, valor: object) -> Decimal:
    """Converte entrada numérica sem herdar imprecisão de float."""
    if isinstance(valor, bool):
        raise TypeError(f"{nome} não pode ser booleano.")
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise TypeError(f"{nome} deve ser numérico.") from exc
    if not numero.is_finite() or numero < ZERO:
        raise ValueError(f"{nome} deve ser finito e não negativo.")
    return numero


def _dinheiro(valor: Decimal) -> Decimal:
    """Arredonda valor monetário para centavos."""
    return valor.quantize(CENTAVO, rounding=ROUND_HALF_UP)


def _float_ou_none(valor: Decimal | None) -> float | None:
    return None if valor is None else float(valor)


def imposto_progressivo_sobre_ganho(ganho: Decimal) -> Decimal:
    """Aplica progressivamente as faixas de ganho de capital."""
    restante = max(ZERO, ganho)
    imposto = ZERO
    limite_anterior = ZERO

    for limite, aliquota in FAIXAS_GANHO_CAPITAL:
        if limite is None:
            imposto += restante * aliquota
            break

        largura = limite - limite_anterior
        parcela = min(restante, largura)
        imposto += parcela * aliquota
        restante -= parcela
        if restante <= ZERO:
            break
        limite_anterior = limite

    return _dinheiro(imposto)


def _comparar_imposto(
    imposto_independente: Decimal,
    esperado: dict[str, Any],
    tolerancia: Decimal,
) -> tuple[Decimal | None, Decimal | None, bool | None]:
    imposto_motor_raw = esperado.get("imposto_estimado")
    if imposto_motor_raw is None:
        return None, None, None

    imposto_motor = _decimal("imposto_estimado", imposto_motor_raw)
    diferenca = _dinheiro(imposto_independente - imposto_motor)
    return imposto_motor, diferenca, abs(diferenca) <= tolerancia


def _resultado_domestico(
    caso: dict[str, Any],
    tolerancia: Decimal,
) -> ResultadoValidacao:
    entrada = caso["entrada"]
    metadados = entrada.get("metadados", {})
    principal = _decimal("principal", entrada["principal"])
    valor_bruto = _decimal("valor_bruto", entrada["valor_bruto"])
    ganho_atual = max(ZERO, valor_bruto - principal)

    acumulado_raw = metadados.get("ganho_acumulado_ano")
    ganho_acumulado = (
        ganho_atual
        if acumulado_raw is None
        else _decimal("ganho_acumulado_ano", acumulado_raw)
    )
    if ganho_acumulado < ganho_atual:
        raise ValueError(
            f"{caso['id']}: ganho acumulado não pode ser menor que o atual."
        )

    ganho_anterior = ganho_acumulado - ganho_atual
    imposto = _dinheiro(
        imposto_progressivo_sobre_ganho(ganho_acumulado)
        - imposto_progressivo_sobre_ganho(ganho_anterior)
    )
    liquido = _dinheiro(valor_bruto - imposto)
    aliquota = ZERO if ganho_atual == ZERO else imposto / ganho_atual
    imposto_motor, diferenca, confere = _comparar_imposto(
        imposto,
        caso["esperado"],
        tolerancia,
    )

    pendencias = []
    observacoes = [
        ("As faixas foram aplicadas progressivamente sobre o ganho, não "
        "sobre o valor bruto da alienação.")
    ]
    if acumulado_raw is not None and not bool(
        metadados.get("alienacoes_parciais_mesmo_bem_confirmadas", False)
    ):
        pendencias.append(
            "Confirmar que a agregação decorre de alienações parciais do "
            "mesmo bem ou direito e atende ao período legal aplicável."
        )
        observacoes.append(
            "O nome ganho_acumulado_ano, isoladamente, não comprova a "
            "hipótese de agregação prevista na Lei 13.259/2016."
        )

    if confere is False:
        status = "DIVERGENTE"
    elif pendencias:
        status = "PENDENTE_PREMISSA"
    else:
        status = "VALIDADO_PRIMEIRA_CAMADA"

    return ResultadoValidacao(
        caso_id=caso["id"],
        status=status,
        jurisdicao="brasil",
        ganho_atual=float(ganho_atual),
        base_acumulada_informada=float(ganho_acumulado),
        imposto_independente=float(imposto),
        valor_liquido_independente=float(liquido),
        aliquota_efetiva_independente=float(aliquota),
        imposto_motor=_float_ou_none(imposto_motor),
        diferenca_imposto=_float_ou_none(diferenca),
        confere_aritmetica=confere,
        premissas_pendentes=tuple(pendencias),
        fundamentos=(
            "Receita Federal — Alíquotas de ganhos de capital",
            "Lei 13.259/2016, art. 1º",
        ),
        observacoes=tuple(observacoes),
    )


def _resultado_exterior(
    caso: dict[str, Any],
    tolerancia: Decimal,
) -> ResultadoValidacao:
    entrada = caso["entrada"]
    metadados = entrada.get("metadados", {})
    principal = _decimal("principal", entrada["principal"])
    valor_bruto = _decimal("valor_bruto", entrada["valor_bruto"])
    ganho = max(ZERO, valor_bruto - principal)

    # Cálculo condicional: só é conclusivo se o ativo estiver enquadrado como
    # aplicação financeira no exterior nos termos da IN RFB 2.180/2024.
    imposto = _dinheiro(ganho * ALIQUOTA_EXTERIOR)
    liquido = _dinheiro(valor_bruto - imposto)
    aliquota = ZERO if ganho == ZERO else imposto / ganho
    imposto_motor, diferenca, confere = _comparar_imposto(
        imposto,
        caso["esperado"],
        tolerancia,
    )

    enquadramento_confirmado = bool(
        metadados.get(
            "enquadramento_aplicacao_financeira_exterior_confirmado",
            False,
        )
    )
    pendencias = []
    if not enquadramento_confirmado:
        pendencias.append(
            "Confirmar que o criptoativo, além de custodiado ou negociado "
            "no exterior, enquadra-se como aplicação financeira no exterior."
        )

    if confere is False:
        status = "DIVERGENTE"
    elif pendencias:
        status = "PENDENTE_PREMISSA"
    else:
        status = "VALIDADO_PRIMEIRA_CAMADA"

    return ResultadoValidacao(
        caso_id=caso["id"],
        status=status,
        jurisdicao="exterior",
        ganho_atual=float(ganho),
        base_acumulada_informada=None,
        imposto_independente=float(imposto),
        valor_liquido_independente=float(liquido),
        aliquota_efetiva_independente=float(aliquota),
        imposto_motor=_float_ou_none(imposto_motor),
        diferenca_imposto=_float_ou_none(diferenca),
        confere_aritmetica=confere,
        premissas_pendentes=tuple(pendencias),
        fundamentos=(
            "Lei 14.754/2023, arts. 2º e 3º",
            "IN RFB 2.180/2024, arts. 9º e 10",
            "Manual MIR — Eventos do Patrimônio",
        ),
        observacoes=(
            ("O imposto de 15% é apurado no ajuste anual; o valor líquido "
            "aqui é uma projeção econômica, não retenção no resgate."),
            ("A localização no exterior não resolve sozinha o enquadramento "
            "material do ativo virtual."),
        ),
    )


def validar_caso(
    caso: dict[str, Any],
    tolerancia: Decimal,
) -> ResultadoValidacao:
    """Seleciona a regra independente pela jurisdição informada."""
    entrada = caso.get("entrada", {})
    metadados = entrada.get("metadados", {})
    jurisdicao = str(metadados.get("jurisdicao_custodia", "")).casefold()
    if jurisdicao == "brasil":
        return _resultado_domestico(caso, tolerancia)
    if jurisdicao == "exterior":
        return _resultado_exterior(caso, tolerancia)
    raise ValueError(
        f"{caso.get('id', '<sem id>')}: jurisdição ausente ou inválida."
    )


def _carregar_casos(caminho: Path) -> tuple[list[dict[str, Any]], Decimal]:
    with caminho.open(encoding="utf-8") as arquivo:
        documento = json.load(arquivo)

    casos_por_id = {caso["id"]: caso for caso in documento["casos"]}
    faltantes = sorted(CASOS_ALVO - set(casos_por_id))
    if faltantes:
        raise ValueError(f"Casos críticos ausentes da fixture: {faltantes}.")

    tolerancia = _decimal(
        "tolerância monetária",
        documento["tolerancias"]["monetaria"],
    )
    return [casos_por_id[caso_id] for caso_id in sorted(CASOS_ALVO)], tolerancia


def _resumo(resultados: list[ResultadoValidacao]) -> dict[str, int]:
    return {
        "total": len(resultados),
        "validado_primeira_camada": sum(
            resultado.status == "VALIDADO_PRIMEIRA_CAMADA"
            for resultado in resultados
        ),
        "pendente_premissa": sum(
            resultado.status == "PENDENTE_PREMISSA"
            for resultado in resultados
        ),
        "divergente": sum(
            resultado.status == "DIVERGENTE" for resultado in resultados
        ),
        "confere_aritmetica": sum(
            resultado.confere_aritmetica is True for resultado in resultados
        ),
    }


def _gravar_relatorio(
    caminho: Path,
    resultados: list[ResultadoValidacao],
) -> None:
    relatorio = {
        "_schema_version": 1,
        "escopo": "validacao_independente_cripto_casos_criticos",
        "independente_do_motor": True,
        "fontes_oficiais": FONTES_OFICIAIS,
        "resumo": _resumo(resultados),
        "resultados": [asdict(resultado) for resultado in resultados],
        "aviso": (
            "Primeira camada técnica. Casos pendentes não devem ser "
            "marcados como validados na matriz tributária."
        ),
    }
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(
        json.dumps(relatorio, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _formatar_console(
    resultados: list[ResultadoValidacao],
    saida: Path,
) -> str:
    linhas = ["VALIDAÇÃO INDEPENDENTE — CRIPTOATIVOS", ""]
    for resultado in resultados:
        linhas.extend(
            (
                f"[{resultado.status}] {resultado.caso_id}",
                f"  Imposto independente: {resultado.imposto_independente}",
                f"  Imposto do motor:      {resultado.imposto_motor}",
                f"  Diferença:             {resultado.diferenca_imposto}",
            )
        )
        for pendencia in resultado.premissas_pendentes:
            linhas.append(f"  PENDÊNCIA: {pendencia}")
        linhas.append("")

    resumo = _resumo(resultados)
    linhas.extend(
        (
            f"Total: {resumo['total']}",
            (f"Validados na primeira camada: "
            f"{resumo['validado_primeira_camada']}"),
            f"Pendentes por premissa: {resumo['pendente_premissa']}",
            f"Divergentes: {resumo['divergente']}",
            f"Relatório: {saida}",
        )
    )
    return "\n".join(linhas) + "\n"


def _argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Recalcula, sem importar o motor tributário, os quatro casos "
            "críticos de criptoativos."
        )
    )
    parser.add_argument(
        "--fixtures",
        type=Path,
        default=Path("tests/fixtures/tributacao/cripto.json"),
        help="Caminho do arquivo cripto.json.",
    )
    parser.add_argument(
        "--saida",
        type=Path,
        default=Path(
            "validacao/tributacao/relatorio_cripto_independente.json"
        ),
        help="Caminho do relatório JSON gerado.",
    )
    parser.add_argument(
        "--falhar-em-pendencia",
        action="store_true",
        help="Retorna código 2 se alguma premissa jurídica estiver pendente.",
    )
    return parser.parse_args()


def main() -> int:
    """Executa a validação, grava o relatório e devolve código de estado."""
    args = _argumentos()
    casos, tolerancia = _carregar_casos(args.fixtures)
    resultados = [validar_caso(caso, tolerancia) for caso in casos]
    _gravar_relatorio(args.saida, resultados)
    sys.stdout.write(_formatar_console(resultados, args.saida))

    resumo = _resumo(resultados)
    if resumo["divergente"]:
        return 1
    if args.falhar_em_pendencia and resumo["pendente_premissa"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())