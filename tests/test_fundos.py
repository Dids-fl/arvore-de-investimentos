# tests/test_fundos.py
"""
Testes completos para o módulo de Fundos de Investimento.
"""

import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import pandas as pd
import numpy as np
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

# ---------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------

@pytest.fixture
def sample_cotas():
    """Gera uma série de cotas simulada para testes."""
    np.random.seed(42)
    datas = pd.date_range("2024-01-01", periods=252, freq="B")
    cotas = 100 * (1 + np.random.normal(0.0005, 0.01, 252)).cumprod()
    return cotas, datas


@pytest.fixture
def sample_df_informe():
    """Gera um DataFrame simulando o informe diário de um fundo."""
    np.random.seed(42)
    datas = pd.date_range("2024-01-01", periods=252, freq="B")
    cotas = 100 * (1 + np.random.normal(0.0005, 0.01, 252)).cumprod()
    pl = cotas * 1000000  # patrimônio proporcional
    captacao = np.random.uniform(0, 100000, 252)
    resgate = np.random.uniform(0, 80000, 252)
    cotistas = np.random.randint(100, 1000, 252)

    df = pd.DataFrame({
        "CNPJ_Classe": ["00.000.000/0001-00"] * 252,
        "Data_Competencia": datas,
        "Valor_Cota": cotas,
        "Patrimonio_Liquido": pl,
        "Captacao_Dia": captacao,
        "Resgate_Dia": resgate,
        "Numero_Cotistas": cotistas,
    })
    return df


@pytest.fixture
def sample_df_cadastro():
    """Gera um DataFrame simulando o cadastro de fundos."""
    return pd.DataFrame({
        "CNPJ_Classe": ["00.000.000/0001-00", "00.000.000/0001-01"],
        "Denominacao_Social": ["Fundo Teste A", "Fundo Teste B"],
        "Situacao": ["EM FUNCIONAMENTO NORMAL", "EM FUNCIONAMENTO NORMAL"],
        "Classificacao_Anbima": ["Renda Fixa", "Ações"],
        "Tipo_Classe": ["Fundo Aberto", "Fundo Aberto"],
        "Patrimonio_Liquido": [500000000, 200000000],
    })


# ---------------------------------------------------------------------
# Testes de Utils
# ---------------------------------------------------------------------

class TestUtils:
    def test_to_float(self):
        from fundos.utils import to_float
        assert to_float(10.5) == 10.5
        assert to_float("10.5") == 10.5
        assert to_float(None) == 0.0
        assert to_float(float("nan")) == 0.0

    def test_serie_retorno(self):
        from fundos.utils import serie_retorno
        cotas = pd.Series([100, 101, 102, 101])
        ret = serie_retorno(cotas)
        expected = pd.Series([0.01, 0.00990099, -0.00980392])
        pd.testing.assert_series_equal(ret, expected, rtol=1e-6)

    def test_retorno(self):
        from fundos.utils import retorno
        cotas = pd.Series([100, 101, 102, 101])
        assert retorno(cotas) == 0.01  # (101 - 100) / 100

    def test_retorno_periodo(self):
        from fundos.utils import retorno_periodo
        cotas = pd.Series([100, 101, 102, 103, 104, 105])
        # Últimos 2 dias: 105 / 104 - 1
        assert retorno_periodo(cotas, 2) == pytest.approx(105/104 - 1, rel=1e-6)

    def test_cagr(self, sample_cotas):
        from fundos.utils import cagr
        cotas, datas = sample_cotas
        # CAGR deve ser aproximadamente o retorno médio anual
        result = cagr(cotas, datas)
        assert result is not None
        assert 0.0 < result < 0.5  # entre 0% e 50% para dados simulados

    def test_volatilidade(self, sample_cotas):
        from fundos.utils import volatilidade
        cotas, _ = sample_cotas
        vol = volatilidade(cotas)
        assert vol is not None
        assert 0.0 < vol < 0.5  # volatilidade razoável

    def test_drawdown(self, sample_cotas):
        from fundos.utils import drawdown
        cotas, _ = sample_cotas
        dd = drawdown(cotas)
        assert dd is not None
        assert dd < 0  # drawdown é negativo


# ---------------------------------------------------------------------
# Testes de Indicadores
# ---------------------------------------------------------------------

class TestIndicadores:
    def test_calcular_indicadores_df(self, sample_df_informe):
        from fundos.indicadores import calcular_indicadores_df
        result = calcular_indicadores_df(sample_df_informe)
        assert result is not None
        assert "retorno_12m" in result
        assert "cagr" in result
        assert "volatilidade" in result
        assert "drawdown" in result
        assert "fluxo_liquido" in result
        assert "patrimonio_atual" in result
        assert "dias_historico" in result

    def test_calcular_indicadores_df_com_cadastro(self, sample_df_informe, sample_df_cadastro):
        from fundos.indicadores import calcular_indicadores_df
        cadastro = sample_df_cadastro.iloc[0].to_dict()
        result = calcular_indicadores_df(sample_df_informe, cadastro)
        assert result is not None
        assert result["cnpj"] == cadastro["CNPJ_Classe"]
        assert result["nome"] == cadastro["Denominacao_Social"]
        assert result["classe"] == cadastro["Classificacao_Anbima"]


# ---------------------------------------------------------------------
# Testes de Sharpe/Sortino
# ---------------------------------------------------------------------

class TestSharpeSortino:
    def test_calcular_sharpe(self, sample_cotas):
        from fundos.sharpe_sortino import calcular_sharpe
        cotas, datas = sample_cotas
        sharpe = calcular_sharpe(cotas, datas, taxa_livre_risco=0.105)
        # Sharpe deve ser um número razoável (pode ser negativo)
        assert sharpe is not None
        assert -2.0 < sharpe < 5.0

    def test_calcular_sortino(self, sample_cotas):
        from fundos.sharpe_sortino import calcular_sortino
        cotas, datas = sample_cotas
        sortino = calcular_sortino(cotas, datas, taxa_livre_risco=0.105)
        assert sortino is not None
        assert -2.0 < sortino < 5.0

    def test_calcular_indicadores_risco(self, sample_cotas):
        from fundos.sharpe_sortino import calcular_indicadores_risco
        cotas, datas = sample_cotas
        risco = calcular_indicadores_risco(cotas, datas)
        assert "sharpe" in risco
        assert "sortino" in risco


# ---------------------------------------------------------------------
# Testes do Ranker (com dados simulados)
# ---------------------------------------------------------------------

class TestRanker:
    @pytest.fixture
    def mock_coletor(self, sample_df_cadastro, sample_df_informe):
        """Mock dos coletores para testar o ranker."""
        with patch("fundos.ranker.listar_fundos_ativos") as mock_listar:
            mock_listar.return_value = sample_df_cadastro
            with patch("fundos.ranker.listar_historicos") as mock_historico:
                # Duplica os dados para dois CNPJs
                df1 = sample_df_informe.copy()
                df2 = sample_df_informe.copy()
                df1["CNPJ_Classe"] = "00.000.000/0001-00"
                df2["CNPJ_Classe"] = "00.000.000/0001-01"
                df_combined = pd.concat([df1, df2], ignore_index=True)
                mock_historico.return_value = df_combined
                yield

    def test_calcular_score(self):
        from fundos.ranker import calcular_score
        indicadores = {
            "retorno_12m": 0.15,
            "volatilidade": 0.12,
            "drawdown": -0.08,
            "fluxo_liquido": 10000000,
            "patrimonio_atual": 500000000,
        }
        score = calcular_score(indicadores, perfil=2, incluir_sharpe_sortino=False)
        assert "score" in score
        assert 0 <= score["score"] <= 10

    def test_calcular_score_com_sharpe_sortino(self):
        from fundos.ranker import calcular_score
        indicadores = {
            "retorno_12m": 0.15,
            "volatilidade": 0.12,
            "drawdown": -0.08,
            "fluxo_liquido": 10000000,
            "patrimonio_atual": 500000000,
            "sharpe": 0.8,
            "sortino": 1.2,
        }
        score = calcular_score(indicadores, perfil=2, incluir_sharpe_sortino=True)
        assert "sharpe" in score
        assert "sortino" in score

    def test_rankear_fundos(self, mock_coletor):
        from fundos.ranker import rankear_fundos
        resultado = rankear_fundos(perfil=2, limite=3, incluir_sharpe_sortino=False)
        assert isinstance(resultado, list)
        assert len(resultado) <= 3
        if resultado:
            assert "cnpj" in resultado[0]
            assert "nome" in resultado[0]
            assert "score" in resultado[0]

    def test_top_fundos(self, mock_coletor):
        from fundos.ranker import top_fundos
        resultado = top_fundos(quantidade=2, perfil=1)
        assert isinstance(resultado, list)
        assert len(resultado) <= 2


# ---------------------------------------------------------------------
# Testes de Integração (com dados reais, marcado como slow)
# ---------------------------------------------------------------------

@pytest.mark.slow
class TestIntegracao:
    def test_cadastro_coletor(self):
        """Testa o download e carregamento do cadastro (pode ser lento)."""
        from fundos.cadastro_coletor import listar_fundos_ativos
        df = listar_fundos_ativos()
        assert isinstance(df, pd.DataFrame)
        if not df.empty:
            assert "CNPJ_Classe" in df.columns
            assert "Denominacao_Social" in df.columns

    def test_informe_coletor(self):
        """Testa o download e carregamento do informe diário."""
        from fundos.informe_diario_coletor import buscar_historico
        # Usa um CNPJ conhecido (pode falhar se não existir)
        cnpj = "00017024000153"  # Exemplo
        df = buscar_historico(cnpj, limite=10)
        assert isinstance(df, pd.DataFrame)
        # Se retornar vazio, o CNPJ pode não existir, mas não é erro

    def test_ranking_completo(self):
        """Testa o ranking completo com dados reais (pode ser demorado)."""
        from fundos.ranker import top_fundos
        resultado = top_fundos(quantidade=5, perfil=2, incluir_sharpe_sortino=True)
        assert isinstance(resultado, list)
        if resultado:
            assert "score" in resultado[0]
            assert "nome" in resultado[0]
            # Verifica se os scores estão entre 0 e 10
            for item in resultado:
                assert 0 <= item["score"] <= 10


# ---------------------------------------------------------------------
# Teste visual (opcional)
# ---------------------------------------------------------------------

def test_mostrar_recomendacoes(mock_coletor):
    """
    Teste visual que exibe recomendações para cada perfil.
    Usa dados mock para ser rápido.
    """
    from fundos.ranker import rankear_fundos

    print("\n" + "="*70)
    print("📊 RECOMENDAÇÕES DE FUNDOS (DADOS MOCK)")
    print("="*70)

    for perfil_nome, perfil_id in [("Conservador", 1), ("Moderado", 2), ("Agressivo", 3)]:
        print(f"\n--- Perfil: {perfil_nome} ---")
        recs = rankear_fundos(perfil=perfil_id, limite=3, incluir_sharpe_sortino=True)
        if not recs:
            print("   Nenhuma recomendação disponível.")
            continue
        for i, f in enumerate(recs, 1):
            print(f"\n{i}️⃣ {f.get('nome', 'N/A')}")
            print(f"   CNPJ: {f.get('cnpj', 'N/A')}")
            print(f"   Classe: {f.get('classe', 'N/A')}")
            print(f"   Score: {f.get('score', 0):.2f}")
            print("   " + "-"*40)

    print("\n" + "="*70)
    print("Fim das recomendações")
    print("="*70 + "\n")


# ---------------------------------------------------------------------
# Execução
# ---------------------------------------------------------------------

if __name__ == "__main__":
    # Para rodar apenas testes rápidos (sem download)
    pytest.main([__file__, "-v", "-m", "not slow", "--tb=short"])

    # Para rodar todos os testes (incluindo downloads)
    # pytest.main([__file__, "-v", "--tb=short"])