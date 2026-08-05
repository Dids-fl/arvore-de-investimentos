"""Tabelas tributárias versionadas e suas fontes primárias."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

FONTE_RECEITA_RENDIMENTOS_CAPITAL = (
    "https://www.gov.br/receitafederal/pt-br/assuntos/"
    "meu-imposto-de-renda/tabelas/2026"
)
FONTE_RECEITA_FUNDOS = (
    "https://www.gov.br/receitafederal/pt-br/assuntos/"
    "meu-imposto-de-renda/pagamento/renda-variavel/"
    "fundos-de-investimento-no-brasil"
)
FONTE_RECEITA_PGBL_VGBL = (
    "https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/"
    "perguntas-frequentes/imposto-de-renda/dirpf/declaracao/pgvl-vgbl"
)
FONTE_PREVIDENCIA = (
    "https://www.gov.br/previdencia/pt-br/assuntos/"
    "previdencia-complementar/mais-informacoes/"
    "perguntas-frequentes-de-previdencia-complementar"
)
FONTE_RECEITA_GANHO_CAPITAL = (
    "https://www.gov.br/receitafederal/pt-br/assuntos/"
    "meu-imposto-de-renda/pagamento/ganhos-de-capital/aliquotas"
)
FONTE_RFB_APLICACOES_FINANCEIRAS_EXTERIOR = (
    "https://normas.receita.fazenda.gov.br/sijut2consulta/"
    "link.action?idAto=136603"
)
FONTE_RECEITA_DIRPF = (
    "https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/"
    "perguntas-frequentes/imposto-de-renda/dirpf"
)
FONTE_SUSEP_VGBL_IOF = (
    "https://www.gov.br/susep/pt-br/central-de-conteudos/noticias/"
    "2025/junho/novo-decreto-atualiza-regra-de-iof-para-planos-vgbl"
)
FONTE_IOF = (
    "https://www.planalto.gov.br/ccivil_03/_ato2007-2010/2007/"
    "decreto/d6306.htm"
)
FONTE_LEI_11033_ISENCOES = (
    "https://www.planalto.gov.br/ccivil_03/_ato2004-2006/2004/"
    "lei/l11033compilado.htm"
)
FONTE_LEI_12431_DEBENTURES = (
    "https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2011/"
    "lei/l12431.htm"
)
FONTE_B3_CALENDARIO_2026 = (
    "https://www.b3.com.br/pt_br/noticias/"
    "calendario-de-negociacao-da-b3-confira-o-funcionamento-da-bolsa-em-2026.htm"
)

VIGENCIA_BASE = date(2026, 1, 1)


@dataclass(frozen=True)
class RegraTributaria:
    id: str
    produto: str
    vigencia_inicio: date
    fonte: str
    descricao: str
    vigencia_fim: date | None = None

    def vigente_em(self, data_referencia: date) -> bool:
        return data_referencia >= self.vigencia_inicio and (
            self.vigencia_fim is None
            or data_referencia <= self.vigencia_fim
        )


RF_REGRESSIVA_DIAS = (
    (180, 0.225),
    (360, 0.20),
    (720, 0.175),
    (None, 0.15),
)
FUNDO_CURTO_PRAZO_DIAS = (
    (180, 0.225),
    (None, 0.20),
)
COME_COTAS_ALIQUOTAS = {
    "fundo_curto_prazo": 0.20,
    "fundo_longo_prazo": 0.15,
    "fundo_rf": 0.15,
}
PREVIDENCIA_REGRESSIVA_ANOS = (
    (2.0, 0.35),
    (4.0, 0.30),
    (6.0, 0.25),
    (8.0, 0.20),
    (10.0, 0.15),
    (None, 0.10),
)
GANHO_CAPITAL_FAIXAS = (
    (5_000_000.0, 0.15),
    (10_000_000.0, 0.175),
    (30_000_000.0, 0.20),
    (None, 0.225),
)
IRPF_APLICACOES_FINANCEIRAS_EXTERIOR = 0.15
IRPF_ANUAL_2026 = (
    (29_145.60, 0.0, 0.0),
    (33_919.80, 0.075, 2_185.92),
    (45_012.60, 0.15, 4_729.91),
    (55_976.16, 0.225, 8_105.85),
    (None, 0.275, 10_904.66),
)
IRPF_REDUCAO_ANUAL_LIMITE_INTEGRAL = 60_000.0
IRPF_REDUCAO_ANUAL_MAXIMA = 2_694.15
IRPF_REDUCAO_ANUAL_LIMITE_FINAL = 88_200.0
IRPF_REDUCAO_ANUAL_CONSTANTE = 8_429.73
IRPF_REDUCAO_ANUAL_COEFICIENTE = 0.095575

# Percentual de IOF sobre o rendimento em resgates com menos de 30 dias.
IOF_RENDA_FIXA_DIAS = {
    1: 0.96,
    2: 0.93,
    3: 0.90,
    4: 0.86,
    5: 0.83,
    6: 0.80,
    7: 0.76,
    8: 0.73,
    9: 0.70,
    10: 0.66,
    11: 0.63,
    12: 0.60,
    13: 0.56,
    14: 0.53,
    15: 0.50,
    16: 0.46,
    17: 0.43,
    18: 0.40,
    19: 0.36,
    20: 0.33,
    21: 0.30,
    22: 0.26,
    23: 0.23,
    24: 0.20,
    25: 0.16,
    26: 0.13,
    27: 0.10,
    28: 0.06,
    29: 0.03,
}


def aliquota_por_limite(
    valor: float,
    tabela: tuple[tuple[float | None, float], ...],
) -> float:
    for limite, aliquota in tabela:
        if limite is None or valor <= limite:
            return aliquota
    raise RuntimeError("Tabela tributária sem faixa final.")


def aliquota_rf(prazo_dias: int) -> float:
    return aliquota_por_limite(float(max(0, prazo_dias)), RF_REGRESSIVA_DIAS)


def aliquota_previdencia(prazo_anos: float) -> float:
    return aliquota_por_limite(
        max(0.0, prazo_anos),
        PREVIDENCIA_REGRESSIVA_ANOS,
    )


def imposto_irpf_anual_bruto(base_calculo: float) -> float:
    """Calcula o IRPF antes da redução anual criada para 2026."""
    base_valida = max(0.0, float(base_calculo))
    for limite, aliquota, deducao in IRPF_ANUAL_2026:
        if limite is None or base_valida <= limite:
            return max(0.0, base_valida * aliquota - deducao)
    raise RuntimeError("Tabela anual sem faixa final.")


def reducao_irpf_anual_2026(
    rendimentos_tributaveis: float,
    imposto_bruto: float,
) -> float:
    """Calcula a redução anual, limitada ao imposto apurado."""
    rendimentos = max(0.0, float(rendimentos_tributaveis))
    imposto = max(0.0, float(imposto_bruto))
    if rendimentos <= IRPF_REDUCAO_ANUAL_LIMITE_INTEGRAL:
        reducao = IRPF_REDUCAO_ANUAL_MAXIMA
    elif rendimentos <= IRPF_REDUCAO_ANUAL_LIMITE_FINAL:
        reducao = max(
            0.0,
            IRPF_REDUCAO_ANUAL_CONSTANTE
            - IRPF_REDUCAO_ANUAL_COEFICIENTE * rendimentos,
        )
    else:
        reducao = 0.0
    return min(imposto, reducao)


def imposto_irpf_anual(
    base_calculo: float,
    *,
    rendimentos_tributaveis: float | None = None,
) -> float:
    """Aplica tabela e redução anual de 2026.

    A base de cálculo e os rendimentos sujeitos ao ajuste são conceitos
    diferentes. Quando o segundo valor não é informado, a função usa a base
    como aproximação explícita para manter compatibilidade.
    """
    imposto_bruto = imposto_irpf_anual_bruto(base_calculo)
    rendimentos = (
        base_calculo
        if rendimentos_tributaveis is None
        else rendimentos_tributaveis
    )
    reducao = reducao_irpf_anual_2026(rendimentos, imposto_bruto)
    return max(0.0, imposto_bruto - reducao)


def imposto_ganho_capital(ganho_acumulado: float) -> float:
    """Aplica as faixas progressivamente, sem tributar tudo pela última."""
    restante = max(0.0, float(ganho_acumulado))
    imposto = 0.0
    limite_anterior = 0.0
    for limite, aliquota in GANHO_CAPITAL_FAIXAS:
        if limite is None:
            imposto += restante * aliquota
            break
        largura = limite - limite_anterior
        parcela = min(restante, largura)
        imposto += parcela * aliquota
        restante -= parcela
        if restante <= 0:
            break
        limite_anterior = limite
    return imposto
