# tests/test_estruturados.py
from datetime import date, timedelta

from produtos_estruturados.filtros import elegivel, filtrar_para_ranking
from produtos_estruturados.indicadores import (
    _isento_ir,
    _prazo_dias,
    montar_indicadores,
)
from produtos_estruturados.ranker import (
    PERFIL_AGRESSIVO,
    PERFIL_CONSERVADOR,
    _calcular_score,
)


def _ativo_exemplo(**overrides):
    base = {
        "tipo": "DEBENTURE",
        "identificador": "Empresa X",
        "isin": "BRDEBEXEMPLO",
        "vencimento": (date.today() + timedelta(days=900)).isoformat(),
        "prazo_dias": 900,
        "isento_ir": True,
        "taxa": 9.5,
        "score_liquidez": 5.0,
        "tem_negociacao_recente": True,
    }
    base.update(overrides)
    return base


def test_isento_ir_cra_cri_sempre_true():
    assert _isento_ir("CRA", {}) is True
    assert _isento_ir("CRI", {}) is True


def test_isento_ir_debenture_depende_do_registro():
    assert _isento_ir("DEBENTURE", {"Especie": "Comum"}) is False
    assert _isento_ir("DEBENTURE", {"Especie": "Incentivada Lei 12.431"}) is True


def test_isento_ir_debenture_schema_real_b3():
    # Schema confirmado em produção (jul/2026): coluna dedicada Sim/Não
    assert _isento_ir("DEBENTURE", {"Destinação do recurso (Lei 12.431)": "Não"}) is False
    assert _isento_ir("DEBENTURE", {"Destinação do recurso (Lei 12.431)": "Sim"}) is True


def test_prazo_dias_calcula_a_partir_da_data():
    venc = (date.today() + timedelta(days=365)).isoformat()
    assert 360 <= _prazo_dias(venc) <= 366


def test_filtro_descarta_prazo_curto_demais():
    ativo = _ativo_exemplo(prazo_dias=30)
    assert not elegivel(ativo, perfil=2)


def test_filtro_conservador_exige_mais_liquidez():
    ativo_pouco_liquido = _ativo_exemplo(score_liquidez=1.0)
    assert not elegivel(ativo_pouco_liquido, perfil=PERFIL_CONSERVADOR)
    assert elegivel(ativo_pouco_liquido, perfil=PERFIL_AGRESSIVO)


def test_ativo_sem_prazo_e_sempre_descartado_em_qualquer_perfil():
    # Sem fallback/mock: se o cadastro (CRA, CRI ou debênture) não trouxe
    # data de vencimento, o ativo é descartado em qualquer perfil — não
    # existe mais exceção especial para CRA/CRI "sem cadastro oficial".
    ativo = _ativo_exemplo(tipo="CRA", prazo_dias=None)
    assert not elegivel(ativo, perfil=1)
    assert not elegivel(ativo, perfil=2)
    assert not elegivel(ativo, perfil=3)


def test_taxa_suspeita_descartada_no_moderado_mas_visivel_no_agressivo():
    # Caso real de produção: CRA com taxa equivalente de 46,58% a.a.
    # (outlier / possível erro de dado) no topo do ranking moderado.
    ativo = _ativo_exemplo(taxa=46.58, taxa_suspeita=True)
    assert not elegivel(ativo, perfil=1)
    assert not elegivel(ativo, perfil=2)
    assert elegivel(ativo, perfil=3)


def test_montar_indicadores_gera_um_registro_por_ativo():
    cadastro = {
        "cras": [{"razaoSocial": "CRA Teste", "isin": "BRCRA01", "dataVencimento": "2027-01-01"}],
        "cris": [],
        "debentures": [{"Emissor": "Empresa Y", "CodigoISIN": "BRDEB01", "DataVencimento": "2028-01-01"}],
    }
    negociacao = {
        "BRCRA01": {"taxa_ultima": 8.2, "n_negocios": 3, "volume_total": 1_000_000},
    }
    ativos = montar_indicadores(cadastro, negociacao)
    assert len(ativos) == 2
    tipos = {a["tipo"] for a in ativos}
    assert tipos == {"CRA", "DEBENTURE"}


def test_score_penaliza_ativo_sem_negociacao_recente():
    com_negociacao = _ativo_exemplo(tem_negociacao_recente=True)
    sem_negociacao = _ativo_exemplo(tem_negociacao_recente=False)
    score_com, _ = _calcular_score(com_negociacao, perfil=2)
    score_sem, _ = _calcular_score(sem_negociacao, perfil=2)
    assert score_sem < score_com