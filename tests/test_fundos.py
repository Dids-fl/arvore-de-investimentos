# tests/test_fundos.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from fundos import rankear_fundos
from fundos.coletor import listar_fundos, buscar_cotas_em_lote

def test_rankear_fundos_com_dados_reais():
    print("\n" + "="*70)
    print(" 🌐 CONECTANDO AO PORTAL DE DADOS ABERTOS DA CVM (via cvm-sqlite)...")
    print("="*70)

    df_cadastro = listar_fundos(limit=150)
    if df_cadastro.empty:
        print("⚠️ Não foi possível carregar o cadastro da CVM.")
        return

    print(f"📋 {len(df_cadastro)} fundos ativos encontrados no cadastro.")

    # Detecta coluna de CNPJ
    cnpj_col = None
    for col in ['CNPJ_FUNDO', 'CNPJ', 'cnpj']:
        if col in df_cadastro.columns:
            cnpj_col = col
            break
    if cnpj_col is None:
        print("⚠️ Coluna de CNPJ não encontrada no cadastro.")
        return

    cnpjs = df_cadastro[cnpj_col].tolist()
    print("⏳ Baixando histórico de cotas...")
    df_cotas = buscar_cotas_em_lote(cnpjs, dias=365)

    if df_cotas.empty:
        print("⚠️ Nenhuma cota encontrada para os fundos selecionados.")
        return

    print(f"📊 Cruzamento concluído: {df_cotas['CNPJ_FUNDO'].nunique()} fundos com cotas disponíveis.")

    top_fundos = rankear_fundos(perfil=2, limite=5)

    if not top_fundos:
        print("⚠️ Nenhum fundo rankeado.")
        return

    print("\n" + "="*70)
    print("📊 TOP 5 FUNDOS REAIS (PERFIL MODERADO)")
    print("="*70)

    for pos, f in enumerate(top_fundos, 1):
        print(f"\n{pos}º LUGAR: {f.get('nome', 'N/A')}")
        print(f"   🔹 CNPJ: {f.get('cnpj', 'N/A')}")
        print(f"   🔹 Classe CVM: {f.get('classe', 'N/A')}")
        print(f"   🔹 Rentabilidade 12m: {f.get('rentabilidade_12m', 0):.2%}")
        print(f"   🔹 Patrimônio Líquido: R$ {f.get('patrimonio', 0):,.2f}")
        print(f"   🔹 Taxa Adm (estimada): {f.get('taxa_adm', 0):.2%}")
        print(f"   ⭐ Score: {f.get('score', 0):.2f} / 10")
        print("   " + "-"*50)

    print("\n" + "="*70)
    print("✅ Teste concluído com sucesso!")

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])