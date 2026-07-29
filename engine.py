"""Núcleo de negócio compartilhado pela CLI, pelo Streamlit e por APIs."""

from __future__ import annotations

import math
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Optional

from calculos import _vf_bruto, _vf_liquido, _vf_real
from core.catalogo import _aliq, _disp, _get_prod
from core.categorias import _risco
from portfolio import _build_portfolio, _classificar_portfolio_final
from recomendador import calcular_recomendacao
from recomendador_ativos import (
    MIN_PCT,
    _CLASSE,
    recomendar_por_portfolio,
)


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
            opcoes = ", ".join(
                sorted(
                    {
                        opcao
                        for opcao in mapa
                        if _normalizar_texto(opcao) == opcao
                    }
                    or set(mapa)
                )
            )
            raise ValueError(
                f"Opção inválida para {campo!r}: {valor!r}. "
                f"Use uma destas: {opcoes}."
            )
        resultado[campo] = mapa_normalizado[chave]
    return resultado


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
    if isinstance(valor, bool):
        raise TypeError(f"market[{chave!r}] não pode ser booleano.")
    try:
        numero = float(valor)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"market[{chave!r}] deve ser numérico.") from exc
    if not math.isfinite(numero):
        raise ValueError(f"market[{chave!r}] deve ser finito.")
    if not -1 < numero <= 5:
        raise ValueError(
            f"market[{chave!r}] deve ser decimal, por exemplo 0.15 para 15%."
        )
    return numero


def _validar_market(market: object) -> dict[str, float | None]:
    if not isinstance(market, Mapping):
        raise TypeError("market deve ser o mapeamento devolvido por mercado.py.")
    return {
        "selic": _numero_mercado(market, "selic"),
        "focus_selic": _numero_mercado(
            market,
            "focus_selic",
            opcional=True,
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
    return mapear_respostas_formulario(dict(respostas))


def taxa_base_mercado(market: dict) -> float:
    """Usa a média SELIC/Focus quando a expectativa está disponível."""
    dados = _validar_market(market)
    selic = float(dados["selic"])
    focus = dados["focus_selic"]
    return (selic + float(focus)) / 2.0 if focus is not None else selic


def taxas_por_risco(market: dict) -> dict[int, float]:
    """Constrói as taxas brutas usadas como hipóteses por nível de risco."""
    dados = _validar_market(market)
    selic = float(dados["selic"])
    focus = dados["focus_selic"]
    ibov = float(dados["ibov_cagr"])
    taxa_base = (
        (selic + float(focus)) / 2.0
        if focus is not None
        else selic
    )
    return {
        1: taxa_base,
        2: (taxa_base + ibov) / 2.0,
        3: ibov,
    }


def _portfolio_positivo(
    portfolio: Mapping[str, int | float],
) -> dict[str, float]:
    if not isinstance(portfolio, Mapping):
        raise TypeError("portfolio deve ser um mapeamento.")
    positivos: dict[str, float] = {}
    for categoria, percentual in portfolio.items():
        if isinstance(percentual, bool):
            raise TypeError(
                f"O percentual de {categoria!r} não pode ser booleano."
            )
        try:
            numero = float(percentual)
        except (TypeError, ValueError) as exc:
            raise TypeError(
                f"O percentual de {categoria!r} deve ser numérico."
            ) from exc
        if not math.isfinite(numero) or numero < 0:
            raise ValueError(
                f"O percentual de {categoria!r} deve ser finito e não negativo."
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
    """Mantém o cenário pessimista sempre menor ou igual ao central."""
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
    taxa_unica: Optional[float] = None,
) -> dict[str, float]:
    """Projeta e tributa cada classe da carteira separadamente."""
    positivos = _portfolio_positivo(portfolio)
    total = sum(positivos.values())

    bruto = 0.0
    liquido = 0.0
    for categoria, percentual in positivos.items():
        peso = percentual / total
        taxa = (
            float(taxa_unica)
            if taxa_unica is not None
            else float(taxas[_risco(categoria)])
        )
        aliquota, pgbl = _aliq(categoria)
        capital_classe = float(cap_inicial) * peso
        aporte_classe = float(aporte_mensal) * peso
        bruto += _vf_bruto(
            capital_classe,
            aporte_classe,
            taxa,
            anos,
        )
        liquido += _vf_liquido(
            capital_classe,
            aporte_classe,
            taxa,
            anos,
            aliquota,
            pgbl,
        )

    return {
        "bruto": bruto,
        "liquido": liquido,
        "real": _vf_real(liquido, ipca, anos),
    }


def aporte_necessario_para_meta(
    meta_valor: float,
    meta_prazo: float,
    cap_inicial: float,
    portfolio: Mapping[str, int | float],
    taxas: Mapping[int, float],
    ipca: float,
) -> Optional[float]:
    """Resolve por busca binária o aporte para atingir uma meta líquida."""
    try:
        meta = float(meta_valor)
        prazo = float(meta_prazo)
    except (TypeError, ValueError) as exc:
        raise TypeError("Meta e prazo devem ser numéricos.") from exc
    if not math.isfinite(meta) or meta <= 0:
        raise ValueError("meta_valor deve ser finito e positivo.")
    if not math.isfinite(prazo) or prazo <= 0:
        raise ValueError("meta_prazo deve ser finito e positivo.")

    sem_aporte = projetar_portfolio(
        cap_inicial,
        0,
        portfolio,
        taxas,
        ipca,
        prazo,
    )["liquido"]
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
        )["liquido"]
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
        )["liquido"]
        if valor >= meta:
            superior = meio
        else:
            inferior = meio
    return superior


def gerar_recomendacao_completa(respostas: dict, market: dict) -> dict:
    """Executa perfil, recomendação, carteira, catálogo e taxas."""
    respostas_validas = _validar_respostas(respostas)
    dados_mercado = _validar_market(market)
    taxas = taxas_por_risco(market)
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
    perfil_exibido, risco_recomendado = _classificar_portfolio_final(
        portfolio
    )

    info_principal = _get_prod(rec_key)
    info_carteira = _get_prod(perfil_exibido)
    aliquota, pgbl = _aliq(perfil_exibido)
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

    return {
        "rec_key": rec_key,
        "recomendacao_principal": rec_key,
        "recomendacao_display": _disp(rec_key),
        "perfil_exibido": perfil_exibido,
        "perfil_display": _disp(perfil_exibido),
        "portfolio": portfolio,
        "portfolio_busca": portfolio_busca,
        "nivel_risco_perfil": nivel_risco_perfil,
        "risco_recomendado": risco_recomendado,
        # Compatibilidade: "info" continua descrevendo a carteira.
        "info": info_carteira,
        "info_principal": info_principal,
        "info_carteira": info_carteira,
        "aliq": aliquota,
        "pgbl": pgbl,
        "taxa_base": taxa_base_mercado(market),
        "taxa_perfil": taxa_perfil,
        "taxa_pess": taxa_pess,
        "avisos": avisos,
        "meses_res": meses_res,
        "conhecimento_ajustado": conhecimento_ajustado,
        "classes_no_portfolio": classes_no_portfolio,
        "TAXAS": taxas,
    }


def buscar_ativos_sugeridos(
    portfolio: dict,
    nivel_risco_perfil: int,
    market: dict,
) -> tuple[dict, dict]:
    """Busca ativos sem misturar falhas de fonte às sugestões válidas."""
    dados = _validar_market(market)
    payload = recomendar_por_portfolio(
        portfolio,
        nivel_risco_perfil,
        selic=dados["selic"],
        ipca=dados["ipca"],
        ibov_cagr=dados["ibov_cagr"],
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
        linhas.append(
            {
                "anos": anos,
                "vf_bruto": bruto,
                "vf_liquido": liquido,
                "vf_real": _vf_real(liquido, ipca, anos),
                "vf_pessimista": _vf_liquido(
                    cap_inicial,
                    aporte_mensal,
                    min(taxa_perfil, taxa_pess),
                    anos,
                    aliq,
                    pgbl,
                ),
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
    anos_lista: Sequence[float] = (1, 2, 5, 10, 20, 30),
) -> list[dict]:
    """Projeção correta da carteira, com imposto próprio de cada classe."""
    linhas: list[dict] = []
    taxa_central = _taxa_ponderada(portfolio, taxas)
    pessimismo = min(float(taxa_pess), taxa_central)
    for anos in anos_lista:
        central = projetar_portfolio(
            cap_inicial,
            aporte_mensal,
            portfolio,
            taxas,
            ipca,
            anos,
        )
        pessimista = projetar_portfolio(
            cap_inicial,
            aporte_mensal,
            portfolio,
            taxas,
            ipca,
            anos,
            taxa_unica=pessimismo,
        )
        linhas.append(
            {
                "anos": anos,
                "vf_bruto": central["bruto"],
                "vf_liquido": central["liquido"],
                "vf_real": central["real"],
                "vf_pessimista": pessimista["liquido"],
            }
        )
    return linhas