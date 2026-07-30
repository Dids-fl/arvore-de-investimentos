"""Regras puras para definir a recomendação principal do investidor."""

from __future__ import annotations

import math
import unicodedata
from collections.abc import Iterable, Mapping

from core.categorias import _ARRISCADAS, RK, _risco
from utils.logging_config import get_logger

logger = get_logger(__name__)


class RecomendacaoBloqueadaError(ValueError):
    """A análise foi interrompida por uma regra financeira de segurança."""


class DividaJurosAltosError(RecomendacaoBloqueadaError):
    """Há dívida cara que deve ser priorizada antes de novos investimentos."""


_PREV_KEYS = {
    RK.PREV_PGBL,
    RK.PREV_VGBL,
    RK.PREV_PGBL_RF,
    RK.PREV_VGBL_RF,
}
_PRODUTOS_COMPLEXOS = {
    RK.RV_CRIPTO,
    RK.FUNDOS_CRIPTO,
    RK.COE,
    RK.ESTRUTURADOS,
    RK.OFERTAS,
    RK.CAMBIO,
}
_RECOMENDACOES_PROTEGIDAS = {
    RK.RF_RESERVA,
    RK.RF_REAVALIE,
    RK.RF_EQUILIBRIO,
    RK.RF_LIQUIDEZ,
    RK.RF_SELIC_CDB,
    *_PREV_KEYS,
}


def _adicionar(avisos: list[str], mensagem: str) -> None:
    if mensagem not in avisos:
        avisos.append(mensagem)


def _opcao(nome: str, valor: object, minimo: int, maximo: int) -> int:
    if isinstance(valor, bool):
        raise TypeError(f"{nome} deve ser um inteiro.")
    try:
        inteiro = int(valor)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{nome} deve ser um inteiro.") from exc
    if inteiro != valor or not minimo <= inteiro <= maximo:
        raise ValueError(f"{nome} deve estar entre {minimo} e {maximo}.")
    return inteiro


def _percentual(nome: str, valor: object) -> float:
    if isinstance(valor, bool):
        raise TypeError(f"{nome} deve ser numérico, não booleano.")
    try:
        numero = float(valor)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{nome} deve ser numérico.") from exc
    if not math.isfinite(numero) or not 0 <= numero <= 100:
        raise ValueError(f"{nome} deve estar entre 0 e 100.")
    return numero


def _sem_acentos(texto: str) -> str:
    decomposicao = unicodedata.normalize("NFKD", texto.casefold().strip())
    return "".join(
        caractere
        for caractere in decomposicao
        if not unicodedata.combining(caractere)
    )


def _normalizar_experiencia(
    experiencia: object,
    avisos: list[str],
) -> set[str]:
    if isinstance(experiencia, str):
        itens: Iterable[object] = experiencia.split(",")
    elif isinstance(experiencia, Iterable):
        itens = experiencia
    else:
        raise TypeError("experiencia deve ser texto ou uma coleção de textos.")

    aliases = {
        "poupanca": "poupança",
        "tesouro": "tesouro",
        "acoes": "ações",
        "fundos": "fundos",
        "opcoes": "opções",
        "nenhum": "nenhum",
    }
    normalizados: set[str] = set()
    desconhecidos: list[str] = []
    for item in itens:
        if not isinstance(item, str):
            raise TypeError("Cada item de experiencia deve ser texto.")
        limpo = item.strip()
        if not limpo:
            continue
        canonico = aliases.get(_sem_acentos(limpo))
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
        _adicionar(
            avisos,
            "ℹ️ A opção 'nenhum' foi ignorada porque há experiências informadas.",
        )
    return normalizados


def _validar_taxas(taxas: object) -> dict[int, float]:
    if not isinstance(taxas, Mapping):
        raise TypeError("TAXAS deve ser um mapeamento por nível de risco.")
    resultado: dict[int, float] = {}
    for nivel in (1, 2, 3):
        if nivel not in taxas:
            raise ValueError(f"TAXAS não contém o nível de risco {nivel}.")
        try:
            taxa = float(taxas[nivel])
        except (TypeError, ValueError) as exc:
            raise TypeError(f"TAXAS[{nivel}] deve ser numérica.") from exc
        if not math.isfinite(taxa) or taxa <= -1:
            raise ValueError(f"TAXAS[{nivel}] deve ser finita e maior que -100%.")
        resultado[nivel] = taxa
    return resultado


def _pode_assumir_volatilidade(
    prazo: int,
    objetivo: int,
    emocional: int,
    reserva_emerg: int,
    renda: int,
) -> bool:
    return (
        prazo == 3
        and objetivo == 2
        and emocional >= 2
        and reserva_emerg in {2, 3}
        and renda != 4
    )


def calcular_recomendacao(
    prazo: int,
    risco: int,
    objetivo: int,
    fluxo: int,
    controle: int,
    liquidez: int,
    liquidez_pct: float,
    reserva_emerg: int,
    idade: int,
    despesas: int,
    faixa_valor: int,
    patrim_pct: int,
    renda: int,
    dividas: int,
    conhecimento: int,
    experiencia: list[str],
    dependentes: int,
    aporte: int,
    emocional: int,
    ir_tipo: int,
    carteira_atual: int,
    TAXAS: dict,
) -> tuple[str, int, int, list[str], int]:
    """
    Calcula a categoria principal e o perfil ajustado.

    A função não imprime nem encerra o processo. Situações impeditivas são
    comunicadas por exceções, para que CLI, Streamlit ou API decidam como
    apresentar a mensagem.
    """
    prazo = _opcao("prazo", prazo, 1, 3)
    risco = _opcao("risco", risco, 1, 3)
    objetivo = _opcao("objetivo", objetivo, 1, 3)
    fluxo = _opcao("fluxo", fluxo, 1, 2)
    controle = _opcao("controle", controle, 1, 2)
    liquidez = _opcao("liquidez", liquidez, 1, 2)
    reserva_emerg = _opcao("reserva_emerg", reserva_emerg, 1, 3)
    idade = _opcao("idade", idade, 1, 3)
    despesas = _opcao("despesas", despesas, 1, 3)
    faixa_valor = _opcao("faixa_valor", faixa_valor, 1, 3)
    patrim_pct = _opcao("patrim_pct", patrim_pct, 1, 3)
    renda = _opcao("renda", renda, 1, 4)
    dividas = _opcao("dividas", dividas, 1, 3)
    conhecimento = _opcao("conhecimento", conhecimento, 1, 3)
    dependentes = _opcao("dependentes", dependentes, 1, 3)
    aporte = _opcao("aporte", aporte, 1, 2)
    emocional = _opcao("emocional", emocional, 1, 3)
    ir_tipo = _opcao("ir_tipo", ir_tipo, 1, 3)
    carteira_atual = _opcao("carteira_atual", carteira_atual, 1, 4)
    liquidez_pct = _percentual("liquidez_pct", liquidez_pct)
    taxas = _validar_taxas(TAXAS)

    avisos: list[str] = []
    experiencias = _normalizar_experiencia(experiencia, avisos)

    if liquidez == 2 and liquidez_pct:
        _adicionar(
            avisos,
            "ℹ️ O percentual de liquidez foi ignorado porque a resposta foi 'não'.",
        )
        liquidez_pct = 0.0
    elif liquidez == 1 and liquidez_pct == 0:
        _adicionar(
            avisos,
            "⚠️ Liquidez imediata foi solicitada sem percentual definido.",
        )

    if dividas == 1:
        melhor = max(taxas.values()) * 100
        raise DividaJurosAltosError(
            "Quite ou renegocie as dívidas de juros altos antes de investir. "
            f"O melhor retorno anual estimado ({melhor:.1f}%) não justifica "
            "manter cartão rotativo ou cheque especial."
        )
    if dividas == 2:
        _adicionar(
            avisos,
            (
                "⚠️ Dívidas de juros baixos podem coexistir com investimentos, "
                "mas compare o custo efetivo e evite concentração em alto risco."
            ),
        )

    risco_limitado_prazo = False
    if prazo == 1 and risco == 3:
        _adicionar(
            avisos,
            (
                "⚠️ Prazo curto e risco alto são incompatíveis; "
                "a tolerância foi reduzida."
            ),
        )
        risco = 2
        risco_limitado_prazo = True

    if emocional < risco:
        _adicionar(
            avisos,
            (
                "⚠️ Sua reação provável a perdas é mais conservadora que o "
                "risco declarado; o comportamento prevaleceu."
            ),
        )
        risco = emocional
    elif emocional > risco:
        _adicionar(
            avisos,
            (
                "ℹ️ Sua reação a quedas sugere mais tolerância, mas o risco "
                "declarado foi mantido como limite."
            ),
        )

    if patrim_pct == 3:
        estrutura_leve = idade == 1 and dependentes == 1 and despesas == 1
        if estrutura_leve:
            _adicionar(
                avisos,
                (
                    "ℹ️ O aporte supera 75% do patrimônio. Hoje suas obrigações "
                    "são leves, mas mantenha uma reserva acessível."
                ),
            )
        else:
            risco = min(risco, 2)
            _adicionar(
                avisos,
                (
                    "🚨 Mais de 75% do patrimônio será investido e há obrigações; "
                    "o risco foi limitado a moderado."
                ),
            )
    elif patrim_pct == 2 and (despesas == 3 or dependentes > 1):
        if risco == 3:
            risco = 2
        _adicionar(
            avisos,
            (
                "⚠️ O investimento representa parcela relevante do patrimônio; "
                "mantenha parte com liquidez."
            ),
        )

    aporte_bonus = aporte == 2 and prazo >= 2
    if aporte_bonus:
        _adicionar(
            avisos,
            (
                "ℹ️ Aportes mensais reduzem o risco de concentrar a entrada "
                "em um único preço, sem eliminar risco de mercado."
            ),
        )

    tem_experiencia_avancada = bool(experiencias & {"ações", "opções"})
    if "nenhum" in experiencias and conhecimento >= 2:
        conhecimento = 1
        _adicionar(
            avisos,
            (
                "⚠️ Sem experiência recente, o conhecimento prático foi "
                "tratado como iniciante."
            ),
        )
    elif conhecimento == 3 and not tem_experiencia_avancada:
        _adicionar(
            avisos,
            (
                "ℹ️ Conhecimento avançado sem uso recente de ações/opções: "
                "comece com posições menores."
            ),
        )
    elif conhecimento == 1 and tem_experiencia_avancada:
        conhecimento = 2
        _adicionar(
            avisos,
            "ℹ️ A experiência em ações/opções ajustou o nível para intermediário.",
        )

    teto_prazo = {1: 1, 2: 2, 3: 3}[prazo]
    risco_final = min(risco, teto_prazo)
    if risco_final != risco and not risco_limitado_prazo:
        _adicionar(
            avisos,
            "ℹ️ O prazo informado reduziu o nível máximo de risco.",
        )
    risco = risco_final
    nivel_risco_perfil = risco

    if risco == 1:
        rec_key = RK.RF
    elif risco == 2:
        rec_key = RK.RF if prazo == 1 else RK.FUNDOS
    else:
        rec_key = RK.RV if prazo == 2 else RK.RV_CRIPTO

    if aporte_bonus and rec_key == RK.FUNDOS:
        rec_key = (
            RK.FUNDOS_ACOES_DCA
            if conhecimento == 1
            else RK.RV_DCA
        )

    if fluxo == 1:
        _adicionar(
            avisos,
            (
                "ℹ️ Renda periódica pode variar e não é garantida; avalie "
                "Tesouro com cupom, FIIs e ações sem ignorar preço e risco."
            ),
        )
        if rec_key == RK.RF and objetivo != 1 and prazo >= 2:
            rec_key = RK.RF_IPCA
        elif _risco(rec_key) >= 2 and objetivo != 1:
            rec_key = RK.FIIS

    meses_res = min(
        12,
        3
        + (dependentes - 1) * 3
        + (3 if renda in {3, 4} else 0),
    )
    if dependentes == 2:
        _adicionar(
            avisos,
            f"ℹ️ Com um dependente, mire reserva de {meses_res} meses.",
        )
        if rec_key == RK.RV_CRIPTO:
            rec_key = RK.RV
    elif dependentes == 3:
        _adicionar(
            avisos,
            f"⚠️ Com dois ou mais dependentes, mire {meses_res} meses de reserva.",
        )
        if rec_key in {RK.RV_CRIPTO, RK.RV, RK.RV_DCA}:
            rec_key = RK.FUNDOS

    if reserva_emerg == 1:
        sem_obrigacoes = (
            idade == 1
            and dependentes == 1
            and despesas == 1
            and renda in {1, 2}
        )
        if sem_obrigacoes:
            _adicionar(
                avisos,
                (
                    f"ℹ️ Ainda não há reserva. Separe gradualmente {meses_res} "
                    "meses em produto líquido."
                ),
            )
            if rec_key in {RK.RV_CRIPTO, RK.RV_DCA}:
                rec_key = RK.RV
        else:
            rec_key = RK.RF_RESERVA
            _adicionar(
                avisos,
                (
                    f"⚠️ Priorize uma reserva de {meses_res} meses antes de "
                    "assumir risco ou baixa liquidez."
                ),
            )
    elif reserva_emerg == 2:
        _adicionar(
            avisos,
            f"⚠️ Complete a reserva até aproximadamente {meses_res} meses.",
        )
        if idade != 1 and rec_key in _ARRISCADAS:
            rec_key = RK.RV if rec_key == RK.RV_CRIPTO else RK.FUNDOS

    if renda == 2:
        _adicionar(
            avisos,
            "ℹ️ PJ contratado não possui a mesma proteção trabalhista de CLT.",
        )
    elif renda == 3:
        _adicionar(
            avisos,
            "ℹ️ Renda variável exige uma reserva de liquidez maior.",
        )
        if rec_key == RK.RV_CRIPTO:
            rec_key = RK.RV
    elif renda == 4:
        _adicionar(
            avisos,
            "⚠️ Sem renda recorrente, evite ativos voláteis ou de difícil resgate.",
        )
        if rec_key in _ARRISCADAS:
            rec_key = RK.FUNDOS if reserva_emerg == 3 else RK.RF_RESERVA

    if objetivo == 1:
        rec_key = (
            RK.RF_RESERVA
            if reserva_emerg != 3
            else RK.RF_LIQUIDEZ
        )
    elif objetivo == 2:
        if rec_key == RK.RF and prazo >= 2 and nivel_risco_perfil >= 2:
            rec_key = RK.FUNDOS
        if rec_key == RK.FUNDOS and prazo == 3:
            rec_key = RK.RV
    else:
        if prazo == 1:
            rec_key = RK.RF_REAVALIE
            _adicionar(
                avisos,
                "⚠️ Aposentadoria e prazo curto são incompatíveis; reveja o prazo.",
            )
        elif prazo == 2:
            rec_key = (
                RK.PREV_PGBL_RF
                if ir_tipo == 1
                else RK.PREV_VGBL_RF
            )
        else:
            rec_key = RK.PREV_PGBL if ir_tipo == 1 else RK.PREV_VGBL
        if prazo >= 2 and ir_tipo == 1:
            _adicionar(
                avisos,
                (
                    "ℹ️ PGBL pode permitir dedução limitada a 12% da renda "
                    "tributável para quem cumpre os requisitos e usa o modelo completo."
                ),
            )
        elif prazo >= 2:
            _adicionar(
                avisos,
                "ℹ️ No VGBL, o IR normalmente incide apenas sobre os rendimentos.",
            )

    if faixa_valor == 1:
        _adicionar(
            avisos,
            (
                "ℹ️ Para valor inicial baixo, priorize produtos sem taxa e "
                "com aporte mínimo acessível."
            ),
        )
        if rec_key not in _PREV_KEYS and _risco(rec_key) >= 2:
            rec_key = RK.RF_SELIC_CDB
    elif faixa_valor == 3:
        _adicionar(
            avisos,
            "ℹ️ Compare taxas, liquidez, risco de emissor e concentração.",
        )

    if conhecimento == 1:
        _adicionar(
            avisos,
            "ℹ️ Perfil iniciante: evite estruturas opacas e custos difíceis de medir.",
        )
        if rec_key in _PRODUTOS_COMPLEXOS:
            rec_key = (
                RK.FUNDOS_ACOES_ETF
                if _pode_assumir_volatilidade(
                    prazo,
                    objetivo,
                    emocional,
                    reserva_emerg,
                    renda,
                )
                else RK.FUNDOS_RF_LIQ
            )
    elif (
        conhecimento == 3
        and tem_experiencia_avancada
        and nivel_risco_perfil == 3
        and prazo == 3
    ):
        _adicionar(
            avisos,
            (
                "ℹ️ Produtos avançados devem ser posições complementares, "
                "com limite de perda e custos conhecidos."
            ),
        )

    if liquidez == 1:
        if liquidez_pct >= 50:
            rec_key = RK.RF_SELIC_CDB
            _adicionar(
                avisos,
                (
                    f"⚠️ {liquidez_pct:.0f}% exige acesso imediato; "
                    "a recomendação principal foi orientada à liquidez."
                ),
            )
        elif liquidez_pct > 0:
            _adicionar(
                avisos,
                (
                    f"ℹ️ Reserve {liquidez_pct:.0f}% em Tesouro Selic ou CDB "
                    "com liquidez diária."
                ),
            )

    if idade == 3:
        if rec_key == RK.RV_CRIPTO:
            rec_key = RK.RV
            _adicionar(
                avisos,
                "⚠️ A exposição direta a cripto foi removida.",
            )
        elif _risco(rec_key) >= 3:
            _adicionar(
                avisos,
                (
                    "ℹ️ Confirme se o horizonte e a reserva suportam perdas "
                    "relevantes antes de manter renda variável."
                ),
            )

    if carteira_atual == 2:
        _adicionar(
            avisos,
            "ℹ️ A nova posição pode diversificar a carteira conservadora existente.",
        )
        if rec_key == RK.RF and prazo >= 2 and nivel_risco_perfil >= 2:
            rec_key = RK.FUNDOS_DIVERSIF
    elif carteira_atual == 3:
        _adicionar(
            avisos,
            "ℹ️ A recomendação funciona como complemento da carteira moderada.",
        )
        if rec_key == RK.FUNDOS and nivel_risco_perfil == 3 and prazo == 3:
            rec_key = RK.RV_COMPL
    elif carteira_atual == 4:
        _adicionar(
            avisos,
            "ℹ️ A nova entrada deve reduzir a concentração da carteira arrojada.",
        )
        if (
            nivel_risco_perfil == 3
            and rec_key not in _RECOMENDACOES_PROTEGIDAS
        ):
            rec_key = RK.RF_EQUILIBRIO

    if controle == 2:
        delegacao = {
            RK.RV_DCA: RK.FUNDOS_ACOES_DCA,
            RK.RV: RK.FUNDOS_ACOES,
            RK.RV_CRIPTO: RK.FUNDOS_CRIPTO,
            RK.RF_SELIC_CDB: RK.FUNDOS_RF_LIQ,
            RK.RF: RK.FUNDOS_RF,
            RK.RF_LIQUIDEZ: RK.FUNDOS_RF_LIQ,
            RK.RF_IPCA: RK.FUNDOS_RF,
            RK.FUNDOS: RK.FUNDOS_MULTI,
            RK.FUNDOS_DIVERSIF: RK.FUNDOS_MULTI,
            RK.FIIS: RK.FIIS_DEL,
            RK.FUNDOS_ACOES_ETF: RK.FUNDOS_ACOES,
        }
        bloqueados = {
            RK.RF_RESERVA,
            RK.RF_REAVALIE,
            RK.RF_EQUILIBRIO,
            RK.COE,
            RK.ESTRUTURADOS,
            RK.OFERTAS,
            RK.CAMBIO,
            *_PREV_KEYS,
        }
        if rec_key not in bloqueados:
            rec_key = delegacao.get(rec_key, rec_key)

    pode_receber_avancado = (
        objetivo == 2
        and conhecimento >= 2
        and faixa_valor == 3
        and prazo == 3
        and liquidez == 2
        and reserva_emerg == 3
        and renda != 4
        and dividas == 3
        and nivel_risco_perfil >= 2
        and rec_key not in _RECOMENDACOES_PROTEGIDAS
    )
    if pode_receber_avancado:
        if carteira_atual == 4 and conhecimento == 3:
            rec_key = RK.OFERTAS
        elif carteira_atual == 4:
            rec_key = RK.ESTRUTURADOS
        elif controle == 2:
            rec_key = RK.COE
        elif carteira_atual == 3:
            rec_key = RK.CAMBIO

    logger.info(
        "Recomendação final: %s (risco %s)",
        rec_key,
        nivel_risco_perfil,
    )
    return (
        rec_key,
        nivel_risco_perfil,
        meses_res,
        avisos,
        conhecimento,
    )