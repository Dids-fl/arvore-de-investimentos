"""Smoke test do app Streamlit, com dados de mercado simulados.

Executa o app de verdade (AppTest), preenche o formulário e gera a análise,
para pegar erros que só aparecem na interface.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = Path(__file__).resolve().parents[2] / "app.py"


def _app(monkeypatch, mercado_valido) -> AppTest:
    import calendarios.sincronizar_b3 as sincronizar_b3
    import mercado

    monkeypatch.setattr(mercado, "load_market_data", lambda **_: dict(mercado_valido))
    monkeypatch.setattr(
        sincronizar_b3, "sincronizar_calendarios_relevantes", lambda *a, **k: []
    )
    app = AppTest.from_file(str(APP), default_timeout=120)
    app.run()
    return app


def _escolher(app: AppTest, rotulo: str, valor: str) -> None:
    for caixa in app.selectbox:
        if caixa.label.startswith(rotulo):
            caixa.set_value(valor)
            return
    raise AssertionError(f"Campo não encontrado: {rotulo}")


@pytest.mark.parametrize("objetivo", ["crescimento", "aposentadoria", "reserva"])
def test_app_gera_analise_sem_erros(monkeypatch, mercado_valido, objetivo) -> None:
    app = _app(monkeypatch, mercado_valido)
    assert not app.exception

    _escolher(app, "Prazo", "longo")
    _escolher(app, "Objetivo", objetivo)
    _escolher(app, "Dívidas", "não tenho")
    _escolher(app, "Reserva", "sim")
    app.button[0].click()
    app.run()

    assert not app.exception, [e.value for e in app.exception]
    assert not app.error, [e.value for e in app.error]
    titulos = [s.value for s in app.subheader]
    assert "📈 Projeção de crescimento" in titulos
    assert "📊 Alocação sugerida" in titulos


def test_app_mostra_taxas_no_padrao_brasileiro(monkeypatch, mercado_valido) -> None:
    app = _app(monkeypatch, mercado_valido)
    metricas = {m.label: m.value for m in app.sidebar.metric}
    assert metricas["SELIC"] == "10,00%"
