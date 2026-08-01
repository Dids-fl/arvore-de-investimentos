"""Tabelas tributárias versionadas e suas fontes primárias."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

FONTE_RECEITA_RENDIMENTOS_CAPITAL = (
    "https://www.gov.br/receitafederal/pt-br/assuntos/"
    "meu-imposto-de-renda/tabelas/2026"
)
FONTE_RECEITA_FUNDOS = (
    "https://www.gov.br/receitafederal/pt-br/assuntos/noticias/2025/"
    "fevereiro/receita-federal-define-forma-e-prazo-para-que-os-"
    "administradores-de-fundos-comuniquem-o-nao-recolhimento-do-irrf-"
    "pela-falta-de-provimento-de-recursos"
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
        return (
            data_referencia >= self.vigencia_inicio
            and (
                self.vigencia_fim is None
                or data_referencia <= self.vigencia_fim
            )
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


def imposto_irpf_anual(base: float) -> float:
    base_valida = max(0.0, float(base))
    for limite, aliquota, deducao in IRPF_ANUAL_2026:
        if limite is None or base_valida <= limite:
            return max(0.0, base_valida * aliquota - deducao)
    raise RuntimeError("Tabela anual sem faixa final.")


def imposto_ganho_capital(ganho_acumulado: float) -> float:
    """Aplica as faixas progressivamente, sem tributar tudo pela última faixa."""
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
