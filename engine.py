"""Núcleo de negócio compartilhado pela CLI, pelo Streamlit e por APIs."""

from __future__ import annotations

import math
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime, timezone
from typing import Any

from calculos import (
    _vf_bruto,
    _vf_liquido,
    _vf_liquido_tributado,
    _vf_real,
)
from core.catalogo import _disp, _get_prod, _tipo_tributario
from core.categorias import RK, _risco
from core.ranking_liquido import comparar_pgbl_vgbl
from macroeconomia.curva_selic import (
    ProjecaoSelic,
    projetar_selic,
)
from portfolio import _build_portfolio, _classificar_portfolio_final
from recomendador import (
    DividaJurosAltosError,
    RecomendacaoBloqueadaError,
    calcular_recomendacao,
)
from recomendador_ativos import (
    _CLASSE,
    _LABEL,
    MIN_PCT,
    recomendar_por_portfolio,
)
from tributacao import PrecisaoTributaria

__all__ = [
    "ANOS_GRAFICO_PADRAO",
    "ANOS_PROJECAO_PADRAO",
    "RESPOSTAS_MAP",
    "RISCO_LABEL",
    "ROTULOS_CLASSES_ATIVOS",
    "DividaJurosAltosError",
    "RecomendacaoBloqueadaError",
    "analisar_meta",
    "aporte_necessario_para_meta",
    "buscar_ativos_da_analise",
    "buscar_ativos_sugeridos",
    "criar_analise",
    "gerar_recomendacao_completa",
    "mapear_respostas_formulario",
    "montar_payload_exportacao",
    "nome_categoria",
    "normalizar_experiencia",
    "projecao_selic_mercado",
    "projetar_portfolio",
    "resumo_taxas_mercado",
    "rotulo_classe_ativo",
    "tabela_projecao",
    "tabela_projecao_portfolio",
    "taxa_base_mercado",
    "taxas_por_risco",
]


ANOS_PROJECAO_PADRAO = (1, 2, 5, 10, 20, 30)
ANOS_GRAFICO_PADRAO = tuple(range(1, 31))
RISCO_LABEL = {1: "Conservador", 2: "Moderado", 3: "Agressivo"}
ROTULOS_CLASSES_ATIVOS = dict(_LABEL)
_PRAZO_REFERENCIA_MESES = {
    1: 12,
    2: 42,
    3: 120,
}
_ORDEM_PRECISAO_TRIBUTARIA = {
    PrecisaoTributaria.EXATA_PARA_PREMISSAS.value: 0,
    PrecisaoTributaria.ESTIMADA.value: 1,
    PrecisaoTributaria.INDETERMINADA.value: 2,
}


RESPOSTAS_MAP: dict[str, dict[str, int]] = {
    "prazo": {"curto": 1, "médio": 2, "medio": 2, "longo": 3},
    "risco": {"baixo": 1, "médio": 2, "medio": 2, "alto": 3},
    "objetivo": {
        "reserva": 1,
        "crescimento": 2,
        "aposentadoria": 3,
    },
    "fluxo": {"renda": 1, "acúmulo": 2, "acumulo": 2},
    "controle": {"gerir": 1, "delegar": 2},
    "liquidez": {"sim": 1, "não": 2, "nao": 2},
    "reserva_emerg": {
        "não tenho": 1,
        "nao tenho": 1,
        "parcial": 2,
        "sim": 3,
    },
    "idade": {"jovem": 1, "adulto": 2, "sênior": 3, "senior": 3},
    "despesas": {"nenhuma": 1, "baixas": 2, "altas": 3},
    "faixa_valor": {"baixo": 1, "médio": 2, "medio": 2, "alto": 3},
    "patrim_pct": {"baixo": 1, "médio": 2, "medio": 2, "alto": 3},
    "renda": {
        "clt": 1,
        "pj contratado": 2,
        "pj": 2,
        "autônomo": 3,
        "autonomo": 3,
        "sem renda": 4,
    },
    "dividas": {
        "juros altos": 1,
        "juros baixos": 2,
        "não tenho": 3,
        "nao tenho": 3,
    },
    "conhecimento": {
        "iniciante": 1,
        "intermediário": 2,
        "intermediario": 2,
        "experiente": 3,
    },
    "dependentes": {"nenhum": 1, "um": 2, "dois ou mais": 3},
    "aporte": {"único": 1, "unico": 1, "mensal": 2},
    "emocional": {
        "venderia tudo": 1,
        "esperaria recuperar": 2,
        "compraria mais": 3,
    },
    "ir_tipo": {
        "completo": 1,
        "simplificado": 2,
        "não declaro": 3,
        "nao declaro": 3,
    },
    "carteira_atual": {
        "não tenho": 1,
        "nao tenho": 1,
        "conservadora": 2,
        "moderada": 3,
        "arrojada": 4,
    },
    "modo_meta": {"sim": 1, "rendendo": 2, "não": 3, "nao": 3},
}

_CAMPOS_RECOMENDACAO = {
    "prazo",
    "risco",
    "objetivo",
    "fluxo",
    "controle",
    "liquidez",
    "liquidez_pct",
    "reserva_emerg",
    "idade",
    "despesas",
    "faixa_valor",
    "patrim_pct",
    "renda",
    "dividas",
    "conhecimento",
    "experiencia",
    "dependentes",
    "aporte",
    "emocional",
    "ir_tipo",
    "carteira_atual",
}

_EXPERIENCIAS = {
    "poupanca": "poupança",
    "tesouro": "tesouro",
    "acoes": "ações",
    "fundos": "fundos",
    "opcoes": "opções",
    "nenhum": "nenhum",
}
_ORDEM_EXPERIENCIAS = {
    nome: indice
    for indice, nome in enumerate(_EXPERIENCIAS.values())
}


def _normalizar_texto(valor: str) -> str:
    decomposicao = unicodedata.normalize("NFKD", valor.casefold().strip())
    sem_acentos = "".join(
        caractere
        for caractere in decomposicao
        if not unicodedata.combining(caractere)
    )
    return " ".join(sem_acentos.split())


def mapear_respostas_formulario(respostas_texto: dict) -> dict:
    """Converte opções textuais nos códigos inteiros usados pelo motor."""
    if not isinstance(respostas_texto, Mapping):
        raise TypeError("respostas_texto deve ser um mapeamento.")

    resultado: dict = {}
    for campo, valor in respostas_texto.items():
        mapa = RESPOSTAS_MAP.get(campo)
        if mapa is None or not isinstance(valor, str):
            resultado[campo] = valor
            continue

        mapa_normalizado = {
            _normalizar_texto(opcao): codigo
            for opcao, codigo in mapa.items()
        }
        chave = _normalizar_texto(valor)
        if chave not in mapa_normalizado:
            opcoes = ", ".join(sorted(set(mapa)))
            raise ValueError(
                f"Opção inválida para {campo!r}: {valor!r}. "
                f"Use uma destas: {opcoes}."
            )
        resultado[campo] = mapa_normalizado[chave]
    return resultado


def normalizar_experiencia(experiencia: object) -> list[str]:
    """Normaliza, valida e remove a contradição entre produtos e “nenhum”."""
    if isinstance(experiencia, str):
        itens: Iterable[object] = experiencia.split(",")
    elif isinstance(experiencia, Iterable):
        itens = experiencia
    else:
        raise TypeError("experiencia deve ser texto ou coleção de textos.")

    normalizados: set[str] = set()
    desconhecidos: list[str] = []
    for item in itens:
        if not isinstance(item, str):
            raise TypeError("Cada experiência deve ser informada como texto.")
        limpo = item.strip()
        if not limpo:
            continue
        canonico = _EXPERIENCIAS.get(_normalizar_texto(limpo))
        if canonico is None:
            desconhecidos.append(limpo)
        else:
            normalizados.add(canonico)

    if desconhecidos:
        raise ValueError(
            "Experiência desconhecida: " + ", ".join(sorted(desconhecidos))
        )
    if not normalizados:
        normalizados.add("nenhum")
    if "nenhum" in normalizados and len(normalizados) > 1:
        normalizados.remove("nenhum")
    return sorted(
        normalizados,
        key=lambda item: _ORDEM_EXPERIENCIAS[item],
    )


def nome_categoria(categoria: str) -> str:
    """Nome de exibição de uma categoria canônica."""
    return _disp(categoria)


def rotulo_classe_ativo(classe: str) -> str:
    """Nome de exibição de uma classe retornada pelos rankers."""
    return ROTULOS_CLASSES_ATIVOS.get(classe, classe.upper())


def _numero_finito(
    nome: str,
    valor: object,
    *,
    minimo: float | None = None,
    maximo: float | None = None,
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
        raise ValueError(f"{nome} deve ser maior ou igual a {minimo}.")
    if maximo is not None and numero > maximo:
        raise ValueError(f"{nome} deve ser menor ou igual a {maximo}.")
    return numero


def _data_referencia_valida(valor: object | None) -> date:
    """Normaliza a data que torna projeções e regras reproduzíveis."""
    if valor is None:
        return datetime.now(timezone.utc).date()
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, str):
        try:
            return date.fromisoformat(valor.strip())
        except ValueError as exc:
            raise ValueError(
                "data_referencia deve usar o formato AAAA-MM-DD."
            ) from exc
    raise TypeError("data_referencia deve ser datetime.date ou texto ISO.")


def _opcao_tributaria(
    nome: str,
    valor: object,
    permitidas: set[str],
) -> str | None:
    if valor is None:
        return None
    if not isinstance(valor, str):
        raise TypeError(f"{nome} deve ser texto ou None.")
    normalizado = _normalizar_texto(valor)
    if not normalizado or normalizado in {
        "nao informado",
        "nao informada",
        "nenhum",
        "nenhuma",
    }:
        return None
    if normalizado not in permitidas:
        opcoes = ", ".join(sorted(permitidas))
        raise ValueError(f"{nome} deve ser uma destas opções: {opcoes}.")
    return normalizado


def _numero_tributario_opcional(
    nome: str,
    valor: object,
) -> float | None:
    if valor is None or valor == "":
        return None
    return _numero_finito(nome, valor, minimo=0)


def _booleano_tributario_opcional(
    nome: str,
    valor: object,
) -> bool | None:
    if valor is None or valor == "":
        return None
    if not isinstance(valor, bool):
        raise TypeError(f"{nome} deve ser booleano ou None.")
    return valor


def _contexto_fiscal_das_respostas(
    respostas: Mapping[str, Any],
) -> dict[str, Any]:
    metadados_por_categoria = respostas.get(
        "metadados_tributarios_por_categoria",
        {},
    )
    if not isinstance(metadados_por_categoria, Mapping):
        raise TypeError(
            "metadados_tributarios_por_categoria deve ser um mapeamento."
        )
    pessoa_fisica = respostas.get("pessoa_fisica", True)
    if not isinstance(pessoa_fisica, bool):
        raise TypeError("pessoa_fisica deve ser booleano.")
    day_trade = respostas.get("day_trade", False)
    if not isinstance(day_trade, bool):
        raise TypeError("day_trade deve ser booleano.")

    renda_por_ano_bruta = respostas.get("renda_tributavel_por_ano", {})
    if not isinstance(renda_por_ano_bruta, Mapping):
        raise TypeError("renda_tributavel_por_ano deve ser um mapeamento.")
    renda_por_ano: dict[int, float] = {}
    for ano, valor in renda_por_ano_bruta.items():
        if isinstance(ano, bool):
            raise TypeError("As chaves de renda_tributavel_por_ano devem ser anos.")
        try:
            ano_inteiro = int(ano)
        except (TypeError, ValueError) as exc:
            raise TypeError(
                "As chaves de renda_tributavel_por_ano devem ser anos."
            ) from exc
        renda_por_ano[ano_inteiro] = _numero_finito(
            f"renda_tributavel_por_ano[{ano_inteiro}]",
            valor,
            minimo=0.0,
        )

    metadados_normalizados: dict[str, dict] = {}
    for categoria, metadados in metadados_por_categoria.items():
        if not isinstance(metadados, Mapping):
            raise TypeError(
                "Cada item de metadados_tributarios_por_categoria "
                "deve ser um mapeamento."
            )
        metadados_normalizados[str(categoria)] = dict(metadados)

    return {
        "regime_previdencia": _opcao_tributaria(
            "regime_previdencia",
            respostas.get("regime_previdencia"),
            {"progressivo", "regressivo"},
        ),
        "renda_tributavel_anual": _numero_tributario_opcional(
            "renda_tributavel_anual",
            respostas.get("renda_tributavel_anual"),
        ),
        "elegibilidade_deducao_pgbl": _booleano_tributario_opcional(
            "elegibilidade_deducao_pgbl",
            respostas.get("elegibilidade_deducao_pgbl"),
        ),
        "renda_tributavel_por_ano": renda_por_ano,
        "crescimento_renda_tributavel_anual": _numero_finito(
            "crescimento_renda_tributavel_anual",
            respostas.get("crescimento_renda_tributavel_anual", 0.0),
            minimo=-0.999999,
        ),
        "jurisdicao_cripto": _opcao_tributaria(
            "jurisdicao_cripto",
            respostas.get("jurisdicao_cripto"),
            {"brasil", "exterior"},
        ),
        "valor_vendas_mes": _numero_tributario_opcional(
            "valor_vendas_mes",
            respostas.get("valor_vendas_mes"),
        ),
        "valor_aportes_ano": _numero_tributario_opcional(
            "valor_aportes_ano",
            respostas.get("valor_aportes_ano"),
        ),
        "pessoa_fisica": pessoa_fisica,
        "day_trade": day_trade,
        "metadados_por_categoria": metadados_normalizados,
    }


def _pior_precisao(*precisoes: str) -> str:
    validas = [
        precisao
        for precisao in precisoes
        if precisao in _ORDEM_PRECISAO_TRIBUTARIA
    ]
    if not validas:
        return PrecisaoTributaria.INDETERMINADA.value
    return max(
        validas,
        key=_ORDEM_PRECISAO_TRIBUTARIA.__getitem__,
    )


def _textos_unicos(valores: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(str(valor) for valor in valores if valor))


def _fontes_unicas(fontes: Iterable[Mapping[str, Any]]) -> list[dict]:
    unicas: list[dict] = []
    vistos: set[tuple[str, str]] = set()
    for fonte in fontes:
        chave = (
            str(fonte.get("url", "")),
            str(fonte.get("vigencia", "")),
        )
        if chave in vistos:
            continue
        vistos.add(chave)
        unicas.append({"url": chave[0], "vigencia": chave[1]})
    return unicas


def _numero_mercado(
    market: Mapping,
    chave: str,
    *,
    opcional: bool = False,
) -> float | None:
    valor = market.get(chave)
    if valor is None and opcional:
        return None
    if valor is None:
        raise ValueError(f"Dado de mercado obrigatório ausente: {chave}.")
    numero = _numero_finito(f"market[{chave!r}]", valor)
    if not -1 < numero <= 5:
        raise ValueError(
            f"market[{chave!r}] deve ser decimal, por exemplo 0.15 para 15%."
        )
    return numero


def _focus_por_ano(
    market: Mapping,
    *,
    data_referencia: date | None = None,
) -> dict[int, float]:
    bruto = market.get("focus_selic_por_ano")
    resultado: dict[int, float] = {}

    if bruto is not None:
        if not isinstance(bruto, Mapping):
            raise TypeError("focus_selic_por_ano deve ser um mapeamento.")
        for ano_bruto, taxa_bruta in bruto.items():
            try:
                ano = int(ano_bruto)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"Ano Focus inválido: {ano_bruto!r}."
                ) from exc
            taxa = _numero_finito(
                f"Focus SELIC {ano}",
                taxa_bruta,
                minimo=0,
                maximo=1,
            )
            resultado[ano] = taxa

    # Compatibilidade com caches e fixtures que possuam apenas um ponto.
    if not resultado:
        focus_unico = _numero_mercado(
            market,
            "focus_selic",
            opcional=True,
        )
        if focus_unico is not None:
            ano = (data_referencia or datetime.now(timezone.utc).date()).year
            resultado[ano] = float(focus_unico)

    return dict(sorted(resultado.items()))


def _validar_market(
    market: object,
    *,
    data_referencia: date | None = None,
) -> dict[str, Any]:
    if not isinstance(market, Mapping):
        raise TypeError("market deve ser o mapeamento devolvido por mercado.py.")
    return {
        "selic": _numero_mercado(market, "selic"),
        "focus_selic": _numero_mercado(
            market,
            "focus_selic",
            opcional=True,
        ),
        "focus_selic_por_ano": _focus_por_ano(
            market,
            data_referencia=data_referencia,
        ),
        "ipca": _numero_mercado(market, "ipca"),
        "ibov_cagr": _numero_mercado(market, "ibov_cagr"),
    }


def _validar_respostas(respostas: object) -> dict:
    if not isinstance(respostas, Mapping):
        raise TypeError("respostas deve ser um mapeamento.")
    faltantes = sorted(_CAMPOS_RECOMENDACAO - set(respostas))
    if faltantes:
        raise ValueError(
            "Respostas obrigatórias ausentes: " + ", ".join(faltantes)
        )

    preparadas = mapear_respostas_formulario(dict(respostas))
    preparadas["experiencia"] = normalizar_experiencia(
        preparadas["experiencia"]
    )
    liquidez_pct = _numero_finito(
        "liquidez_pct",
        preparadas["liquidez_pct"],
        minimo=0,
        maximo=100,
    )
    preparadas["liquidez_pct"] = (
        liquidez_pct
        if preparadas["liquidez"] == 1
        else 0.0
    )
    preparadas["cap_inicial"] = _numero_finito(
        "cap_inicial",
        preparadas.get("cap_inicial", 0),
        minimo=0,
    )
    for campo_reserva in (
        "despesas_essenciais_mensais",
        "reserva_atual",
    ):
        valor_reserva = preparadas.get(campo_reserva)
        preparadas[campo_reserva] = (
            None
            if valor_reserva is None
            else _numero_finito(
                campo_reserva,
                valor_reserva,
                minimo=0,
            )
        )
    aporte_mensal = _numero_finito(
        "aporte_mensal",
        preparadas.get("aporte_mensal", 0),
        minimo=0,
    )
    preparadas["aporte_mensal"] = (
        aporte_mensal
        if preparadas["aporte"] == 2
        else 0.0
    )

    modo_meta = preparadas.get("modo_meta")
    if modo_meta is not None:
        if isinstance(modo_meta, bool):
            raise TypeError("modo_meta deve ser um inteiro.")
        try:
            modo_meta_inteiro = int(modo_meta)
        except (TypeError, ValueError) as exc:
            raise TypeError("modo_meta deve ser um inteiro.") from exc
        if modo_meta_inteiro != modo_meta or modo_meta_inteiro not in {1, 2, 3}:
            raise ValueError("modo_meta deve ser 1, 2 ou 3.")
        preparadas["modo_meta"] = modo_meta_inteiro

    contexto_fiscal = _contexto_fiscal_das_respostas(preparadas)
    preparadas.update(
        {
            "regime_previdencia": contexto_fiscal[
                "regime_previdencia"
            ],
            "renda_tributavel_anual": contexto_fiscal[
                "renda_tributavel_anual"
            ],
            "elegibilidade_deducao_pgbl": contexto_fiscal[
                "elegibilidade_deducao_pgbl"
            ],
            "renda_tributavel_por_ano": contexto_fiscal[
                "renda_tributavel_por_ano"
            ],
            "crescimento_renda_tributavel_anual": contexto_fiscal[
                "crescimento_renda_tributavel_anual"
            ],
            "jurisdicao_cripto": contexto_fiscal["jurisdicao_cripto"],
            "valor_vendas_mes": contexto_fiscal["valor_vendas_mes"],
            "valor_aportes_ano": contexto_fiscal["valor_aportes_ano"],
            "pessoa_fisica": contexto_fiscal["pessoa_fisica"],
            "day_trade": contexto_fiscal["day_trade"],
            "metadados_tributarios_por_categoria": contexto_fiscal[
                "metadados_por_categoria"
            ],
        }
    )
    return preparadas


def _resolver_meta(
    respostas: Mapping[str, Any],
    meta_valor: float | None,
    meta_prazo: float | None,
) -> tuple[float | None, float | None]:
    """Interpreta o modo de meta sem delegar essa regra às interfaces."""
    recebeu_argumento = meta_valor is not None or meta_prazo is not None
    if recebeu_argumento:
        valores = (meta_valor, meta_prazo)
    else:
        modo_meta = respostas.get("modo_meta")
        if modo_meta in {2, 3}:
            return None, None
        valores = (
            respostas.get("meta_valor"),
            respostas.get("meta_prazo"),
        )
        if modo_meta == 1 and valores == (None, None):
            raise ValueError(
                "Informe meta_valor e meta_prazo para calcular a meta."
            )

    if (valores[0] is None) != (valores[1] is None):
        raise ValueError("meta_valor e meta_prazo devem ser informados juntos.")
    return valores


def projecao_selic_mercado(
    market: Mapping,
    *,
    prazo_meses: int = 12,
    data_referencia: date | str | None = None,
) -> ProjecaoSelic:
    """Projeta a curva SELIC aplicável ao horizonte solicitado."""
    data_base = _data_referencia_valida(data_referencia)
    dados = _validar_market(
        market,
        data_referencia=data_base,
    )
    return projetar_selic(
        selic_atual=float(dados["selic"]),
        focus_por_ano=dados["focus_selic_por_ano"],
        prazo_meses=prazo_meses,
        data_base=data_base,
    )


def taxa_base_mercado(
    market: Mapping,
    *,
    prazo_meses: int = 12,
    data_referencia: date | str | None = None,
) -> float:
    """Retorna a taxa anual equivalente da curva SELIC para o prazo."""
    return projecao_selic_mercado(
        market,
        prazo_meses=prazo_meses,
        data_referencia=data_referencia,
    ).taxa_anual_equivalente


def taxas_por_risco(
    market: Mapping,
    *,
    prazo_meses: int = 12,
    data_referencia: date | str | None = None,
) -> dict[int, float]:
    """Constrói as hipóteses brutas de retorno por nível de risco."""
    data_base = _data_referencia_valida(data_referencia)
    dados = _validar_market(
        market,
        data_referencia=data_base,
    )
    taxa_base = taxa_base_mercado(
        market,
        prazo_meses=prazo_meses,
        data_referencia=data_base,
    )
    ibov = float(dados["ibov_cagr"])
    return {
        1: taxa_base,
        2: (taxa_base + ibov) / 2.0,
        3: ibov,
    }


def resumo_taxas_mercado(
    market: Mapping,
    *,
    prazo_meses: int = 12,
    data_referencia: date | str | None = None,
) -> dict[str, Any]:
    """Resumo validado dos indicadores e hipóteses exibidos pelas interfaces."""
    data_base = _data_referencia_valida(data_referencia)
    dados = _validar_market(
        market,
        data_referencia=data_base,
    )
    projecao = projecao_selic_mercado(
        market,
        prazo_meses=prazo_meses,
        data_referencia=data_base,
    )
    taxas = taxas_por_risco(
        market,
        prazo_meses=prazo_meses,
        data_referencia=data_base,
    )
    ipca = float(dados["ipca"])
    perfis = []
    for nivel in (1, 2, 3):
        bruta = taxas[nivel]
        real_bruta = (1.0 + bruta) / (1.0 + ipca) - 1.0
        perfis.append(
            {
                "nivel": nivel,
                "rotulo": RISCO_LABEL[nivel],
                "taxa_bruta": bruta,
                "taxa_real_bruta": real_bruta,
            }
        )
    return {
        **dados,
        "taxa_base": projecao.taxa_anual_equivalente,
        "metodo_taxa_base": "curva_selic_focus_composta",
        "prazo_taxa_meses": prazo_meses,
        "meses_extrapolados": projecao.meses_extrapolados,
        "avisos_curva_selic": list(projecao.avisos),
        "taxas": taxas,
        "perfis": perfis,
    }


def _portfolio_positivo(
    portfolio: Mapping[str, int | float],
) -> dict[str, float]:
    if not isinstance(portfolio, Mapping):
        raise TypeError("portfolio deve ser um mapeamento.")
    positivos: dict[str, float] = {}
    for categoria, percentual in portfolio.items():
        numero = _numero_finito(
            f"percentual de {categoria!r}",
            percentual,
            minimo=0,
        )
        if numero > 0:
            positivos[categoria] = numero
    if not positivos:
        raise ValueError("O portfólio não possui alocação positiva.")
    return positivos


def _taxa_ponderada(
    portfolio: Mapping[str, int | float],
    taxas: Mapping[int, float],
) -> float:
    positivos = _portfolio_positivo(portfolio)
    total = sum(positivos.values())
    return sum(
        percentual * float(taxas[_risco(categoria)])
        for categoria, percentual in positivos.items()
    ) / total


def _taxa_pessimista(taxa_central: float, ipca: float) -> float:
    candidato = max(ipca + 0.02, taxa_central * 0.60)
    return min(taxa_central, candidato)


def projetar_portfolio(
    cap_inicial: float,
    aporte_mensal: float,
    portfolio: Mapping[str, int | float],
    taxas: Mapping[int, float],
    ipca: float,
    anos: float,
    *,
    taxa_unica: float | None = None,
    data_referencia: date | str | None = None,
    contexto_fiscal: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Projeta e tributa cada classe sem substituir dados fiscais ausentes."""
    positivos = _portfolio_positivo(portfolio)
    total = sum(positivos.values())
    data_base = _data_referencia_valida(data_referencia)
    capital = _numero_finito("cap_inicial", cap_inicial, minimo=0)
    aporte = _numero_finito("aporte_mensal", aporte_mensal, minimo=0)
    inflacao = _numero_finito("ipca", ipca)
    prazo = _numero_finito("anos", anos, minimo=0)
    if inflacao <= -1:
        raise ValueError("ipca deve ser maior que -100%.")
    if contexto_fiscal is None:
        fiscal: dict[str, Any] = {}
    elif isinstance(contexto_fiscal, Mapping):
        fiscal = dict(contexto_fiscal)
    else:
        raise TypeError("contexto_fiscal deve ser um mapeamento ou None.")

    metadados_por_categoria = fiscal.get("metadados_por_categoria", {})
    if not isinstance(metadados_por_categoria, Mapping):
        raise TypeError("metadados_por_categoria deve ser um mapeamento.")

    tributacao_por_classe: dict[str, dict[str, Any]] = {}

    for categoria, percentual in positivos.items():
        peso = percentual / total
        taxa = (
            _numero_finito("taxa_unica", taxa_unica)
            if taxa_unica is not None
            else _numero_finito(
                f"taxa do risco {_risco(categoria)}",
                taxas[_risco(categoria)],
            )
        )
        tratamento = _tipo_tributario(categoria)
        capital_classe = capital * peso
        aporte_classe = aporte * peso
        metadados = dict(metadados_por_categoria.get(categoria, {}))
        if (
            tratamento.tipo_produto == "cripto"
            and fiscal.get("jurisdicao_cripto") is not None
        ):
            metadados.setdefault(
                "jurisdicao_custodia",
                fiscal["jurisdicao_cripto"],
            )

        calculo = _vf_liquido_tributado(
            capital_classe,
            aporte_classe,
            taxa,
            prazo,
            tratamento.tipo_produto,
            data_referencia=data_base,
            regime=fiscal.get("regime_previdencia"),
            renda_tributavel=fiscal.get("renda_tributavel_anual"),
            valor_vendas_mes=fiscal.get("valor_vendas_mes"),
            valor_aportes_ano=fiscal.get("valor_aportes_ano"),
            day_trade=fiscal.get("day_trade", False),
            pessoa_fisica=fiscal.get("pessoa_fisica", True),
            metadados=metadados,
        )
        calculo["precisao"] = _pior_precisao(
            calculo["precisao"],
            tratamento.precisao_maxima.value,
        )
        calculo["premissas"] = _textos_unicos(
            (*tratamento.premissas, *calculo["premissas"])
        )
        calculo.update(
            {
                "categoria": categoria,
                "nome": _disp(categoria),
                "percentual": percentual,
                "peso_normalizado": peso,
            }
        )
        tributacao_por_classe[categoria] = calculo

    classes = list(tributacao_por_classe.values())
    todas_determinadas = all(
        classe["liquido"] is not None for classe in classes
    )
    bruto = sum(float(classe["bruto"]) for classe in classes)
    imposto_parcial = sum(
        float(classe["imposto_calculado_parcial"])
        for classe in classes
    )
    liquido_parcial = sum(
        float(classe["liquido_calculado_parcial"])
        for classe in classes
    )
    bruto_indeterminado = sum(
        float(classe["bruto_indeterminado"])
        for classe in classes
    )
    liquido = liquido_parcial if todas_determinadas else None
    imposto = imposto_parcial if todas_determinadas else None
    precisao = _pior_precisao(
        *(str(classe["precisao"]) for classe in classes)
    )

    return {
        "bruto": bruto,
        "liquido": liquido,
        "real": (
            _vf_real(liquido, inflacao, prazo)
            if liquido is not None
            else None
        ),
        "imposto_estimado": imposto,
        "imposto_calculado_parcial": imposto_parcial,
        "liquido_calculado_parcial": liquido_parcial,
        "real_calculado_parcial": _vf_real(
            liquido_parcial,
            inflacao,
            prazo,
        ),
        "bruto_indeterminado": bruto_indeterminado,
        "precisao_tributaria": precisao,
        "premissas_tributarias": _textos_unicos(
            premissa
            for classe in classes
            for premissa in classe["premissas"]
        ),
        "fontes_tributarias": _fontes_unicas(
            fonte
            for classe in classes
            for fonte in classe["fontes"]
        ),
        "regras_tributarias": _textos_unicos(
            regra
            for classe in classes
            for regra in classe["regras"]
        ),
        "tributacao_por_classe": tributacao_por_classe,
        "data_referencia": data_base.isoformat(),
    }


def aporte_necessario_para_meta(
    meta_valor: float,
    meta_prazo: float,
    cap_inicial: float,
    portfolio: Mapping[str, int | float],
    taxas: Mapping[int, float],
    ipca: float,
    *,
    data_referencia: date | str | None = None,
    contexto_fiscal: Mapping[str, Any] | None = None,
) -> float | None:
    """Resolve por busca binária o aporte para atingir uma meta líquida."""
    meta = _numero_finito("meta_valor", meta_valor, minimo=0.01)
    prazo = _numero_finito("meta_prazo", meta_prazo, minimo=1, maximo=100)

    sem_aporte = projetar_portfolio(
        cap_inicial,
        0,
        portfolio,
        taxas,
        ipca,
        prazo,
        data_referencia=data_referencia,
        contexto_fiscal=contexto_fiscal,
    )["liquido"]
    if sem_aporte is None:
        return None
    if sem_aporte >= meta:
        return 0.0

    inferior = 0.0
    superior = max(100.0, meta / (prazo * 12.0))
    for _ in range(30):
        valor = projetar_portfolio(
            cap_inicial,
            superior,
            portfolio,
            taxas,
            ipca,
            prazo,
            data_referencia=data_referencia,
            contexto_fiscal=contexto_fiscal,
        )["liquido"]
        if valor is None:
            return None
        if valor >= meta:
            break
        superior *= 2.0
    else:
        return None

    for _ in range(60):
        meio = (inferior + superior) / 2.0
        valor = projetar_portfolio(
            cap_inicial,
            meio,
            portfolio,
            taxas,
            ipca,
            prazo,
            data_referencia=data_referencia,
            contexto_fiscal=contexto_fiscal,
        )["liquido"]
        if valor is None:
            return None
        if valor >= meta:
            superior = meio
        else:
            inferior = meio
    return superior


def _descricao_reserva(
    respostas: Mapping[str, Any],
    resultado: Mapping[str, Any],
) -> str:
    plano = resultado.get("plano_reserva")
    if not isinstance(plano, Mapping):
        return {
            1: "Sem reserva",
            2: "Parcial",
            3: "Completa",
        }[respostas["reserva_emerg"]]
    alvo = float(plano["valor_alvo"])
    deficit = float(plano["deficit"])
    atual = float(plano["valor_atual"])
    meses = int(plano["meses"])
    if alvo == 0:
        return (
            "Reserva-alvo calculada: R$ 0,00 "
            "(despesas essenciais mensais informadas como zero)"
        )
    if deficit == 0:
        return (
            f"Reserva-alvo de R$ {alvo:,.2f} coberta; "
            f"valor atual R$ {atual:,.2f}"
        )
    return (
        f"Déficit de R$ {deficit:,.2f} para a reserva-alvo de "
        f"R$ {alvo:,.2f} ({meses} meses)"
    )


def _perfil_resumo(
    respostas: Mapping[str, Any],
    resultado: Mapping[str, Any],
    meta: Mapping[str, Any] | None,
) -> dict[str, str]:
    resumo = {
        "Prazo": {
            1: "Curto (até 2 anos)",
            2: "Médio (2–5 anos)",
            3: "Longo (acima de 5 anos)",
        }[respostas["prazo"]],
        "Risco declarado": {
            1: "Baixo",
            2: "Médio",
            3: "Alto",
        }[respostas["risco"]],
        "Risco emocional": RISCO_LABEL[respostas["emocional"]],
        "Risco efetivo": resultado["nivel_risco_display"],
        "Objetivo": {
            1: "Reserva",
            2: "Crescimento",
            3: "Aposentadoria",
        }[respostas["objetivo"]],
        "Fluxo": {
            1: "Renda periódica",
            2: "Acúmulo",
        }[respostas["fluxo"]],
        "Controle": {
            1: "Gestão própria",
            2: "Delegar",
        }[respostas["controle"]],
        "Liquidez": (
            f"Sim — {respostas['liquidez_pct']:.0f}%"
            if respostas["liquidez"] == 1
            else "Não"
        ),
        "Reserva de emergência": _descricao_reserva(
            respostas,
            resultado,
        ),
        "Idade": {
            1: "Jovem (até 35)",
            2: "Adulto (36–55)",
            3: "Sênior (acima de 55)",
        }[respostas["idade"]],
        "Despesas fixas": {
            1: "Nenhuma",
            2: "Baixas",
            3: "Altas",
        }[respostas["despesas"]],
        "Despesas essenciais mensais": (
            "Não informado"
            if respostas.get("despesas_essenciais_mensais") is None
            else f"R$ {respostas['despesas_essenciais_mensais']:,.2f}"
        ),
        "Reserva disponível hoje": (
            "Não informado"
            if respostas.get("reserva_atual") is None
            else f"R$ {respostas['reserva_atual']:,.2f}"
        ),
        "Valor disponível": {
            1: "Até R$ 1 mil",
            2: "R$ 1–10 mil",
            3: "Acima de R$ 10 mil",
        }[respostas["faixa_valor"]],
        "Parcela do patrimônio": {
            1: "Abaixo de 25%",
            2: "25–75%",
            3: "Acima de 75%",
        }[respostas["patrim_pct"]],
        "Renda": {
            1: "CLT",
            2: "PJ contratado",
            3: "Autônomo",
            4: "Sem renda",
        }[respostas["renda"]],
        "Dívidas": {
            1: "Juros altos",
            2: "Juros baixos",
            3: "Sem dívidas",
        }[respostas["dividas"]],
        "Conhecimento declarado": {
            1: "Iniciante",
            2: "Intermediário",
            3: "Experiente",
        }[respostas["conhecimento"]],
        "Conhecimento ajustado": {
            1: "Iniciante",
            2: "Intermediário",
            3: "Experiente",
        }[resultado["conhecimento_ajustado"]],
        "Experiência": ", ".join(respostas["experiencia"]),
        "Dependentes": {
            1: "Nenhum",
            2: "Um",
            3: "Dois ou mais",
        }[respostas["dependentes"]],
        "Aporte": {
            1: "Único",
            2: "Mensal",
        }[respostas["aporte"]],
        "Declaração de IR": {
            1: "Completa",
            2: "Simplificada",
            3: "Não declara",
        }[respostas["ir_tipo"]],
        "Carteira atual": {
            1: "Sem carteira",
            2: "Conservadora",
            3: "Moderada",
            4: "Arrojada",
        }[respostas["carteira_atual"]],
        "Capital inicial": f"R$ {respostas['cap_inicial']:,.2f}",
        "Aporte mensal": f"R$ {respostas['aporte_mensal']:,.2f}",
        "Recomendação principal": resultado["recomendacao_display"],
    }
    if meta is not None:
        resumo["Meta financeira"] = (
            f"R$ {meta['valor_alvo']:,.2f} "
            f"em {meta['prazo_anos']:g} ano(s)"
        )
    return resumo


_PREVIDENCIA_PGBL = {RK.PREV_PGBL, RK.PREV_PGBL_RF}
_PREVIDENCIA_VGBL = {RK.PREV_VGBL, RK.PREV_VGBL_RF}
_PREVIDENCIA_TODAS = _PREVIDENCIA_PGBL | _PREVIDENCIA_VGBL


def _alocar_deficit_reserva(
    rec_key: str,
    portfolio_base: dict[str, float],
    respostas: Mapping[str, Any],
    meses_reserva: int,
    avisos: list[str],
) -> tuple[str, dict[str, float], dict[str, Any]]:
    """Separa somente o déficit mensurável da reserva de emergência."""
    despesas = respostas.get("despesas_essenciais_mensais")
    reserva_atual = respostas.get("reserva_atual")
    capital = float(respostas["cap_inicial"])

    if despesas is None or reserva_atual is None:
        plano = {
            "valor_alvo": 0.0,
            "valor_atual": 0.0,
            "deficit": capital,
            "percentual_capital": 100.0,
            "meses": meses_reserva,
            "precisao": "indeterminada",
        }
        if rec_key == RK.RF_RESERVA:
            return rec_key, {RK.RF_RESERVA: 100.0}, plano
        return rec_key, portfolio_base, plano

    valor_alvo = float(despesas) * meses_reserva
    deficit = max(0.0, valor_alvo - float(reserva_atual))
    plano = {
        "valor_alvo": valor_alvo,
        "valor_atual": float(reserva_atual),
        "deficit": deficit,
        "percentual_capital": 0.0,
        "meses": meses_reserva,
        "precisao": "calculada",
    }
    if rec_key != RK.RF_RESERVA:
        return rec_key, portfolio_base, plano

    if deficit <= 0:
        avisos[:] = [
            aviso
            for aviso in avisos
            if "Priorize uma reserva" not in aviso
        ]
        avisos.append(
            "ℹ️ Reserva-alvo calculada: R$ 0,00; nenhuma parcela do novo "
            "capital foi direcionada compulsoriamente à reserva."
            if valor_alvo == 0
            else "ℹ️ A reserva-alvo calculada já está coberta; o capital "
            "novo pode seguir a alocação compatível com o perfil."
        )
        categoria_base, _ = _classificar_portfolio_final(portfolio_base)
        return categoria_base, portfolio_base, plano

    if capital <= 0 or deficit >= capital:
        plano["percentual_capital"] = 100.0
        avisos.append(
            "⚠️ Todo o capital inicial é necessário para reduzir o déficit "
            "da reserva antes da diversificação."
        )
        return rec_key, {RK.RF_RESERVA: 100.0}, plano

    percentual_reserva = 100.0 * deficit / capital
    percentual_excedente = 100.0 - percentual_reserva
    portfolio = {
        categoria: float(percentual) * percentual_excedente / 100.0
        for categoria, percentual in portfolio_base.items()
        if percentual > 0
    }
    portfolio[RK.RF_RESERVA] = (
        portfolio.get(RK.RF_RESERVA, 0.0) + percentual_reserva
    )
    diferenca = 100.0 - sum(portfolio.values())
    portfolio[RK.RF_RESERVA] += diferenca
    plano["percentual_capital"] = percentual_reserva
    avisos.append(
        "ℹ️ Somente o déficit calculado da reserva foi separado; o capital "
        "excedente permaneceu diversificado conforme o perfil."
    )
    return rec_key, portfolio, plano


def _categoria_previdencia_equivalente(
    categoria_atual: str,
    produto: str,
) -> str:
    renda_fixa = categoria_atual in {RK.PREV_PGBL_RF, RK.PREV_VGBL_RF}
    if produto == "pgbl":
        return RK.PREV_PGBL_RF if renda_fixa else RK.PREV_PGBL
    if produto == "vgbl":
        return RK.PREV_VGBL_RF if renda_fixa else RK.PREV_VGBL
    raise ValueError("produto deve ser pgbl ou vgbl.")


def _prazo_comparacao_previdencia(
    respostas: Mapping[str, Any],
    prazo_taxa_meses: int,
) -> float:
    meta_prazo = respostas.get("meta_prazo")
    if respostas.get("modo_meta") == 1 and meta_prazo is not None:
        try:
            prazo = float(meta_prazo)
        except (TypeError, ValueError):
            prazo = 0.0
        if math.isfinite(prazo) and prazo > 0:
            return prazo
    return prazo_taxa_meses / 12.0


def _ajustar_previdencia_por_eficiencia(
    rec_key: str,
    portfolio: dict[str, float],
    respostas: Mapping[str, Any],
    contexto_fiscal: Mapping[str, Any],
    taxas: Mapping[int, float],
    prazo_taxa_meses: int,
    data_base: date,
    avisos: list[str],
) -> tuple[str, dict[str, float], dict[str, Any] | None]:
    categoria_atual = next(
        (
            categoria
            for categoria, percentual in portfolio.items()
            if categoria in _PREVIDENCIA_TODAS and percentual > 0
        ),
        None,
    )
    if categoria_atual is None:
        return rec_key, portfolio, None

    percentual = float(portfolio[categoria_atual])
    peso = percentual / 100.0
    prazo = _prazo_comparacao_previdencia(
        respostas,
        prazo_taxa_meses,
    )
    metadados_por_categoria = contexto_fiscal.get(
        "metadados_por_categoria",
        {},
    )
    metadados_pgbl = dict(
        metadados_por_categoria.get(categoria_atual, {})
        if isinstance(metadados_por_categoria, Mapping)
        else {}
    )
    if metadados_pgbl.get("lotes_previdencia_existentes"):
        return rec_key, portfolio, {
            "aplicado": False,
            "produto_escolhido": None,
            "categoria_original": categoria_atual,
            "categoria_escolhida": categoria_atual,
            "percentual_previdencia": percentual,
            "prazo_anos": prazo,
            "motivo": (
                "Lotes previdenciários existentes foram informados. O motor "
                "não converte automaticamente PGBL em VGBL ou VGBL em PGBL; "
                "a comparação deve ser aplicada apenas a novos aportes."
            ),
        }
    comparacao = comparar_pgbl_vgbl(
        float(respostas["cap_inicial"]) * peso,
        float(respostas["aporte_mensal"]) * peso,
        float(taxas[_risco(categoria_atual)]),
        prazo,
        data_referencia=data_base,
        regime=contexto_fiscal.get("regime_previdencia"),
        renda_tributavel_anual=contexto_fiscal.get(
            "renda_tributavel_anual"
        ),
        declaracao_completa=respostas["ir_tipo"] == 1,
        elegibilidade_deducao_pgbl=contexto_fiscal.get(
            "elegibilidade_deducao_pgbl"
        ),
        deducao_ja_utilizada_primeiro_ano=float(
            contexto_fiscal.get("valor_aportes_ano") or 0.0
        ),
        metadados_pgbl=metadados_pgbl,
        renda_tributavel_por_ano=contexto_fiscal.get(
            "renda_tributavel_por_ano"
        ),
        crescimento_renda_anual=float(
            contexto_fiscal.get("crescimento_renda_tributavel_anual")
            or 0.0
        ),
    )

    anos_extrapolados = comparacao.get(
        "anos_regra_tributaria_extrapolada",
        [],
    )
    if anos_extrapolados:
        avisos.append(
            "⚠️ A regra tributária de 2026 foi usada apenas como cenário "
            "nos anos futuros: "
            + ", ".join(str(ano) for ano in anos_extrapolados)
            + "."
        )

    escolhido = comparacao.get("produto_escolhido")
    if not comparacao.get("aplicado"):
        if contexto_fiscal.get("elegibilidade_deducao_pgbl") is not True:
            escolhido = "vgbl"
            comparacao["produto_escolhido"] = escolhido
            comparacao["escolha_conservadora"] = True
            comparacao["motivo_escolha_conservadora"] = (
                "Sem benefício fiscal do PGBL confirmado, o motor não o "
                "considera na escolha automática."
            )
        else:
            avisos.append(
                "⚠️ PGBL e VGBL não puderam ser comparados integralmente: "
                + str(comparacao.get("motivo", "dados insuficientes"))
            )
            return rec_key, portfolio, comparacao

    nova_categoria = _categoria_previdencia_equivalente(
        categoria_atual,
        str(escolhido),
    )
    portfolio_ajustado = dict(portfolio)
    if nova_categoria != categoria_atual:
        valor = portfolio_ajustado.pop(categoria_atual)
        portfolio_ajustado[nova_categoria] = (
            float(portfolio_ajustado.get(nova_categoria, 0.0)) + float(valor)
        )
    if rec_key in _PREVIDENCIA_TODAS:
        rec_key = _categoria_previdencia_equivalente(rec_key, str(escolhido))

    if comparacao.get("aplicado"):
        avisos.append(
            "ℹ️ Previdência escolhida por eficiência líquida comparável: "
            f"{str(escolhido).upper()}."
        )
    else:
        avisos.append(
            "ℹ️ VGBL mantido como escolha conservadora porque o benefício "
            "fiscal do PGBL não foi confirmado."
        )
    comparacao["categoria_original"] = categoria_atual
    comparacao["categoria_escolhida"] = nova_categoria
    comparacao["percentual_previdencia"] = percentual
    comparacao["prazo_anos"] = prazo
    return rec_key, portfolio_ajustado, comparacao


def gerar_recomendacao_completa(
    respostas: dict,
    market: dict,
    *,
    data_referencia: date | str | None = None,
) -> dict:
    """Executa perfil, recomendação, carteira, catálogo e hipóteses de taxa."""
    respostas_validas = _validar_respostas(respostas)
    contexto_fiscal = _contexto_fiscal_das_respostas(respostas_validas)
    data_base = _data_referencia_valida(data_referencia)
    dados_mercado = _validar_market(
        market,
        data_referencia=data_base,
    )
    prazo_taxa_meses = _PRAZO_REFERENCIA_MESES[
        respostas_validas["prazo"]
    ]
    projecao_selic_base = projecao_selic_mercado(
        market,
        prazo_meses=prazo_taxa_meses,
        data_referencia=data_base,
    )
    taxas = taxas_por_risco(
        market,
        prazo_meses=prazo_taxa_meses,
        data_referencia=data_base,
    )
    ipca = float(dados_mercado["ipca"])

    (
        rec_key,
        nivel_risco_perfil,
        meses_res,
        avisos,
        conhecimento_ajustado,
    ) = calcular_recomendacao(
        prazo=respostas_validas["prazo"],
        risco=respostas_validas["risco"],
        objetivo=respostas_validas["objetivo"],
        fluxo=respostas_validas["fluxo"],
        controle=respostas_validas["controle"],
        liquidez=respostas_validas["liquidez"],
        liquidez_pct=respostas_validas["liquidez_pct"],
        reserva_emerg=respostas_validas["reserva_emerg"],
        idade=respostas_validas["idade"],
        despesas=respostas_validas["despesas"],
        faixa_valor=respostas_validas["faixa_valor"],
        patrim_pct=respostas_validas["patrim_pct"],
        renda=respostas_validas["renda"],
        dividas=respostas_validas["dividas"],
        conhecimento=respostas_validas["conhecimento"],
        experiencia=respostas_validas["experiencia"],
        dependentes=respostas_validas["dependentes"],
        aporte=respostas_validas["aporte"],
        emocional=respostas_validas["emocional"],
        ir_tipo=respostas_validas["ir_tipo"],
        carteira_atual=respostas_validas["carteira_atual"],
        TAXAS=taxas,
    )
    avisos.extend(
        aviso
        for aviso in projecao_selic_base.avisos
        if aviso not in avisos
    )

    portfolio = _build_portfolio(
        nivel_risco_perfil,
        conhecimento_ajustado,
        respostas_validas["faixa_valor"],
        respostas_validas["objetivo"],
        respostas_validas["renda"],
        respostas_validas["dividas"],
        respostas_validas["dependentes"],
        respostas_validas["aporte"],
        respostas_validas["carteira_atual"],
        respostas_validas["ir_tipo"],
        respostas_validas["fluxo"],
        respostas_validas["patrim_pct"],
        respostas_validas["liquidez_pct"],
        respostas_validas["despesas"],
        respostas_validas["idade"],
        avisos,
    )
    rec_key, portfolio, plano_reserva = _alocar_deficit_reserva(
        rec_key,
        portfolio,
        respostas_validas,
        meses_res,
        avisos,
    )
    rec_key, portfolio, ranking_previdencia = (
        _ajustar_previdencia_por_eficiencia(
            rec_key,
            portfolio,
            respostas_validas,
            contexto_fiscal,
            taxas,
            prazo_taxa_meses,
            data_base,
            avisos,
        )
    )
    perfil_exibido, risco_recomendado = _classificar_portfolio_final(
        portfolio
    )
    info_principal = _get_prod(rec_key)
    info_carteira = _get_prod(perfil_exibido)
    tratamento_representativo = _tipo_tributario(perfil_exibido)
    taxa_perfil = _taxa_ponderada(portfolio, taxas)
    taxa_pess = _taxa_pessimista(taxa_perfil, ipca)

    portfolio_busca = dict(portfolio)
    if rec_key in _CLASSE and rec_key not in portfolio_busca:
        portfolio_busca[rec_key] = MIN_PCT
    classes_no_portfolio = {
        _CLASSE[categoria]
        for categoria, percentual in portfolio_busca.items()
        if percentual >= MIN_PCT and categoria in _CLASSE
    }
    portfolio_itens = [
        {
            "categoria": categoria,
            "nome": _disp(categoria),
            "percentual": percentual,
        }
        for categoria, percentual in portfolio.items()
        if percentual > 0
    ]

    return {
        "rec_key": rec_key,
        "recomendacao_principal": rec_key,
        "recomendacao_display": _disp(rec_key),
        "perfil_exibido": perfil_exibido,
        "perfil_display": _disp(perfil_exibido),
        "portfolio": portfolio,
        "portfolio_itens": portfolio_itens,
        "portfolio_busca": portfolio_busca,
        "nivel_risco_perfil": nivel_risco_perfil,
        "nivel_risco_display": RISCO_LABEL[nivel_risco_perfil],
        "risco_recomendado": risco_recomendado,
        "risco_recomendado_display": RISCO_LABEL[risco_recomendado],
        "info": info_carteira,
        "info_principal": info_principal,
        "info_carteira": info_carteira,
        "tratamento_tributario_representativo": (
            tratamento_representativo.como_dict()
        ),
        "contexto_fiscal": contexto_fiscal,
        "ranking_previdencia_liquida": ranking_previdencia,
        "plano_reserva": plano_reserva,
        "taxa_base": projecao_selic_base.taxa_anual_equivalente,
        "metodo_taxa_base": "curva_selic_focus_composta",
        "prazo_taxa_meses": prazo_taxa_meses,
        "meses_extrapolados_selic": (
            projecao_selic_base.meses_extrapolados
        ),
        "taxa_perfil": taxa_perfil,
        "taxa_pess": taxa_pess,
        "avisos": avisos,
        "meses_res": meses_res,
        "conhecimento_ajustado": conhecimento_ajustado,
        "classes_no_portfolio": classes_no_portfolio,
        "classes_display": {
            classe: rotulo_classe_ativo(classe)
            for classe in classes_no_portfolio
        },
        "TAXAS": taxas,
        "respostas_normalizadas": respostas_validas,
    }


def tabela_projecao(
    cap_inicial: float,
    aporte_mensal: float,
    taxa_perfil: float,
    taxa_pess: float,
    ipca: float,
    aliq: float,
    pgbl: bool,
    anos_lista=(1, 2, 5, 10, 20, 30),
) -> list[dict]:
    """Compatibilidade com a projeção antiga de uma única classe."""
    linhas: list[dict] = []
    for anos in anos_lista:
        bruto = _vf_bruto(
            cap_inicial,
            aporte_mensal,
            taxa_perfil,
            anos,
        )
        liquido = _vf_liquido(
            cap_inicial,
            aporte_mensal,
            taxa_perfil,
            anos,
            aliq,
            pgbl,
        )
        pessimista = _vf_liquido(
            cap_inicial,
            aporte_mensal,
            min(taxa_perfil, taxa_pess),
            anos,
            aliq,
            pgbl,
        )
        linhas.append(
            {
                "anos": anos,
                "vf_bruto": bruto,
                "vf_liquido": liquido,
                "vf_real": _vf_real(liquido, ipca, anos),
                "vf_pessimista": pessimista,
                "vf_pessimista_liquido": pessimista,
            }
        )
    return linhas


def tabela_projecao_portfolio(
    cap_inicial: float,
    aporte_mensal: float,
    portfolio: Mapping[str, int | float],
    taxas: Mapping[int, float],
    taxa_pess: float,
    ipca: float,
    anos_lista: Sequence[float] = ANOS_PROJECAO_PADRAO,
    *,
    data_referencia: date | str | None = None,
    contexto_fiscal: Mapping[str, Any] | None = None,
    market: Mapping[str, Any] | None = None,
) -> list[dict]:
    """Projeção da carteira, com retorno e imposto próprios de cada classe."""
    linhas: list[dict] = []
    data_base = _data_referencia_valida(data_referencia)
    for anos in anos_lista:
        prazo_meses = max(1, round(float(anos) * 12))
        projecao_selic_horizonte: ProjecaoSelic | None = None

        if market is not None:
            taxas_horizonte = taxas_por_risco(
                market,
                prazo_meses=prazo_meses,
                data_referencia=data_base,
            )
            projecao_selic_horizonte = projecao_selic_mercado(
                market,
                prazo_meses=prazo_meses,
                data_referencia=data_base,
            )
            taxa_central = _taxa_ponderada(
                portfolio,
                taxas_horizonte,
            )
            pessimismo = _taxa_pessimista(taxa_central, ipca)
        else:
            taxas_horizonte = taxas
            taxa_central = _taxa_ponderada(portfolio, taxas_horizonte)
            pessimismo = min(float(taxa_pess), taxa_central)

        central = projetar_portfolio(
            cap_inicial,
            aporte_mensal,
            portfolio,
            taxas_horizonte,
            ipca,
            anos,
            data_referencia=data_base,
            contexto_fiscal=contexto_fiscal,
        )
        pessimista = projetar_portfolio(
            cap_inicial,
            aporte_mensal,
            portfolio,
            taxas_horizonte,
            ipca,
            anos,
            taxa_unica=pessimismo,
            data_referencia=data_base,
            contexto_fiscal=contexto_fiscal,
        )
        linhas.append(
            {
                "anos": anos,
                "prazo_taxa_meses": prazo_meses,
                "taxa_base_horizonte": (
                    projecao_selic_horizonte.taxa_anual_equivalente
                    if projecao_selic_horizonte is not None
                    else None
                ),
                "taxa_carteira_horizonte": taxa_central,
                "meses_extrapolados_selic": (
                    projecao_selic_horizonte.meses_extrapolados
                    if projecao_selic_horizonte is not None
                    else None
                ),
                "vf_bruto": central["bruto"],
                "vf_liquido": central["liquido"],
                "vf_real": central["real"],
                "vf_pessimista": pessimista["liquido"],
                "vf_pessimista_liquido": pessimista["liquido"],
                "imposto_estimado": central["imposto_estimado"],
                "imposto_calculado_parcial": central[
                    "imposto_calculado_parcial"
                ],
                "vf_liquido_calculado_parcial": central[
                    "liquido_calculado_parcial"
                ],
                "vf_real_calculado_parcial": central[
                    "real_calculado_parcial"
                ],
                "bruto_indeterminado": central[
                    "bruto_indeterminado"
                ],
                "precisao_tributaria": central[
                    "precisao_tributaria"
                ],
                "premissas_tributarias": central[
                    "premissas_tributarias"
                ],
                "fontes_tributarias": central["fontes_tributarias"],
                "regras_tributarias": central["regras_tributarias"],
                "tributacao_por_classe": central[
                    "tributacao_por_classe"
                ],
                "data_referencia": central["data_referencia"],
                "pessimista_precisao_tributaria": pessimista[
                    "precisao_tributaria"
                ],
            }
        )
    return linhas


def analisar_meta(
    meta_valor: float,
    meta_prazo: float,
    cap_inicial: float,
    aporte_mensal: float,
    portfolio: Mapping[str, int | float],
    taxas: Mapping[int, float],
    ipca: float,
    *,
    data_referencia: date | str | None = None,
    contexto_fiscal: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Calcula o resultado da meta e o aporte mensal total necessário."""
    meta = _numero_finito("meta_valor", meta_valor, minimo=0.01)
    prazo = _numero_finito("meta_prazo", meta_prazo, minimo=1, maximo=100)
    projecao = projetar_portfolio(
        cap_inicial,
        aporte_mensal,
        portfolio,
        taxas,
        ipca,
        prazo,
        data_referencia=data_referencia,
        contexto_fiscal=contexto_fiscal,
    )
    valor_projetado = projecao["liquido"]
    if valor_projetado is None:
        return {
            "valor_alvo": meta,
            "prazo_anos": prazo,
            "valor_liquido_projetado": None,
            "atingida": None,
            "diferenca": None,
            "aporte_mensal_informado": aporte_mensal,
            "aporte_mensal_estimado": None,
            "precisao_tributaria": projecao["precisao_tributaria"],
            "motivo_indeterminacao": (
                "A meta líquida não pode ser avaliada enquanto houver "
                "tributação indeterminada em alguma classe."
            ),
        }

    diferenca = valor_projetado - meta
    aporte_necessario = aporte_necessario_para_meta(
        meta,
        prazo,
        cap_inicial,
        portfolio,
        taxas,
        ipca,
        data_referencia=data_referencia,
        contexto_fiscal=contexto_fiscal,
    )
    return {
        "valor_alvo": meta,
        "prazo_anos": prazo,
        "valor_liquido_projetado": valor_projetado,
        "atingida": diferenca >= 0,
        "diferenca": diferenca,
        "aporte_mensal_informado": aporte_mensal,
        "aporte_mensal_estimado": aporte_necessario,
        "precisao_tributaria": projecao["precisao_tributaria"],
        "motivo_indeterminacao": None,
    }


def criar_analise(
    respostas: dict,
    market: dict,
    meta_valor: float | None = None,
    meta_prazo: float | None = None,
    *,
    data_referencia: date | str | None = None,
    anos_projecao: Sequence[float] = ANOS_PROJECAO_PADRAO,
    anos_grafico: Sequence[float] = ANOS_GRAFICO_PADRAO,
) -> dict[str, Any]:
    """
    Operação única: questionário → recomendação → projeções → meta.

    As interfaces devem chamar esta função e apenas renderizar o retorno.
    """
    data_base = _data_referencia_valida(data_referencia)
    resultado = gerar_recomendacao_completa(
        respostas,
        market,
        data_referencia=data_base,
    )
    respostas_validas = dict(resultado["respostas_normalizadas"])
    contexto_fiscal = dict(resultado["contexto_fiscal"])
    dados_mercado = _validar_market(
        market,
        data_referencia=data_base,
    )
    ipca = float(dados_mercado["ipca"])

    valores_meta = _resolver_meta(
        respostas_validas,
        meta_valor,
        meta_prazo,
    )

    anos_unicos = tuple(
        sorted(
            {
                _numero_finito("ano de projeção", ano, minimo=0)
                for ano in (*anos_projecao, *anos_grafico)
            }
        )
    )
    todas_projecoes = tabela_projecao_portfolio(
        respostas_validas["cap_inicial"],
        respostas_validas["aporte_mensal"],
        resultado["portfolio"],
        resultado["TAXAS"],
        resultado["taxa_pess"],
        ipca,
        anos_unicos,
        data_referencia=data_base,
        contexto_fiscal=contexto_fiscal,
        market=market,
    )
    por_ano = {linha["anos"]: linha for linha in todas_projecoes}
    projecoes = [por_ano[float(ano)] for ano in anos_projecao]
    serie_projecao = [por_ano[float(ano)] for ano in anos_grafico]

    meta = None
    if valores_meta[0] is not None:
        taxas_meta = taxas_por_risco(
            market,
            prazo_meses=max(1, round(float(valores_meta[1]) * 12)),
            data_referencia=data_base,
        )
        meta = analisar_meta(
            valores_meta[0],
            valores_meta[1],
            respostas_validas["cap_inicial"],
            respostas_validas["aporte_mensal"],
            resultado["portfolio"],
            taxas_meta,
            ipca,
            data_referencia=data_base,
            contexto_fiscal=contexto_fiscal,
        )

    resultado["perfil_resumo"] = _perfil_resumo(
        respostas_validas,
        resultado,
        meta,
    )
    return {
        "respostas": respostas_validas,
        "market": dict(market),
        "resultado": resultado,
        "projecoes": projecoes,
        "serie_projecao": serie_projecao,
        "meta": meta,
        "ativos_sugeridos": {},
        "classes_indisponiveis": {},
        "data_referencia": data_base.isoformat(),
        "contexto_fiscal": contexto_fiscal,
    }


def buscar_ativos_sugeridos(
    portfolio: dict,
    nivel_risco_perfil: int,
    market: dict,
    *,
    n: int = 5,
    prazo_anos: float | None = None,
    data_referencia: date | str | None = None,
    retorno_esperado_fundos: float | None = None,
) -> tuple[dict, dict]:
    """Busca ativos sem misturar falhas de fonte às sugestões válidas."""
    dados = _validar_market(market)
    payload = recomendar_por_portfolio(
        portfolio,
        nivel_risco_perfil,
        n=n,
        selic=dados["selic"],
        ipca=dados["ipca"],
        ibov_cagr=dados["ibov_cagr"],
        prazo_anos=prazo_anos,
        data_referencia=(
            _data_referencia_valida(data_referencia)
            if data_referencia is not None
            else None
        ),
        retorno_esperado_fundos=retorno_esperado_fundos,
    )
    if not isinstance(payload, Mapping):
        raise TypeError("O recomendador de ativos retornou formato inválido.")

    indisponiveis_bruto = payload.get("_indisponiveis", {})
    if not isinstance(indisponiveis_bruto, Mapping):
        raise TypeError("_indisponiveis deve ser um mapeamento.")
    ativos = {
        classe: lista
        for classe, lista in payload.items()
        if classe != "_indisponiveis"
    }
    return ativos, dict(indisponiveis_bruto)


def buscar_ativos_da_analise(
    analise: Mapping[str, Any],
    *,
    n: int = 5,
) -> tuple[dict, dict]:
    """Consulta os rankers usando somente os parâmetros da análise pronta."""
    try:
        resultado = analise["resultado"]
        market = analise["market"]
        portfolio_busca = resultado["portfolio_busca"]
        nivel_risco = resultado["nivel_risco_perfil"]
    except (KeyError, TypeError) as exc:
        raise ValueError("Estrutura de análise inválida.") from exc
    meta = analise.get("meta")
    if isinstance(meta, Mapping) and meta.get("prazo_anos") is not None:
        prazo_anos = float(meta["prazo_anos"])
    else:
        prazo_anos = float(resultado["prazo_taxa_meses"]) / 12.0
    return buscar_ativos_sugeridos(
        portfolio_busca,
        nivel_risco,
        market,
        n=n,
        prazo_anos=prazo_anos,
        data_referencia=analise.get("data_referencia"),
        retorno_esperado_fundos=float(resultado["taxa_perfil"]),
    )


def _enquadramento_tributario_portfolio(
    portfolio: Mapping[str, int | float],
) -> dict[str, dict[str, Any]]:
    enquadramentos: dict[str, dict[str, Any]] = {}
    for categoria, percentual in portfolio.items():
        if percentual <= 0:
            continue
        tratamento = _tipo_tributario(categoria)
        enquadramentos[categoria] = {
            "nome": _disp(categoria),
            **tratamento.como_dict(),
        }
    return enquadramentos


def _tributacao_exportacao(
    analise: Mapping[str, Any],
) -> dict[str, Any]:
    horizontes: list[dict[str, Any]] = []
    for linha in analise.get("projecoes", []):
        classes = {}
        for categoria, detalhe in linha.get(
            "tributacao_por_classe",
            {},
        ).items():
            classes[categoria] = {
                "nome": detalhe["nome"],
                "tipo_produto": detalhe["tipo_produto"],
                "percentual": detalhe["percentual"],
                "principal": detalhe["principal"],
                "bruto": detalhe["bruto"],
                "imposto_estimado": detalhe["imposto_estimado"],
                "liquido": detalhe["liquido"],
                "precisao": detalhe["precisao"],
                "premissas": list(detalhe["premissas"]),
                "fontes": list(detalhe["fontes"]),
                "regras": list(detalhe["regras"]),
                "quantidade_lotes": detalhe["quantidade_lotes"],
                "lotes_indeterminados": detalhe[
                    "lotes_indeterminados"
                ],
            }
            for campo_auditoria in (
                "metodo_tributacao",
                "aliquotas_efetivas",
                "eventos_come_cotas",
                "come_cotas_estimado",
                "ir_no_resgate",
                "iof_no_resgate",
                "saldo_apos_come_cotas",
                "custo_oportunidade_come_cotas",
            ):
                if campo_auditoria in detalhe:
                    classes[categoria][campo_auditoria] = detalhe[
                        campo_auditoria
                    ]
        horizontes.append(
            {
                "anos": linha["anos"],
                "imposto_estimado": linha["imposto_estimado"],
                "imposto_calculado_parcial": linha[
                    "imposto_calculado_parcial"
                ],
                "valor_liquido": linha["vf_liquido"],
                "valor_liquido_calculado_parcial": linha[
                    "vf_liquido_calculado_parcial"
                ],
                "bruto_indeterminado": linha["bruto_indeterminado"],
                "precisao": linha["precisao_tributaria"],
                "premissas": list(linha["premissas_tributarias"]),
                "fontes": list(linha["fontes_tributarias"]),
                "regras": list(linha["regras_tributarias"]),
                "por_classe": classes,
            }
        )
    return {
        "data_referencia": analise.get("data_referencia"),
        "contexto_fiscal": dict(analise.get("contexto_fiscal", {})),
        "horizontes": horizontes,
    }


def montar_payload_exportacao(
    analise: Mapping[str, Any],
) -> dict[str, Any]:
    """Monta a representação serializável comum à CLI e ao Streamlit."""
    try:
        resultado = analise["resultado"]
        respostas = analise["respostas"]
        market = analise["market"]
    except (KeyError, TypeError) as exc:
        raise ValueError("Estrutura de análise inválida.") from exc

    portfolio = resultado["portfolio"]
    focus = market.get("focus_selic")
    focus_por_ano = market.get("focus_selic_por_ano", {})
    if not isinstance(focus_por_ano, Mapping):
        focus_por_ano = {}
    return {
        "recomendacao": resultado["recomendacao_principal"],
        "recomendacao_display": resultado["recomendacao_display"],
        "categoria_representativa_carteira": resultado["perfil_exibido"],
        "categoria_representativa_display": resultado["perfil_display"],
        "portfolio": portfolio,
        "portfolio_display": {
            item["nome"]: item["percentual"]
            for item in resultado["portfolio_itens"]
        },
        "nivel_risco_perfil": resultado["nivel_risco_perfil"],
        "risco_recomendacao": resultado["risco_recomendado"],
        "taxas_utilizadas": {
            "selic_atual_pct": round(float(market["selic"]) * 100, 2),
            "focus_selic_pct": (
                round(float(focus) * 100, 2)
                if focus is not None
                else None
            ),
            "focus_selic_por_ano_pct": {
                str(ano): round(float(taxa) * 100, 2)
                for ano, taxa in focus_por_ano.items()
            },
            "taxa_base_pct": round(resultado["taxa_base"] * 100, 2),
            "metodo_taxa_base": resultado.get("metodo_taxa_base"),
            "prazo_taxa_meses": resultado.get("prazo_taxa_meses"),
            "meses_extrapolados_selic": resultado.get(
                "meses_extrapolados_selic"
            ),
            "ipca_12m_pct": round(float(market["ipca"]) * 100, 2),
            "ibov_cagr_10a_pct": round(
                float(market["ibov_cagr"]) * 100,
                2,
            ),
            "taxa_carteira_ponderada_bruto_pct": round(
                resultado["taxa_perfil"] * 100,
                2,
            ),
            "taxa_pessimista_bruto_pct": round(
                resultado["taxa_pess"] * 100,
                2,
            ),
            "enquadramento_tributario_por_classe": (
                _enquadramento_tributario_portfolio(portfolio)
            ),
        },
        "tributacao": _tributacao_exportacao(analise),
        "ranking_previdencia_liquida": resultado.get(
            "ranking_previdencia_liquida"
        ),
        "perfil": resultado["perfil_resumo"],
        "respostas_normalizadas": dict(respostas),
        "meta": analise.get("meta"),
        "projecoes": list(analise.get("projecoes", [])),
        "avisos": list(resultado["avisos"]),
        "ativos_sugeridos": dict(analise.get("ativos_sugeridos", {})),
        "classes_indisponiveis": dict(
            analise.get("classes_indisponiveis", {})
        ),
        "fontes_de_dados": list(market.get("fontes", [])),
        "dados_mercado": {
            "data_ref": market.get("data_ref"),
            "fetched_at": market.get("fetched_at"),
            "cache_status": market.get("cache_status"),
        },
    }
