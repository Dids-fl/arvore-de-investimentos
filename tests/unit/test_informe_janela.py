"""Janela móvel de 3 anos do Informe Diário da CVM, sem rede."""

from __future__ import annotations

import pytest

coletor_mod = pytest.importorskip("fundos.informe_diario_coletor")


@pytest.fixture
def coletor(tmp_path, monkeypatch):
    c = coletor_mod.InformeDiarioColetorCVM(db_path=tmp_path / "informe.db", atualizar=False)
    monkeypatch.setattr(c, "_gerar_lista_meses", lambda q: [(2026, 11), (2026, 10), (2026, 9), (2026, 8)][:q])
    monkeypatch.setattr(coletor_mod, "_remover_antigos", lambda recentes: [])
    yield c
    c.conn.close()


def _inserir(c, data):
    c.conn.execute(
        "INSERT INTO informe_diario (CNPJ_Classe, Data_Competencia, Valor_Cota) VALUES (?, ?, ?)",
        ("00000000000191", data, 1.0),
    )
    c.conn.commit()


def test_remove_registros_fora_da_janela(coletor, monkeypatch):
    for data in ("2026-07-31", "2026-08-01", "2026-09-15"):
        _inserir(coletor, data)
    monkeypatch.setattr(coletor, "atualizar_informe", lambda **k: None)
    monkeypatch.setattr(coletor_mod, "_precisa_atualizar", lambda a, m: False)

    coletor.carregar_historico(anos=1, meses_recentes_forcar=2)

    datas = [r[0] for r in coletor.conn.execute("SELECT Data_Competencia FROM informe_diario")]
    assert sorted(datas) == ["2026-08-01", "2026-09-15"]


def test_mes_recente_sem_arquivo_novo_nao_e_reprocessado(coletor, monkeypatch):
    for data in ("2026-11-03", "2026-10-30", "2026-09-30", "2026-08-31"):
        _inserir(coletor, data)
    processados = []
    monkeypatch.setattr(
        coletor, "atualizar_informe", lambda ano, mes, force: processados.append((ano, mes))
    )
    monkeypatch.setattr(coletor_mod, "_precisa_atualizar", lambda a, m: (a, m) == (2026, 11))

    coletor.carregar_historico(anos=1, meses_recentes_forcar=2)

    assert processados == [(2026, 11)]


def test_mes_ausente_e_baixado(coletor, monkeypatch):
    processados = []
    monkeypatch.setattr(
        coletor, "atualizar_informe", lambda ano, mes, force: processados.append((ano, mes))
    )
    monkeypatch.setattr(coletor_mod, "_precisa_atualizar", lambda a, m: True)

    coletor.carregar_historico(anos=1, meses_recentes_forcar=2)

    assert processados == [(2026, 11), (2026, 10), (2026, 9), (2026, 8)]


def test_consultas_respeitam_data_maxima(coletor):
    for data in ("2026-08-03", "2026-09-01", "2026-10-01"):
        _inserir(coletor, data)

    historico = coletor.listar_historicos(["00000000000191"], limite=10, data_maxima="2026-09-15")
    metricas = coletor.listar_metricas_agregadas(["00000000000191"], data_maxima="2026-09-15")

    assert list(historico["Data_Competencia"]) == ["2026-08-03", "2026-09-01"]
    assert int(metricas["Dias_Historico"].iloc[0]) == 2
