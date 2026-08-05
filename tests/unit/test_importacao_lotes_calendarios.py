"""Testes dos importadores de lotes e calendários versionados."""

from __future__ import annotations

import io
import json
from datetime import date

import pandas as pd
import pytest

from calendarios.mercado import carregar_ano, carregar_intervalo
from calendarios.registrar_b3 import registrar_calendario
from calendarios.sincronizar_b3 import (
    URL_CALENDARIO_B3,
    extrair_calendario_b3,
    sincronizar_calendarios_relevantes,
    validar_calendario_extraido,
)
from importacao.lotes_tributarios import (
    importar_lotes_tributarios,
    mesclar_metadados_tributarios,
)
from tributacao.projecoes import projetar_come_cotas


def _csv_lotes() -> bytes:
    return (
        b"id_lote,categoria,tipo_lote,principal,saldo_atual,"
        b"data_aplicacao,base_tributaria_atual,ganho_antecipado,"
        b"come_cotas_pago_historico,saldo_categoria_esperado\n"
        b"F1,fundos_rf,fundo,8000,10000,2022-03-15,9300,700,105,10000\n"
        b"P1,prev_pgbl,previdencia,6000,7500,2019-08-10,,,,7500\n"
    )


def _html_b3_2026(*, remover: str | None = None) -> str:
    datas = [
        "2026-01-01",
        "2026-02-16",
        "2026-02-17",
        "2026-04-03",
        "2026-04-21",
        "2026-05-01",
        "2026-06-04",
        "2026-09-07",
        "2026-10-12",
        "2026-11-02",
        "2026-11-20",
        "2026-12-24",
        "2026-12-25",
        "2026-12-31",
    ]
    if remover is not None:
        datas.remove(remover)
    nomes = {
        1: "Janeiro",
        2: "Fevereiro",
        4: "Abril",
        5: "Maio",
        6: "Junho",
        9: "Setembro",
        10: "Outubro",
        11: "Novembro",
        12: "Dezembro",
    }
    partes = ["<html><body><h2>Calendário do mercado 2026</h2>"]
    for mes, nome in nomes.items():
        partes.append(f'<a href="#m{mes}">{nome}</a>')
        partes.append(f'<div class="content" id="m{mes}"><table>')
        partes.append("<tr><th>Dia</th><th>Evento</th><th>Descrição</th></tr>")
        for valor in datas:
            item = date.fromisoformat(valor)
            if item.month != mes:
                continue
            partes.append(
                f"<tr><td>{item.day:02d}</td><td>Feriado</td><td>"
                "Listado B3: Não haverá negociação nos mercados de renda "
                "variável, renda fixa privada e derivativos listados."
                "</td></tr>"
            )
        if mes == 2:
            partes.append(
                "<tr><td>18</td><td>Quarta-feira de Cinzas</td>"
                "<td>Listado B3: negociação começa às 13h.</td></tr>"
            )
        partes.append(
            "<tr><td>19</td><td>Feriado norte-americano</td>"
            "<td>Câmara de Câmbio: liquidação no dia seguinte.</td></tr>"
        )
        partes.append("</table></div>")
    partes.append("</body></html>")
    return "".join(partes)


class _RespostaB3:
    def __init__(self, html: str) -> None:
        self.text = html
        self.url = URL_CALENDARIO_B3
        self.headers = {"Last-Modified": "Wed, 05 Aug 2026 12:00:00 GMT"}

    def raise_for_status(self) -> None:
        return None


class _SessaoB3:
    def __init__(self, html: str) -> None:
        self.html = html

    def get(self, *args, **kwargs):
        return _RespostaB3(self.html)


def test_importador_csv_entrega_contrato_do_engine() -> None:
    resultado = importar_lotes_tributarios(
        _csv_lotes(),
        nome_arquivo="lotes.csv",
        data_referencia=date(2026, 8, 5),
    )

    assert resultado.quantidade_lotes == 2
    assert resultado.saldo_total == pytest.approx(17_500)
    fundo = resultado.metadados_por_categoria["fundos_rf"]
    previdencia = resultado.metadados_por_categoria["prev_pgbl"]
    assert fundo["lotes_fundo_existentes"][0][
        "come_cotas_pago_historico"
    ] == pytest.approx(105)
    assert previdencia["lotes_previdencia_existentes"][0][
        "data_aplicacao"
    ] == "2019-08-10"


def test_importador_xlsx_usa_mesmo_contrato() -> None:
    tabela = pd.read_csv(io.BytesIO(_csv_lotes()))
    arquivo = io.BytesIO()
    with pd.ExcelWriter(arquivo, engine="openpyxl") as writer:
        tabela.to_excel(writer, index=False)

    resultado = importar_lotes_tributarios(
        arquivo.getvalue(),
        nome_arquivo="lotes.xlsx",
        data_referencia=date(2026, 8, 5),
    )

    assert resultado.quantidade_lotes == 2
    assert set(resultado.metadados_por_categoria) == {
        "fundos_rf",
        "prev_pgbl",
    }


def test_importador_rejeita_saldo_nao_reconciliado() -> None:
    arquivo = _csv_lotes().replace(b"105,10000", b"105,9999")
    with pytest.raises(ValueError, match="saldo importado"):
        importar_lotes_tributarios(
            arquivo,
            nome_arquivo="lotes.csv",
            data_referencia=date(2026, 8, 5),
        )


def test_mescla_nao_sobrescreve_lotes_digitados() -> None:
    with pytest.raises(ValueError, match="conflito"):
        mesclar_metadados_tributarios(
            {"fundos_rf": {"lotes_fundo_existentes": []}},
            {"fundos_rf": {"lotes_fundo_existentes": [{"saldo": 1}]}},
        )


def test_calendario_2026_e_confirmado_pela_b3() -> None:
    calendario = carregar_ano(2026)

    assert calendario.anos_confirmados == frozenset({2026})
    assert date(2026, 11, 20) in calendario.feriados
    assert not calendario.avisos


def test_calendario_futuro_e_explicitamente_provisorio() -> None:
    calendario = carregar_ano(2027)

    assert calendario.anos_provisorios == frozenset({2027})
    assert calendario.anos_confirmados == frozenset()
    assert calendario.avisos


def test_complemento_manual_confirma_ano_sem_esconder_feriado() -> None:
    calendario = carregar_intervalo(
        2027,
        2027,
        feriados_adicionais=["2027-05-31"],
        anos_confirmados_manualmente=[2027],
    )

    assert date(2027, 5, 31) in calendario.feriados
    assert calendario.anos_confirmados == frozenset({2027})
    assert not calendario.anos_provisorios


def test_projecao_avisa_quando_calendario_b3_futuro_nao_confirmado() -> None:
    projecao = projetar_come_cotas(
        10_000,
        0,
        0.10,
        18,
        data_referencia=date(2026, 8, 5),
        tipo_produto="fundo_longo_prazo",
    )

    assert 2027 in projecao.anos_sem_calendario_confirmado
    assert any("não foi confirmado" in item for item in projecao.premissas)


def test_registro_de_calendario_exige_fonte_oficial(tmp_path) -> None:
    with pytest.raises(ValueError, match="oficial da B3"):
        registrar_calendario(
            ano=2027,
            fonte="https://exemplo.test/calendario",
            datas=["2027-01-01"],
            destino=tmp_path,
        )

    extraido = extrair_calendario_b3(_html_b3_2026(), 2026)
    assert extraido is not None
    arquivo = registrar_calendario(
        ano=2026,
        fonte=URL_CALENDARIO_B3,
        datas=[item.isoformat() for item in extraido.datas],
        destino=tmp_path,
    )
    assert arquivo.name == "2026.json"
    assert '"status": "confirmado"' in arquivo.read_text(encoding="utf-8")


def test_registro_manual_rejeita_calendario_incompleto(tmp_path) -> None:
    with pytest.raises(ValueError, match="Quantidade anormal"):
        registrar_calendario(
            ano=2026,
            fonte=URL_CALENDARIO_B3,
            datas=["2026-01-01", "2026-12-25"],
            destino=tmp_path,
        )


def test_loader_revalida_json_confirmado(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("RECOMENDADOR_CALENDARIOS_CACHE_DIR", str(tmp_path))
    (tmp_path / "2026.json").write_text(
        json.dumps(
            {
                "ano": 2026,
                "status": "confirmado",
                "fonte": URL_CALENDARIO_B3,
                "dias_sem_negociacao": ["2026-01-01"],
            }
        ),
        encoding="utf-8",
    )
    carregar_ano.cache_clear()

    calendario = carregar_ano(2026)

    assert len(calendario.feriados) == 14
    assert calendario.anos_confirmados == frozenset({2026})
    assert any("inválido descartado" in item for item in calendario.avisos)


def test_parser_b3_ignora_horario_especial_e_feriado_estrangeiro() -> None:
    extraido = extrair_calendario_b3(_html_b3_2026(), 2026)

    assert extraido is not None
    validar_calendario_extraido(extraido, anos_permitidos=[2026, 2027])
    assert date(2026, 2, 18) not in extraido.datas
    assert len(extraido.datas) == 14


def test_sincronizacao_automatica_grava_cache_atomico(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("RECOMENDADOR_CALENDARIOS_CACHE_DIR", str(tmp_path))
    carregar_ano.cache_clear()

    resultados = sincronizar_calendarios_relevantes(
        data_referencia=date(2026, 8, 5),
        sessao=_SessaoB3(_html_b3_2026()),
    )

    assert resultados[0].status in {"atualizado", "sem_alteracao"}
    assert resultados[1].status == "nao_publicado"
    arquivo = tmp_path / "2026.json"
    dados = json.loads(arquivo.read_text(encoding="utf-8"))
    assert dados["status"] == "confirmado"
    assert dados["hash_fonte"]
    assert carregar_ano(2026).anos_confirmados == frozenset({2026})


def test_sincronizacao_rejeita_extracao_parcial_e_preserva_cache(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("RECOMENDADOR_CALENDARIOS_CACHE_DIR", str(tmp_path))
    cache = tmp_path / "2026.json"
    cache.write_text(
        json.dumps(
            {
                "ano": 2026,
                "status": "confirmado",
                "fonte": URL_CALENDARIO_B3,
                "dias_sem_negociacao": ["2026-01-01"],
            }
        ),
        encoding="utf-8",
    )
    conteudo_anterior = cache.read_bytes()

    resultados = sincronizar_calendarios_relevantes(
        data_referencia=date(2026, 8, 5),
        sessao=_SessaoB3(_html_b3_2026(remover="2026-05-01")),
    )

    assert resultados[0].status == "rejeitado"
    assert cache.read_bytes() == conteudo_anterior
