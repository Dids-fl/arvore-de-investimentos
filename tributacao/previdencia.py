"""Tributação de PGBL e VGBL nos regimes regressivo e progressivo."""

from __future__ import annotations

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


def calcular_previdencia(
    contexto: ContextoTributario,
) -> ResultadoTributario:
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
        aliquota = aliquota_previdencia(contexto.prazo_anos)
        return resultado_calculado(
            contexto,
            imposto=base * aliquota,
            aliquota=aliquota,
            precisao=PrecisaoTributaria.ESTIMADA,
            premissas=(
                (
                    "PGBL tributado sobre o saldo total."
                    if contexto.tipo_produto == "pgbl"
                    else "VGBL tributado apenas sobre o rendimento."
                ),
                "Todo o saldo foi tratado como um único lote.",
                "Aportes reais devem ser tributados pela idade de cada lote.",
            ),
            fonte=FONTE_PREVIDENCIA,
            vigencia=VIGENCIA_BASE,
            regra_id=f"{contexto.tipo_produto}_regressivo_2026",
        )

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

    imposto_sem_resgate = imposto_irpf_anual(contexto.renda_tributavel)
    imposto_com_resgate = imposto_irpf_anual(
        contexto.renda_tributavel + base
    )
    imposto_incremental = max(0.0, imposto_com_resgate - imposto_sem_resgate)
    return resultado_calculado(
        contexto,
        imposto=imposto_incremental,
        aliquota=(imposto_incremental / base if base else 0.0),
        precisao=PrecisaoTributaria.ESTIMADA,
        premissas=(
            "Estimativa incremental pela tabela anual de 2026.",
            "Deduções, redução anual, retenções e outras rendas foram omitidas.",
        ),
        fonte=FONTE_PREVIDENCIA,
        vigencia=VIGENCIA_BASE,
        regra_id=f"{contexto.tipo_produto}_progressivo_2026",
    )
