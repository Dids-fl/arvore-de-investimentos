# intersect.py
from fundos.cadastro_coletor import listar_fundos_ativos
from fundos.informe_diario_coletor import listar_informe

df_cad = listar_fundos_ativos(limit=None)  # todos
df_inf = listar_informe()

cnpjs_cad = set(df_cad["CNPJ_Classe"])
cnpjs_inf = set(df_inf["CNPJ_Classe"])

intersecao = cnpjs_cad.intersection(cnpjs_inf)
print(f"CNPJs no cadastro (ativos): {len(cnpjs_cad)}")
print(f"CNPJs no informe: {len(cnpjs_inf)}")
print(f"Interseção: {len(intersecao)}")

if intersecao:
    print("Exemplos de CNPJs com histórico:", list(intersecao)[:5])
else:
    print("Nenhum CNPJ do cadastro aparece no informe. Verifique normalização.")