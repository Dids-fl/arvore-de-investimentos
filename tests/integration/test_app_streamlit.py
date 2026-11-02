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


def tmp_path_factory_dir(monkeypatch):
    import tempfile

    pasta = Path(tempfile.mkdtemp(prefix="arvore_teste_"))
    monkeypatch.setenv("ARVORE_DIARIO", str(pasta / "decisoes.jsonl"))
    return pasta


def _app(monkeypatch, mercado_valido) -> AppTest:
    import calendarios.sincronizar_b3 as sincronizar_b3
    import mercado
    from decisao import historico

    # Sem internet nos testes: o histórico usa só a base embarcada.
    monkeypatch.setattr(historico, "_baixar_recentes", lambda desde: historico.ler_base().iloc[0:0])
    monkeypatch.setattr(historico, "CACHE_RECENTES", tmp_path_factory_dir(monkeypatch) / "recentes.csv")

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
    assert "🛡️ Antes de uma decisão grande" in titulos


def test_app_salva_decisao_no_historico(monkeypatch, mercado_valido) -> None:
    import os

    from decisao import diario

    app = _app(monkeypatch, mercado_valido)
    _escolher(app, "Prazo", "longo")
    _escolher(app, "Dívidas", "não tenho")
    _escolher(app, "Reserva", "sim")
    app.button[0].click()
    app.run()
    salvar = next(b for b in app.button if b.label.startswith("Salvar esta análise"))
    salvar.click()
    app.run()
    assert not app.exception, [e.value for e in app.exception]
    registros = diario.listar(Path(os.environ["ARVORE_DIARIO"]))
    assert len(registros) == 1


def test_app_mostra_taxas_no_padrao_brasileiro(monkeypatch, mercado_valido) -> None:
    app = _app(monkeypatch, mercado_valido)
    metricas = {m.label: m.value for m in app.sidebar.metric}
    assert metricas["SELIC"] == "10,00%"
