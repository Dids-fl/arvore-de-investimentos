"""Tributação de PGBL e VGBL nos regimes regressivo e progressivo."""

from __future__ import annotations

import math

from tributacao.base import (
    ContextoTributario,
    PrecisaoTributaria,
    ResultadoTributario,
    resultado_calculado,
    resultado_indeterminado,
)
from tributacao.regras import (
    FONTE_PREVIDENCIA,
    FONTE_RECEITA_PGBL_VGBL,
    VIGENCIA_BASE,
    aliquota_previdencia,
    imposto_irpf_anual,
)


def _base_previdencia(contexto: ContextoTributario) -> float:
    if contexto.tipo_produto == "pgbl":
        return contexto.valor_bruto
    return contexto.ganho


def _base_calculo_anual(contexto: ContextoTributario) -> float:
    """Obtém a base anual; por padrão, usa a renda como aproximação."""
    valor = contexto.metadados.get(
        "base_calculo_irpf_anual",
        contexto.renda_tributavel,
    )
    if isinstance(valor, bool):
        raise TypeError("base_calculo_irpf_anual não pode ser booleano.")
    try:
        numero = float(valor)
    except (TypeError, ValueError) as exc:
        raise TypeError(
            "base_calculo_irpf_anual deve ser numérico."
        ) from exc
    if not math.isfinite(numero) or numero < 0:
        raise ValueError(
            "base_calculo_irpf_anual deve ser finito e não negativo."
        )
    return numero


def _calcular_regressivo(
    contexto: ContextoTributario,
    base: float,
) -> ResultadoTributario:
    aliquota = aliquota_previdencia(contexto.prazo_anos)
    return resultado_calculado(
        contexto,
        imposto=base * aliquota,
        aliquota=aliquota if base else 0.0,
        precisao=PrecisaoTributaria.ESTIMADA,
        premissas=(
            (
                "PGBL tributado sobre o saldo total."
                if contexto.tipo_produto == "pgbl"
                else "VGBL tributado apenas sobre o rendimento."
            ),
            "Todo o saldo foi tratado como um único lote.",
            "Aportes reais devem ser tributados pela idade de cada lote.",
            "A regra de 2026 foi mantida como hipótese até o resgate.",
        ),
        fonte=FONTE_PREVIDENCIA,
        vigencia=VIGENCIA_BASE,
        regra_id=f"{contexto.tipo_produto}_regressivo_2026",
    )


def _calcular_progressivo(
    contexto: ContextoTributario,
    base_resgate: float,
) -> ResultadoTributario:
    if contexto.renda_tributavel is None:
        return resultado_indeterminado(
            contexto,
            motivo=(
                "O regime progressivo exige a renda tributável anual para "
                "estimar o ajuste."
            ),
            fonte=FONTE_PREVIDENCIA,
            vigencia=VIGENCIA_BASE,
            regra_id=f"{contexto.tipo_produto}_progressivo_sem_renda",
        )

    rendimentos_antes = contexto.renda_tributavel
    base_antes = _base_calculo_anual(contexto)
    rendimentos_depois = rendimentos_antes + base_resgate
    base_depois = base_antes + base_resgate

    imposto_sem_resgate = imposto_irpf_anual(
        base_antes,
        rendimentos_tributaveis=rendimentos_antes,
    )
    imposto_com_resgate = imposto_irpf_anual(
        base_depois,
        rendimentos_tributaveis=rendimentos_depois,
    )
    imposto_incremental = max(
        0.0,
        imposto_com_resgate - imposto_sem_resgate,
    )
    base_explicita = "base_calculo_irpf_anual" in contexto.metadados
    premissas = [
        "Estimativa incremental pela tabela e redução anual de 2026.",
        "PGBL soma o saldo resgatado; VGBL soma apenas o rendimento.",
        "A regra de 2026 foi mantida como hipótese até o resgate.",
        "Retenções, outras rendas e particularidades da declaração foram omitidas.",
    ]
    if not base_explicita:
        premissas.append(
            "A renda tributável foi usada também como base de cálculo anual."
        )

    return resultado_calculado(
        contexto,
        imposto=imposto_incremental,
        aliquota=(imposto_incremental / base_resgate if base_resgate else 0.0),
        precisao=PrecisaoTributaria.ESTIMADA,
        premissas=tuple(premissas),
        fonte=FONTE_RECEITA_PGBL_VGBL,
        vigencia=VIGENCIA_BASE,
        regra_id=f"{contexto.tipo_produto}_progressivo_2026",
    )


def calcular_previdencia(
    contexto: ContextoTributario,
) -> ResultadoTributario:
    """Calcula a estimativa sem inferir tipo ou regime ausentes."""
    if contexto.tipo_produto not in {"pgbl", "vgbl"}:
        return resultado_indeterminado(
            contexto,
            motivo="Informe pgbl ou vgbl como tipo_produto.",
            fonte=FONTE_RECEITA_PGBL_VGBL,
            vigencia=VIGENCIA_BASE,
            regra_id="previdencia_tipo_indeterminado",
        )
    if contexto.regime not in {"regressivo", "progressivo"}:
        return resultado_indeterminado(
            contexto,
            motivo="Informe regime regressivo ou progressivo.",
            fonte=FONTE_PREVIDENCIA,
            vigencia=VIGENCIA_BASE,
            regra_id="previdencia_regime_indeterminado",
        )

    base = _base_previdencia(contexto)
    if contexto.regime == "regressivo":
        return _calcular_regressivo(contexto, base)
    return _calcular_progressivo(contexto, base)
