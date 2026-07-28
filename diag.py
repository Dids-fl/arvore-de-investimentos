from produtos_estruturados.ranker import RankerEstruturados, PERFIL_MODERADO
from collections import Counter

r = RankerEstruturados(perfil=PERFIL_MODERADO)
ranking = r.gerar_ranking()

print("Total elegiveis:", len(ranking))
print("Distribuicao por tipo:", Counter(a["tipo"] for a in ranking))
print()

print("Top 5 DEBENTURE especificamente:")
for a in r.por_tipo("DEBENTURE", 5):
    print(
        f"  {a['identificador']} | score={a['score']} | taxa={a.get('taxa')} "
        f"| prazo={a.get('prazo_dias')} | isento={a['isento_ir']}"
    )
