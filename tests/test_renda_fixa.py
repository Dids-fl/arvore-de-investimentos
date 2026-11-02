"""Testes determinísticos do coletor e ranker de renda fixa."""

from __future__ import annotations

import datetime as dt

import pytest
import requests

from renda_fixa import coletor, ranker
from utils.exceptions import DadosIndisponiveisError


class RespostaFalsa:
    """Resposta HTTP mínima usada pelos testes do coletor."""

    def __init__(
        self,
        *,
        json_data=None,
        text: str = "",
        erro: Exception | None = None,
    ) -> None:
        self._json_data = json_data
        self.text = text
        self._erro = erro

    def raise_for_status(self) -> None:
        if self._erro is not None:
            raise self._erro

    def json(self):
        return self._json_data


@pytest.fixture
def titulos_tesouro() -> list[dict]:
    hoje = dt.datetime.now(dt.UTC).date()
    return [
        {
            "nome": "Tesouro Selic 2029",
            "taxa": 0.0015,
            "vencimento": (hoje + dt.timedelta(days=700)).isoformat(),
            "tipo": "SELIC",
            "data_base": hoje.isoformat(),
        },
        {
            "nome": "Tesouro IPCA+ 2035",
            "taxa": 0.065,
            "vencimento": (hoje + dt.timedelta(days=3000)).isoformat(),
            "tipo": "IPCA",
            "data_base": hoje.isoformat(),
        },
    ]


REFERENCIAS_TESTE = {
    "selic_atual": 0.14,
    "ipca_atual": 0.045,
    "selic_por_ano": {2026: 0.14, 2027: 0.12, 2028: 0.10},
    "ipca_por_ano": {2026: 0.05, 2027: 0.04},
}


@pytest.fixture(autouse=True)
def _referencias_fixas(monkeypatch):
    """Selic/IPCA esperados fixos: o ranker não lê o cache do usuário."""
    monkeypatch.setattr(ranker, "_referencias_mercado", lambda: dict(REFERENCIAS_TESTE))


@pytest.fixture
def fontes_ranker_mockadas(
    monkeypatch,
    titulos_tesouro,
) -> None:
    monkeypatch.setattr(
        ranker,
        "coletar_tesouro",
        lambda: titulos_tesouro,
    )


def test_coletar_indicadores_usa_cdi_oficial(monkeypatch) -> None:
    respostas = {
        "bcdata.sgs.432/": RespostaFalsa(json_data=[{"valor": "14.25"}]),
        "bcdata.sgs.4389/": RespostaFalsa(json_data=[{"valor": "14.15"}]),
    }

    def falso_get(url, *a, **k):
        return next(r for chave, r in respostas.items() if chave in url)

    monkeypatch.setattr(coletor.requests, "get", falso_get)

    selic, cdi = coletor.coletar_indicadores()

    assert selic == pytest.approx(0.1425)
    assert cdi == pytest.approx(0.1415)


def test_coletar_indicadores_estima_cdi_se_serie_falhar(monkeypatch) -> None:
    def falso_get(url, *a, **k):
        if "bcdata.sgs.432/" in url:
            return RespostaFalsa(json_data=[{"valor": "14.25"}])
        return RespostaFalsa(erro=requests.RequestException("fora do ar"))

    monkeypatch.setattr(coletor.requests, "get", falso_get)

    selic, cdi = coletor.coletar_indicadores()

    assert selic == pytest.approx(0.1425)
    assert cdi == pytest.approx(0.1415)


@pytest.mark.parametrize(
    "resposta",
    [
        RespostaFalsa(json_data=[]),
        RespostaFalsa(json_data=[{"valor": "inválido"}]),
        RespostaFalsa(
            erro=requests.RequestException("fonte indisponível")
        ),
    ],
)
def test_coletar_indicadores_rejeita_fonte_invalida(
    monkeypatch,
    resposta,
) -> None:
    monkeypatch.setattr(
        coletor.requests,
        "get",
        lambda *args, **kwargs: resposta,
    )

    with pytest.raises(DadosIndisponiveisError):
        coletor.coletar_indicadores()


def test_coletar_tesouro_interpreta_package_show(monkeypatch) -> None:
    metadados = RespostaFalsa(
        json_data={
            "success": True,
            "result": {
                "resources": [
                    {
                        "format": "CSV",
                        "url": (
                            "https://exemplo.test/"
                            "PrecoTaxaTesouroDireto.csv"
                        ),
                    }
                ]
            },
        }
    )
    csv = RespostaFalsa(
        text=(
            "Data Base;Tipo Titulo;Taxa Compra Manha;"
            "Data Vencimento\n"
            "30/07/2026;Tesouro Selic 2029;0,15;"
            "01/03/2029\n"
            "29/07/2026;Tesouro Selic 2029;0,14;"
            "01/03/2029\n"
        )
    )
    respostas = iter([metadados, csv])
    monkeypatch.setattr(
        coletor.requests,
        "get",
        lambda *args, **kwargs: next(respostas),
    )

    titulos = coletor.coletar_tesouro()

    assert len(titulos) == 1
    assert titulos[0]["nome"] == "Tesouro Selic 2029"
    assert titulos[0]["taxa"] == pytest.approx(0.0015)
    assert titulos[0]["vencimento"] == "01/03/2029"
    assert titulos[0]["tipo"] == "SELIC"
    assert titulos[0]["data_base"] == "2026-07-30"


def test_renda_mais_e_educa_mais_sao_indexados_ao_ipca(monkeypatch) -> None:
    metadados = RespostaFalsa(
        json_data={
            "success": True,
            "result": {
                "resources": [
                    {
                        "format": "CSV",
                        "url": "https://exemplo.test/PrecoTaxaTesouroDireto.csv",
                    }
                ]
            },
        }
    )
    csv = RespostaFalsa(
        text=(
            "Data Base;Tipo Titulo;Taxa Compra Manha;Data Vencimento\n"
            "30/07/2026;Tesouro Renda+ Aposentadoria Extra;7,10;15/12/2049\n"
            "30/07/2026;Tesouro Educa+;7,05;15/12/2035\n"
        )
    )
    respostas = iter([metadados, csv])
    monkeypatch.setattr(coletor.requests, "get", lambda *a, **k: next(respostas))

    titulos = coletor.coletar_tesouro()

    assert {titulo["tipo"] for titulo in titulos} == {"IPCA"}
    produtos = ranker._processar_tesouro(titulos)
    assert {produto["ticker"] for produto in produtos} == {
        "TD-RENDA+-2049",
        "TD-EDUCA+-2035",
    }


@pytest.mark.parametrize(
    "metadados",
    [
        {"success": False},
        {"success": True, "result": {"resources": []}},
    ],
)
def test_coletar_tesouro_sem_recurso_retorna_none(
    monkeypatch,
    metadados,
) -> None:
    resposta = RespostaFalsa(json_data=metadados)
    monkeypatch.setattr(
        coletor.requests,
        "get",
        lambda *args, **kwargs: resposta,
    )
    assert coletor.coletar_tesouro() is None


def test_coletar_tesouro_em_erro_http_retorna_none(
    monkeypatch,
) -> None:
    resposta = RespostaFalsa(
        erro=requests.RequestException("fora do ar")
    )
    monkeypatch.setattr(
        coletor.requests,
        "get",
        lambda *args, **kwargs: resposta,
    )
    assert coletor.coletar_tesouro() is None


def test_rankear_rf_retorna_contrato_ordenado(
    fontes_ranker_mockadas,
) -> None:
    recomendacoes = ranker.rankear_rf(perfil=2, limite=2)

    assert len(recomendacoes) == 2
    assert recomendacoes[0]["score"] >= recomendacoes[1]["score"]
    assert {
        "ticker",
        "nome",
        "emissor",
        "tipo",
        "taxa_bruta",
        "vencimento",
        "garantia",
        "liquidez",
        "ir",
        "isento_ir",
        "prazo_dias",
        "fonte",
        "score",
    }.issubset(recomendacoes[0])
    assert recomendacoes[0]["emissor"] == "Tesouro Nacional"
    assert 0 <= recomendacoes[0]["score"] <= 10
    assert len({item["ticker"] for item in recomendacoes}) == 2
    assert all("Regressivo" in item["ir"] for item in recomendacoes)


def test_rankear_rf_respeita_limite_e_perfis(
    fontes_ranker_mockadas,
) -> None:
    for perfil in (1, 2, 3):
        resultado = ranker.rankear_rf(perfil=perfil, limite=1)
        assert len(resultado) == 1
        assert 0 <= resultado[0]["score"] <= 10


def test_rankear_rf_sem_titulos_retorna_lista_vazia(
    monkeypatch,
) -> None:
    monkeypatch.setattr(ranker, "coletar_tesouro", list)

    assert ranker.rankear_rf() == []


def test_rankear_rf_nao_depende_da_selic(
    monkeypatch,
    titulos_tesouro,
) -> None:
    def falhar():
        raise AssertionError(
            "O ranker não deveria consultar SELIC/CDI."
        )

    monkeypatch.setattr(coletor, "coletar_indicadores", falhar)
    monkeypatch.setattr(
        ranker,
        "coletar_tesouro",
        lambda: titulos_tesouro,
    )

    resultado = ranker.rankear_rf()

    assert resultado

def test_calcular_prazo_dias_aceita_formatos_e_fallback() -> None:
    futuro = dt.datetime.now(dt.UTC).date() + dt.timedelta(days=100)

    assert 99 <= ranker._calcular_prazo_dias(
        futuro.strftime("%d/%m/%Y")
    ) <= 101
    assert 99 <= ranker._calcular_prazo_dias(
        futuro.strftime("%Y-%m-%d")
    ) <= 101
    assert ranker._calcular_prazo_dias("formato inválido") == 9999
    assert ranker._calcular_prazo_dias(None) == 9999


def test_calcular_score_varia_com_perfil() -> None:
    produto = {
        "taxa_bruta": 0.12,
        "garantia": "Governo Federal",
        "liquidez": "D+1",
        "prazo_dias": 1096,
        "tipo": "Tesouro Prefixado",
    }

    score_conservador = ranker._calcular_score(produto, perfil=1)
    score_moderado = ranker._calcular_score(produto, perfil=2)
    score_agressivo = ranker._calcular_score(produto, perfil=3)

    assert 0 <= score_conservador <= 10
    assert score_conservador <= score_moderado <= score_agressivo


def test_ranker_prioriza_vencimento_compativel_com_horizonte(
    monkeypatch,
) -> None:
    titulos = [
        {
            "nome": "Tesouro IPCA+",
            "taxa": 0.07,
            "vencimento": "15/08/2026",
            "tipo": "IPCA",
        },
        {
            "nome": "Tesouro IPCA+",
            "taxa": 0.065,
            "vencimento": "15/08/2035",
            "tipo": "IPCA",
        },
    ]
    monkeypatch.setattr(ranker, "coletar_tesouro", lambda: titulos)

    resultado = ranker.rankear_rf(
        perfil=2,
        limite=2,
        prazo_anos=10,
        data_referencia="2026-08-06",
    )

    assert resultado[0]["ticker"] == "TD-IPCA-2035"
    assert resultado[0]["compatibilidade_prazo"] > resultado[1][
        "compatibilidade_prazo"
    ]


def test_ranker_remove_titulo_vencido(monkeypatch) -> None:
    titulos = [
        {
            "nome": "Tesouro Prefixado",
            "taxa": 0.13,
            "vencimento": "01/01/2026",
            "tipo": "PREFIXADO",
        }
    ]
    monkeypatch.setattr(ranker, "coletar_tesouro", lambda: titulos)

    assert ranker.rankear_rf(
        data_referencia="2026-08-06",
    ) == []


def test_taxa_nominal_equivalente_usa_focus() -> None:
    ipca = ranker.taxa_nominal_equivalente(
        {"taxa_bruta": 0.07, "tipo": "IPCA", "vencimento": "15/05/2027"},
        REFERENCIAS_TESTE,
        "2026-11-02",
    )
    # média do IPCA esperado em 2026 e 2027: 4,5%
    assert ipca == pytest.approx(1.07 * 1.045 - 1)

    selic = ranker.taxa_nominal_equivalente(
        {"taxa_bruta": 0.001, "tipo": "SELIC", "vencimento": "01/03/2031"},
        REFERENCIAS_TESTE,
        "2026-11-02",
    )
    # 2026–2031: 14%, 12%, 10% e o último ponto (10%) repetido até 2031
    esperado = (0.14 + 0.12 + 0.10 * 4) / 6
    assert selic == pytest.approx((1 + esperado) * 1.001 - 1)

    prefixado = ranker.taxa_nominal_equivalente(
        {"taxa_bruta": 0.13, "tipo": "Prefixado", "vencimento": "01/01/2030"},
        REFERENCIAS_TESTE,
        "2026-11-02",
    )
    assert prefixado == pytest.approx(0.13)


def test_tesouro_selic_compete_com_os_demais(monkeypatch) -> None:
    """Antes, o Selic entrava só com o ágio (0,1%) e ficava sempre em último."""
    titulos = [
        {"nome": "Tesouro Selic 2028", "taxa": 0.001, "vencimento": "01/03/2028", "tipo": "SELIC"},
        {"nome": "Tesouro Prefixado 2028", "taxa": 0.115, "vencimento": "01/01/2028", "tipo": "Prefixado"},
    ]
    monkeypatch.setattr(ranker, "coletar_tesouro", lambda: titulos)

    resultado = ranker.rankear_rf(perfil=1, limite=2, data_referencia="2026-11-02")

    assert resultado[0]["ticker"] == "TD-SELIC-2028"
    assert resultado[0]["taxa_nominal_estimada"] > 0.12


def test_sem_referencia_de_mercado_classe_fica_indisponivel(monkeypatch, titulos_tesouro) -> None:
    def falhar():
        raise RuntimeError("BCB fora do ar")

    monkeypatch.setattr(ranker, "_referencias_mercado", falhar)
    monkeypatch.setattr(ranker, "coletar_tesouro", lambda: titulos_tesouro)

    with pytest.raises(DadosIndisponiveisError):
        ranker.rankear_rf()
