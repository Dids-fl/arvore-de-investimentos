"""Ferramentas de decisão: crises, faixas, saída, entrada parcelada, FGC e histórico."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from decisao import analises, diario, fgc, historico


def _indices(meses: int = 240, queda_em: str | None = "2008-09-30") -> pd.DataFrame:
    datas = pd.date_range("2000-01-31", periods=meses, freq="ME")
    tabela = pd.DataFrame(index=datas, columns=list(historico.SERIES), dtype=float)
    tabela["cdi"] = 0.01
    tabela["ipca_mais"] = 0.01
    # Bolsa com oscilação: sorteio fixo para o teste ser reprodutível.
    sorteio = np.random.default_rng(7).normal(0.01, 0.07, len(datas))
    tabela["ibov"] = sorteio
    tabela["usd"] = 0.0
    if queda_em:
        tabela.loc[queda_em, "ibov"] = -0.40  # crise: bolsa cai 40% em um mês
    return tabela


def test_base_embarcada_tem_meses_e_series() -> None:
    base = historico.ler_base()
    assert list(base.columns) == list(historico.SERIES)
    assert base.index.min() <= pd.Timestamp("2000-02-01")
    assert base["cdi"].notna().all()
    assert base["ibov"].abs().max() < 0.5


def test_carregar_sem_atualizar_nao_usa_internet(monkeypatch) -> None:
    monkeypatch.setattr(historico, "_baixar_recentes", lambda desde: pytest.fail("baixou"))
    assert len(historico.carregar_indices(atualizar=False)) > 200


def test_serie_ausente_usa_substituto_e_pesos_sao_normalizados() -> None:
    ind = _indices(queda_em=None)
    fii = historico.retornos_carteira({"fiis": 100}, ind)
    ibov = ind["ibov"].iloc[0]
    assert fii.iloc[0] == pytest.approx(0.5 * 0.01 + 0.5 * ibov)  # IPCA+ e Ibovespa
    metade = historico.retornos_carteira({"rf": 30, "rv": 30}, ind)
    assert metade.iloc[0] == pytest.approx(0.5 * 0.01 + 0.5 * ibov)


def test_crise_mostra_perda_em_reais_e_recuperacao() -> None:
    ind = _indices()
    resultado = analises.teste_crises({"rv": 50, "rf": 50}, 100_000, ind)
    crise_2008 = resultado["crises"][0]
    assert crise_2008["perda_maxima"] < -0.10
    assert crise_2008["perda_maxima_reais"] == pytest.approx(100_000 * crise_2008["perda_maxima"])
    assert crise_2008["meses_para_recuperar"] is not None
    assert resultado["pior_queda"]["perda"] <= crise_2008["perda_maxima"]
    so_cdi = analises.teste_crises({"rf_liq": 100}, 100_000, ind)
    assert all(c["perda_maxima"] == 0 for c in so_cdi["crises"])
    assert so_cdi["pior_queda"]["meses_para_recuperar"] == 0


def test_faixas_alargam_com_risco_e_estreitam_com_prazo() -> None:
    ind = _indices()
    renda_fixa = analises.faixas_retorno({"rf": 100}, 5, 0.12, ind, 10_000)
    bolsa_1a = analises.faixas_retorno({"rv": 100}, 1, 0.12, ind, 10_000)
    bolsa_5a = analises.faixas_retorno({"rv": 100}, 5, 0.12, ind, 10_000)

    def largura(f, nome="80%"):
        return f["faixas"][nome]["maximo"] - f["faixas"][nome]["minimo"]

    # Renda fixa ainda tem a incerteza do próprio CDI, mas é a menor.
    assert 0 < largura(renda_fixa) < largura(bolsa_5a)
    assert largura(bolsa_5a) < largura(bolsa_1a)
    f = bolsa_1a["faixas"]
    assert f["90%"]["minimo"] <= f["80%"]["minimo"] <= f["50%"]["minimo"] <= bolsa_1a["mediana"]
    assert bolsa_1a["mediana"] <= f["50%"]["maximo"] <= f["80%"]["maximo"] <= f["90%"]["maximo"]
    assert analises.faixas_retorno({"rv": 100}, 25, 0.12, ind)["prazo_limitado"]


def test_custo_de_sair_pgbl_tributa_o_valor_todo() -> None:
    ind = _indices(queda_em=None)
    vgbl, pgbl = (
        analises.custo_de_sair({cat: 100}, 100_000, 0.10, ind, horizontes=(12,))[0]["horizontes"][0]
        for cat in ("prev_vgbl", "prev_pgbl")
    )
    assert pgbl["ir_central"] == pytest.approx(0.35 * (100_000 + 10_000))
    assert vgbl["ir_central"] == pytest.approx(0.35 * 10_000)
    cdb = analises.custo_de_sair({"rf": 100}, 100_000, 0.10, ind, horizontes=(6, 24))[0]
    # 6 meses já passam de 180 dias: alíquota de 20%.
    assert cdb["horizontes"][0]["ir_central"] / (100_000 * (1.1**0.5 - 1)) == pytest.approx(0.20)
    # 24 meses já passam de 720 dias: alíquota de 15%.
    assert cdb["horizontes"][1]["ir_central"] / (100_000 * (1.1**2 - 1)) == pytest.approx(0.15)


def test_entrada_parcelada_protege_no_pior_caso() -> None:
    resultado = analises.entrada_parcelada({"rv": 100}, 100_000, _indices())
    uma_vez, seis, _doze = resultado["estrategias"]
    assert uma_vez["parcelas"] == 1 and seis["parcelas"] == 6
    assert seis["pior_caso"] > uma_vez["pior_caso"]
    assert resultado["faz_diferenca"]
    so_cdi = analises.entrada_parcelada({"rf": 100}, 100_000, _indices(queda_em=None))
    assert not so_cdi["faz_diferenca"]


def test_meses_por_extenso() -> None:
    assert analises.meses_por_extenso(None) == "ainda não recuperou"
    assert analises.meses_por_extenso(0) == "não caiu"
    assert analises.meses_por_extenso(14) == "1 ano e 2 meses"
    assert analises.meses_por_extenso(1) == "1 mês"


def test_fgc_divide_por_banco_e_avisa_teto_global() -> None:
    pequeno = fgc.analisar_garantias({"rf": 100}, 200_000)
    assert pequeno["alertas"] == []
    grande = fgc.analisar_garantias({"rf": 100}, 600_000, rendimento_ate_vencimento=0.1)
    assert grande["instituicoes_necessarias"] == 3  # 660 mil no vencimento
    acima_do_teto = fgc.analisar_garantias({"rf": 100}, 1_500_000)
    assert any("R$ 1 milhão" in a for a in acima_do_teto["alertas"])
    misto = fgc.analisar_garantias({"rv": 60, "prev_vgbl": 40}, 100_000)
    assert misto["grupos"]["sem_garantia"] == pytest.approx(60_000)
    assert len(misto["alertas"]) == 2


def test_diario_salva_lista_avalia_e_remove(tmp_path) -> None:
    arquivo = tmp_path / "decisoes.jsonl"
    analise = {
        "data_referencia": "2005-06-15",
        "respostas": {"cap_inicial": 50_000},
        "resultado": {
            "portfolio": {"rf": 100, "rv": 0},
            "nivel_risco_display": "Conservador",
            "taxa_perfil": 0.13,
            "taxa_pess": 0.10,
        },
    }
    registro = diario.registro_da_analise(analise, " primeira ")
    assert registro["carteira"] == {"rf": 100.0}
    diario.salvar(registro, arquivo)
    arquivo.open("a").write("linha quebrada\n")
    lidos = diario.listar(arquivo)
    assert [r["id"] for r in lidos] == [registro["id"]]
    assert lidos[0]["observacao"] == "primeira"

    avaliacao = diario.avaliar(lidos[0], _indices(queda_em=None))
    assert avaliacao["meses"] > 12
    assert avaliacao["realizado"] == pytest.approx(1.01 ** avaliacao["meses"] - 1)
    assert avaliacao["situacao"] == "dentro da faixa prevista"
    assert diario.remover(registro["id"], arquivo)
    assert diario.listar(arquivo) == []


def test_carregar_completa_meses_recentes_e_usa_cache(monkeypatch, tmp_path) -> None:
    base = historico.ler_base()
    ultimo = base.index.max()
    novos = pd.DataFrame(
        {"cdi": [0.01, 0.01], "ibov": [0.02, -0.03]},
        index=pd.date_range(ultimo + pd.offsets.MonthEnd(1), periods=2, freq="ME"),
    )
    chamadas = []

    def baixar(desde):
        chamadas.append(desde)
        return novos

    monkeypatch.setattr(historico, "_baixar_recentes", baixar)
    monkeypatch.setattr(historico, "CACHE_RECENTES", tmp_path / "recentes.csv")
    hoje = ultimo + pd.offsets.MonthEnd(3)  # dois meses fechados depois da base
    completo = historico.carregar_indices(hoje=hoje)
    assert len(completo) == len(base) + 2
    assert completo["ibov"].iloc[-1] == pytest.approx(-0.03)
    assert pd.isna(completo["fii"].iloc[-1])  # sem dado: substituto na simulação
    historico.carregar_indices(hoje=hoje)
    assert len(chamadas) == 1  # a segunda leitura veio do cache
    # Base em dia: não consulta a internet.
    assert len(historico.carregar_indices(hoje=ultimo + pd.Timedelta(5, unit="D"))) == len(base)
    assert len(chamadas) == 1


def test_series_usadas_indica_inicio_dos_dados() -> None:
    base = historico.ler_base()
    usadas = historico.series_usadas({"fiis": 50, "rv_cripto": 50}, base)
    assert usadas["fii"].endswith("2019") or usadas["fii"].endswith("2020")
    if base["btc"].isna().all():
        assert usadas["btc"] == "sem dado (substituto)"


def test_btc_mercado_bitcoin_junta_blocos_anuais() -> None:
    class Resposta:
        def __init__(self, dados):
            self._dados = dados

        def raise_for_status(self):
            return None

        def json(self):
            return self._dados

    class Sessao:
        def __init__(self):
            self.chamadas = []

        def get(self, url, params, timeout):
            self.chamadas.append(params)
            inicio = params["from"]
            return Resposta({"t": [inicio, inicio + 86400], "c": ["100.5", "101"]})

    sessao = Sessao()
    serie = historico.btc_mercado_bitcoin("2024-01-01", sessao=sessao)
    assert len(sessao.chamadas) >= 2  # um bloco por ano
    assert serie.iloc[0] == pytest.approx(100.5)
    assert serie.index.is_monotonic_increasing
    lista = historico._fechamentos_candles([{"timestamp": 1700000000, "close": 5}])
    assert lista.iloc[0] == 5
    with pytest.raises(ValueError):
        historico._fechamentos_candles({"erro": "x"})
