from produtos_estruturados.cadastro_coletor import obter_cadastro
from produtos_estruturados.negociacao_coletor import obter_negociacao_agregada
from produtos_estruturados.indicadores import _buscar_campo, _CANDIDATOS_ISIN

cadastro = obter_cadastro()
negociacao = obter_negociacao_agregada(dias=60)

isins_cadastro = set()
for reg in cadastro["debentures"]:
    isin = _buscar_campo(reg, _CANDIDATOS_ISIN)
    if isin:
        isins_cadastro.add(isin)

isins_negociacao = set(negociacao.keys())

print(f"ISINs no cadastro de debentures: {len(isins_cadastro)}")
print(f"ISINs na negociacao (todos os tipos): {len(isins_negociacao)}")
print(f"Interseccao: {len(isins_cadastro & isins_negociacao)}")
print()
print("Amostra de 5 ISINs do cadastro:", list(isins_cadastro)[:5])
print("Amostra de 5 ISINs da negociacao:", list(isins_negociacao)[:5])
print()

# Checa se algum ISIN de debenture aparece "quase igual" (case/espaco)
amostra_cadastro = list(isins_cadastro)[:200]
for isin in amostra_cadastro:
    for isin_neg in isins_negociacao:
        if isin.strip().upper() == isin_neg.strip().upper() and isin != isin_neg:
            print(f"MATCH SÓ APÓS NORMALIZAR: {isin!r} vs {isin_neg!r}")
