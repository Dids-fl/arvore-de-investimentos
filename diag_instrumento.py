from datetime import date, timedelta
from collections import Counter
from mercados.b3 import B3

b3 = B3()
instrumentos = Counter()

# Só 1 dia já basta para ver os valores possíveis do campo "instrumento"
dia = date.today() - timedelta(days=1)
for i in range(1, 6):  # tenta alguns dias corridos até achar um com pregão
    try:
        for neg in b3.negociacao_balcao(dia):
            instrumentos[neg.instrumento] += 1
        if instrumentos:
            break
    except Exception as e:
        print(f"dia {dia} falhou: {e}")
    dia = dia - timedelta(days=1)

print(f"Dia consultado: {dia}")
print("Valores distintos de 'instrumento' encontrados:")
for valor, contagem in instrumentos.most_common(30):
    print(f"  {valor!r}: {contagem} negócios")
