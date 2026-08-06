"""Testes da rastreabilidade, reconciliação e revisão tributárias."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from validacao.tributacao.auditar_fontes import (
    ARQUIVO_FONTES,
    auditar_disponibilidade_online,
    auditar_registro,
    carregar_registro,
)
from validacao.tributacao.reconciliar_documentos import (
    reconciliar_documento,
)
from validacao.tributacao.registrar_revisao import (
    criar_registro,
    verificar_registro,
)


def test_registro_de_fontes_cobre_validadores() -> None:
    relatorio = auditar_registro(carregar_registro(ARQUIVO_FONTES))
    assert relatorio["valido"] is True
    assert relatorio["problemas"] == []
    assert relatorio["resumo"]["utilizadas"] > 0


def test_auditoria_rejeita_fonte_nao_oficial() -> None:
    registro = carregar_registro(ARQUIVO_FONTES)
    registro["fontes"][0]["url"] = "https://exemplo.invalid/regra"
    relatorio = auditar_registro(registro)
    assert relatorio["valido"] is False
    assert any("não oficial" in item for item in relatorio["problemas"])


def test_auditoria_online_registra_hash_sem_rede() -> None:
    class Resposta:
        def __init__(self) -> None:
            self.status_code = 200
            self.url = "https://www.gov.br/fonte"
            self.headers = {"ETag": "abc"}
            self.content = b"conteudo oficial de teste"

        def raise_for_status(self) -> None:
            return None

    class Sessao:
        def get(self, *args, **kwargs):
            return Resposta()

    registro = {"fontes": [{"id": "fonte", "url": "https://www.gov.br"}]}
    relatorio = auditar_disponibilidade_online(registro, session=Sessao())
    assert relatorio["disponiveis"] == 1
    assert len(relatorio["resultados"][0]["sha256_conteudo"]) == 64


def test_reconciliacao_anonimizada_confere(tmp_path: Path) -> None:
    origem = Path("modelos/casos_tributarios_reais_anonimizados.json")
    copia = tmp_path / "casos.json"
    copia.write_bytes(origem.read_bytes())
    relatorio = reconciliar_documento(copia)
    assert relatorio["resumo"]["CONCILIADO"] == 1
    assert relatorio["resumo"]["DIVERGENTE"] == 0


def test_reconciliacao_bloqueia_dados_pessoais(tmp_path: Path) -> None:
    origem = json.loads(
        Path("modelos/casos_tributarios_reais_anonimizados.json").read_text(
            encoding="utf-8"
        )
    )
    origem["casos"][0]["documento"]["cpf"] = "000.000.000-00"
    caminho = tmp_path / "com_pii.json"
    caminho.write_text(json.dumps(origem), encoding="utf-8")
    with pytest.raises(ValueError, match="dados pessoais"):
        reconciliar_documento(caminho)


def test_registro_de_revisao_detecta_relatorio_alterado(
    tmp_path: Path,
) -> None:
    relatorio = tmp_path / "relatorio.json"
    relatorio.write_text('{"resultado": "ok"}\n', encoding="utf-8")
    registro = criar_registro(
        relatorio,
        revisor="Revisor de teste",
        credencial="OAB",
        registro_profissional="UF 000000",
        decisao="aprovado_com_ressalvas",
        escopo="casos dourados",
        ressalvas=["Exemplo automatizado."],
        declarou_responsabilidade=True,
    )
    assert verificar_registro(registro, relatorio) is True
    relatorio.write_text('{"resultado": "alterado"}\n', encoding="utf-8")
    assert verificar_registro(registro, relatorio) is False


def test_aprovacao_exige_declaracao_de_responsabilidade(
    tmp_path: Path,
) -> None:
    relatorio = tmp_path / "relatorio.json"
    relatorio.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="responsabilidade"):
        criar_registro(
            relatorio,
            revisor="Revisor de teste",
            credencial="CRC",
            registro_profissional="UF 000000",
            decisao="aprovado_com_ressalvas",
            escopo="casos dourados",
            ressalvas=[],
            declarou_responsabilidade=False,
        )
