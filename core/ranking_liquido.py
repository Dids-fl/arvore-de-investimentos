"""Comparações econômicas líquidas usadas depois dos filtros de adequação."""

from __future__ import annotations

import calendar
import math
import unicodedata
from collections.abc import Mapping
from datetime import date
from typing import Any

from calculos import _vf_liquido_tributado
from tributacao.regras import imposto_irpf_anual

LIMITE_DEDUCAO_PGBL = 0.12
PESO_EFICIENCIA_LIQUIDA = 0.15


def _numero_finito(
    nome: str,
    valor: object,
    *,
    minimo: float | None = None,
) -> float:
    if isinstance(valor, bool):
        raise TypeError(f"{nome} não pode ser booleano.")
    try:
        numero = float(valor)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{nome} deve ser numérico.") from exc
    if not math.isfinite(numero):
        raise ValueError(f"{nome} deve ser finito.")
    if minimo is not None and numero < minimo:
        raise ValueError(f"{nome} deve ser >= {minimo}.")
    return numero


def _meses_do_prazo(anos: float) -> int:
    prazo = _numero_finito("anos", anos, minimo=0.0)
    return max(0, round(prazo * 12))


def _somar_meses(data_base: date, quantidade: int) -> date:
    indice = data_base.year * 12 + data_base.month - 1 + quantidade
    ano, mes_zero = divmod(indice, 12)
    mes = mes_zero + 1
    dia = min(data_base.day, calendar.monthrange(ano, mes)[1])
    return date(ano, mes, dia)


def _indice_mensal_ate(
    data_base: date,
    data_alvo: date,
    limite_meses: int,
) -> int:
    for indice in range(limite_meses + 1):
        if _somar_meses(data_base, indice) >= data_alvo:
            return indice
    return limite_meses


def _mapa_anual_numerico(
    nome: str,
    valores: Mapping[int | str, object] | None,
) -> dict[int, float]:
    if valores is None:
        return {}
    if not isinstance(valores, Mapping):
        raise TypeError(f"{nome} deve ser um mapeamento por ano.")
    resultado: dict[int, float] = {}
    for ano, valor in valores.items():
        if isinstance(ano, bool):
            raise TypeError(f"As chaves de {nome} devem ser anos.")
        try:
            ano_inteiro = int(ano)
        except (TypeError, ValueError) as exc:
            raise TypeError(f"As chaves de {nome} devem ser anos.") from exc
        if ano_inteiro < 1900 or ano_inteiro > 9999:
            raise ValueError(f"Ano inválido em {nome}: {ano_inteiro}.")
        resultado[ano_inteiro] = _numero_finito(
            f"{nome}[{ano_inteiro}]",
            valor,
            minimo=0.0,
        )
    return resultado


def _valor_presente(fluxos: list[float], taxa_mensal: float) -> float:
    fator = 1.0 + taxa_mensal
    valor = 0.0
    for fluxo in reversed(fluxos):
        valor = valor / fator + fluxo
        if math.isinf(valor):
            return valor
    return valor


def _tir_mensal(fluxos: list[float]) -> float | None:
    """Resolve a TIR mensal por bisseção sem depender de NumPy Financial."""
    if not fluxos or not any(valor < 0 for valor in fluxos):
        return None
    if not any(valor > 0 for valor in fluxos):
        return None

    inferior = -0.999999
    superior = 1.0
    vp_inferior = _valor_presente(fluxos, inferior)
    vp_superior = _valor_presente(fluxos, superior)
    while vp_inferior * vp_superior > 0 and superior < 1_000_000:
        superior = superior * 2.0 + 1.0
        vp_superior = _valor_presente(fluxos, superior)
    if vp_inferior * vp_superior > 0:
        return None

    for _ in range(180):
        meio = (inferior + superior) / 2.0
        vp_meio = _valor_presente(fluxos, meio)
        if abs(vp_meio) <= 1e-10:
            return meio
        if vp_inferior * vp_meio <= 0:
            superior = meio
        else:
            inferior = meio
            vp_inferior = vp_meio
    return (inferior + superior) / 2.0


def _tir_anual(fluxos: list[float]) -> float | None:
    mensal = _tir_mensal(fluxos)
    if mensal is None:
        return None
    return (1.0 + mensal) ** 12 - 1.0


def beneficios_fiscais_pgbl(
    cap_inicial: float,
    aporte_mensal: float,
    anos: float,
    *,
    data_referencia: date,
    renda_tributavel_anual: float,
    elegibilidade_confirmada: bool,
    deducao_ja_utilizada_primeiro_ano: float = 0.0,
    base_calculo_irpf_anual: float | None = None,
    renda_tributavel_por_ano: Mapping[int | str, object] | None = None,
    base_calculo_irpf_por_ano: Mapping[int | str, object] | None = None,
    deducao_ja_utilizada_por_ano: Mapping[int | str, object] | None = None,
    crescimento_renda_anual: float = 0.0,
    capital_inicial_dedutivel: bool = True,
) -> list[dict[str, float | int]]:
    """Estima o benefício por ano-calendário sem misturá-lo ao resgate."""
    capital = _numero_finito("cap_inicial", cap_inicial, minimo=0.0)
    aporte = _numero_finito("aporte_mensal", aporte_mensal, minimo=0.0)
    renda = _numero_finito(
        "renda_tributavel_anual",
        renda_tributavel_anual,
        minimo=0.0,
    )
    usado = _numero_finito(
        "deducao_ja_utilizada_primeiro_ano",
        deducao_ja_utilizada_primeiro_ano,
        minimo=0.0,
    )
    crescimento = _numero_finito(
        "crescimento_renda_anual",
        crescimento_renda_anual,
    )
    if crescimento <= -1:
        raise ValueError("crescimento_renda_anual deve ser maior que -100%.")
    if not isinstance(data_referencia, date):
        raise TypeError("data_referencia deve ser datetime.date.")
    if not isinstance(elegibilidade_confirmada, bool):
        raise TypeError("elegibilidade_confirmada deve ser booleano.")
    if not isinstance(capital_inicial_dedutivel, bool):
        raise TypeError("capital_inicial_dedutivel deve ser booleano.")
    if not elegibilidade_confirmada:
        return []

    meses = _meses_do_prazo(anos)
    if meses == 0 or capital + aporte * meses == 0:
        return []

    rendas_informadas = _mapa_anual_numerico(
        "renda_tributavel_por_ano",
        renda_tributavel_por_ano,
    )
    bases_informadas = _mapa_anual_numerico(
        "base_calculo_irpf_por_ano",
        base_calculo_irpf_por_ano,
    )
    deducoes_informadas = _mapa_anual_numerico(
        "deducao_ja_utilizada_por_ano",
        deducao_ja_utilizada_por_ano,
    )
    deducoes_informadas.setdefault(data_referencia.year, usado)

    contribuicoes_por_ano: dict[int, float] = {}
    if capital_inicial_dedutivel and capital > 0:
        contribuicoes_por_ano[data_referencia.year] = capital
    if aporte > 0:
        for numero_aporte in range(1, meses + 1):
            ano_aporte = _somar_meses(data_referencia, numero_aporte).year
            contribuicoes_por_ano[ano_aporte] = (
                contribuicoes_por_ano.get(ano_aporte, 0.0) + aporte
            )

    base_padrao = (
        None
        if base_calculo_irpf_anual is None
        else _numero_finito(
            "base_calculo_irpf_anual",
            base_calculo_irpf_anual,
            minimo=0.0,
        )
    )
    beneficios: list[dict[str, float | int]] = []
    data_resgate = _somar_meses(data_referencia, meses)
    for ano in sorted(contribuicoes_por_ano):
        distancia_anos = ano - data_referencia.year
        renda_ano = rendas_informadas.get(
            ano,
            renda * ((1.0 + crescimento) ** distancia_anos),
        )
        base_ano = bases_informadas.get(
            ano,
            renda_ano if base_padrao is None else base_padrao,
        )
        contribuicao = contribuicoes_por_ano[ano]
        limite_anual = renda_ano * LIMITE_DEDUCAO_PGBL
        limite_disponivel = max(
            0.0,
            limite_anual - deducoes_informadas.get(ano, 0.0),
        )
        deducao = min(contribuicao, limite_disponivel)
        imposto_sem = imposto_irpf_anual(
            base_ano,
            rendimentos_tributaveis=renda_ano,
        )
        imposto_com = imposto_irpf_anual(
            max(0.0, base_ano - deducao),
            rendimentos_tributaveis=renda_ano,
        )
        encerramento_ano = min(date(ano, 12, 31), data_resgate)
        beneficios.append(
            {
                "ano": ano,
                "mes_recebimento": _indice_mensal_ate(
                    data_referencia,
                    encerramento_ano,
                    meses,
                ),
                "contribuicao_pgbl": contribuicao,
                "deducao_utilizada": deducao,
                "beneficio_fiscal": max(0.0, imposto_sem - imposto_com),
                "renda_tributavel": renda_ano,
                "base_calculo_irpf": base_ano,
                "regra_tributaria_extrapolada": ano != 2026,
            }
        )
    return beneficios


def _fluxos_com_resgate(
    cap_inicial: float,
    aporte_mensal: float,
    meses: int,
    valor_resgate: float,
    beneficios: list[dict[str, float | int]] | None = None,
) -> list[float]:
    fluxos = [-cap_inicial] + [-aporte_mensal] * meses
    fluxos[meses] += valor_resgate
    for beneficio in beneficios or []:
        mes = int(beneficio["mes_recebimento"])
        fluxos[mes] += float(beneficio["beneficio_fiscal"])
    return fluxos


def comparar_pgbl_vgbl(
    cap_inicial: float,
    aporte_mensal: float,
    taxa_anual: float,
    anos: float,
    *,
    data_referencia: date,
    regime: str | None,
    renda_tributavel_anual: float | None,
    declaracao_completa: bool,
    elegibilidade_deducao_pgbl: bool | None,
    deducao_ja_utilizada_primeiro_ano: float = 0.0,
    metadados_pgbl: Mapping[str, Any] | None = None,
    renda_tributavel_por_ano: Mapping[int | str, object] | None = None,
    crescimento_renda_anual: float = 0.0,
) -> dict[str, Any]:
    """Compara PGBL e VGBL com os mesmos fluxos, prazo e retorno bruto."""
    capital = _numero_finito("cap_inicial", cap_inicial, minimo=0.0)
    aporte = _numero_finito("aporte_mensal", aporte_mensal, minimo=0.0)
    taxa = _numero_finito("taxa_anual", taxa_anual)
    if taxa <= -1:
        raise ValueError("taxa_anual deve ser maior que -100%.")
    if not isinstance(data_referencia, date):
        raise TypeError("data_referencia deve ser datetime.date.")
    if not isinstance(declaracao_completa, bool):
        raise TypeError("declaracao_completa deve ser booleano.")
    if elegibilidade_deducao_pgbl not in {True, False, None}:
        raise TypeError(
            "elegibilidade_deducao_pgbl deve ser booleano ou None."
        )

    prazo = _numero_finito("anos", anos, minimo=0.0)
    meses = _meses_do_prazo(prazo)
    if meses == 0 or capital + aporte * meses == 0:
        return {
            "aplicado": False,
            "motivo": "Não há prazo ou fluxo positivo para comparar.",
            "produto_escolhido": None,
            "alternativas": {},
        }

    metadados = dict(metadados_pgbl or {})
    argumentos = {
        "cap": capital,
        "ap": aporte,
        "taxa_a": taxa,
        "anos": prazo,
        "data_referencia": data_referencia,
        "regime": regime,
        "renda_tributavel": renda_tributavel_anual,
    }
    pgbl = _vf_liquido_tributado(
        tipo_produto="pgbl",
        metadados=metadados,
        **argumentos,
    )
    vgbl = _vf_liquido_tributado(
        tipo_produto="vgbl",
        metadados=metadados,
        **argumentos,
    )
    if pgbl["liquido"] is None or vgbl["liquido"] is None:
        return {
            "aplicado": False,
            "motivo": (
                "A comparação exige regime previdenciário e dados fiscais "
                "suficientes para liquidar PGBL e VGBL."
            ),
            "produto_escolhido": None,
            "alternativas": {"pgbl": pgbl, "vgbl": vgbl},
        }

    beneficio_confirmado = (
        declaracao_completa and elegibilidade_deducao_pgbl is True
    )
    if beneficio_confirmado and renda_tributavel_anual is None:
        return {
            "aplicado": False,
            "motivo": (
                "A elegibilidade do PGBL foi confirmada, mas falta a renda "
                "tributável anual para quantificar a dedução."
            ),
            "produto_escolhido": None,
            "alternativas": {"pgbl": pgbl, "vgbl": vgbl},
        }

    beneficios = (
        beneficios_fiscais_pgbl(
            capital,
            aporte,
            prazo,
            data_referencia=data_referencia,
            renda_tributavel_anual=float(renda_tributavel_anual),
            elegibilidade_confirmada=True,
            deducao_ja_utilizada_primeiro_ano=(
                deducao_ja_utilizada_primeiro_ano
            ),
            base_calculo_irpf_anual=metadados.get(
                "base_calculo_irpf_anual"
            ),
            renda_tributavel_por_ano=renda_tributavel_por_ano,
            base_calculo_irpf_por_ano=metadados.get(
                "base_calculo_irpf_por_ano"
            ),
            deducao_ja_utilizada_por_ano=metadados.get(
                "deducao_ja_utilizada_por_ano"
            ),
            crescimento_renda_anual=crescimento_renda_anual,
            capital_inicial_dedutivel=not bool(
                metadados.get("lotes_previdencia_existentes")
            ),
        )
        if beneficio_confirmado
        else []
    )
    fluxos_pgbl = _fluxos_com_resgate(
        capital,
        aporte,
        meses,
        float(pgbl["liquido"]),
        beneficios,
    )
    fluxos_vgbl = _fluxos_com_resgate(
        capital,
        aporte,
        meses,
        float(vgbl["liquido"]),
    )
    tir_pgbl = _tir_anual(fluxos_pgbl)
    tir_vgbl = _tir_anual(fluxos_vgbl)
    if tir_pgbl is None or tir_vgbl is None:
        return {
            "aplicado": False,
            "motivo": "Não foi possível obter uma TIR válida para os fluxos.",
            "produto_escolhido": None,
            "alternativas": {"pgbl": pgbl, "vgbl": vgbl},
        }

    alternativas = {
        "pgbl": {
            "valor_liquido_no_plano": float(pgbl["liquido"]),
            "imposto_no_resgate": float(pgbl["imposto_estimado"]),
            "beneficio_fiscal_total": sum(
                float(item["beneficio_fiscal"]) for item in beneficios
            ),
            "beneficios_por_ano": beneficios,
            "tir_liquida_anual": tir_pgbl,
            "precisao_tributaria": pgbl["precisao"],
        },
        "vgbl": {
            "valor_liquido_no_plano": float(vgbl["liquido"]),
            "imposto_no_resgate": float(vgbl["imposto_estimado"]),
            "beneficio_fiscal_total": 0.0,
            "beneficios_por_ano": [],
            "tir_liquida_anual": tir_vgbl,
            "precisao_tributaria": vgbl["precisao"],
        },
    }
    escolhido = "pgbl" if tir_pgbl > tir_vgbl else "vgbl"
    return {
        "aplicado": True,
        "motivo": (
            "Escolha pela maior TIR líquida com os mesmos fluxos, prazo "
            "e retorno bruto."
        ),
        "produto_escolhido": escolhido,
        "beneficio_pgbl_confirmado": beneficio_confirmado,
        "anos_regra_tributaria_extrapolada": [
            int(item["ano"])
            for item in beneficios
            if item["regra_tributaria_extrapolada"]
        ],
        "adequacao_pre_filtrada": True,
        "criterio_desempate": "maior_tir_liquida_anual",
        "alternativas": alternativas,
        "premissas": [
            "PGBL e VGBL foram comparados dentro da mesma finalidade.",
            (
                "O benefício do PGBL só foi incluído quando declaração "
                "completa e elegibilidade legal foram confirmadas."
            ),
            (
                "A renda, a tabela de 2026 e o retorno bruto foram mantidos "
                "constantes durante a projeção."
            ),
        ],
    }


def tipo_tributario_fundo(classe: object) -> str | None:
    """Mapeia apenas classificações cujo regime pode ser inferido com segurança."""
    if not isinstance(classe, str) or not classe.strip():
        return None
    texto = unicodedata.normalize("NFKD", classe.casefold())
    texto = "".join(
        caractere
        for caractere in texto
        if not unicodedata.combining(caractere)
    )
    if "acoes" in texto:
        return "fundo_acoes"
    if "curto prazo" in texto:
        return "fundo_curto_prazo"
    if any(
        termo in texto
        for termo in (
            "renda fixa",
            "referenciado",
            "multimercado",
            "cambial",
            "credito privado",
        )
    ):
        return "fundo_longo_prazo"
    return None


def avaliar_fundo_liquido(
    indicadores: Mapping[str, Any],
    *,
    prazo_anos: float,
    data_referencia: date,
    retorno_esperado_anual: float | None,
) -> dict[str, Any]:
    """Projeta R$ 100 pela cota histórica e liquida o imposto do cotista."""
    if not isinstance(indicadores, Mapping):
        raise TypeError("indicadores deve ser um mapeamento.")
    tipo = tipo_tributario_fundo(indicadores.get("classe"))
    if tipo is None:
        return {
            "aplicado": False,
            "motivo": "Classificação tributária do fundo indeterminada.",
        }
    if retorno_esperado_anual is None:
        return {
            "aplicado": False,
            "motivo": (
                "Retorno esperado não informado; o histórico não foi usado "
                "como previsão automática."
            ),
        }
    retorno = _numero_finito(
        "retorno_esperado_anual",
        retorno_esperado_anual,
    )
    if retorno <= -1:
        return {
            "aplicado": False,
            "motivo": "Retorno histórico incompatível com a projeção.",
        }
    prazo = _numero_finito("prazo_anos", prazo_anos, minimo=0.01)
    projecao = _vf_liquido_tributado(
        100.0,
        0.0,
        retorno,
        prazo,
        tipo,
        data_referencia=data_referencia,
    )
    if projecao["liquido"] is None:
        return {
            "aplicado": False,
            "motivo": "Tributação líquida do fundo ficou indeterminada.",
            "tipo_produto": tipo,
        }
    liquido = float(projecao["liquido"])
    retorno_liquido = (liquido / 100.0) ** (1.0 / prazo) - 1.0
    return {
        "aplicado": True,
        "tipo_produto": tipo,
        "retorno_esperado_anual": retorno,
        "retorno_historico_cagr": indicadores.get("cagr"),
        "retorno_historico_12m": indicadores.get("retorno_12m"),
        "retorno_liquido_anual": retorno_liquido,
        "valor_liquido_notional": liquido,
        "imposto_notional": float(projecao["imposto_estimado"]),
        "precisao_tributaria": projecao["precisao"],
        "retorno_cota_liquido_despesas_fundo": True,
        "metodo_tributacao": projecao.get("metodo_tributacao"),
        "premissas": [
            "O retorno da cota foi tratado como líquido das despesas do fundo.",
            "O histórico não garante o retorno futuro.",
            "A regra tributária de 2026 foi mantida até o resgate projetado.",
        ],
    }


def combinar_scores(
    score_adequacao: float,
    score_eficiencia_liquida: float,
    *,
    peso_eficiencia: float = PESO_EFICIENCIA_LIQUIDA,
) -> float:
    """Mantém adequação dominante e limita o efeito do retorno líquido."""
    adequacao = _numero_finito("score_adequacao", score_adequacao)
    eficiencia = _numero_finito(
        "score_eficiencia_liquida",
        score_eficiencia_liquida,
    )
    peso = _numero_finito("peso_eficiencia", peso_eficiencia, minimo=0.0)
    if peso > 1:
        raise ValueError("peso_eficiencia deve estar entre 0 e 1.")
    combinado = adequacao * (1.0 - peso) + eficiencia * peso
    return round(max(0.0, min(10.0, combinado)), 2)
