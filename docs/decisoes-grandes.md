# Antes de uma decisão grande

A seção **🛡️ Antes de uma decisão grande** aparece no resultado da análise.
Ela usa o histórico real de cada classe desde 2000 para mostrar o que a
carteira recomendada teria passado, em reais, e quanto custa mudar de ideia.
O código fica em `decisao/`, com testes em `tests/unit/test_decisao.py`.

## Base histórica

`decisao/dados/indices_mensais.csv` tem o retorno de cada mês, por classe:

| Coluna | Fonte gratuita | Desde |
|---|---|---|
| `cdi` | Banco Central, SGS 12 | 2000 |
| `ipca_mais` | Tesouro IPCA+ sem cupom de ~5 anos, preços do Tesouro Transparente | 2005 |
| `ibov` | Ibovespa, Yahoo Finance | 2000 |
| `fii` | Média dos FIIs líquidos (informes da CVM e preços do Yahoo) | 2020 |
| `usd` | Dólar, Yahoo Finance | 2004 |
| `btc` | Bitcoin em reais, Yahoo Finance | quando disponível |

Para refazer o arquivo: `python scripts/atualizar_indices_historicos.py`.
Ao abrir o app, os meses que faltam no fim da base são completados com CDI,
Ibovespa e dólar baixados na hora (cache de um dia). Meses sem dado de uma
classe usam um substituto: FIIs → metade IPCA+ e metade Ibovespa; bitcoin →
Ibovespa (o app avisa que isso subestima o risco); IPCA+ e dólar → CDI.

Cada categoria do app vira uma mistura desses índices
(`decisao.historico.PROXY_CATEGORIA`). Multimercado e previdência que não é
de renda fixa usam 70% CDI, 15% IPCA+ e 15% Ibovespa, porque não há índice
gratuito para eles. A carteira é rebalanceada todo mês.

## As seis abas

1. **Teste de crise:** perda máxima em reais, meses até o fundo e até voltar
   ao valor inicial nas crises de 2008, 2015–2016, 2020 e 2021–2022, mais a
   pior queda de todo o histórico. Como os dados são mensais, quedas dentro
   de um mês não aparecem inteiras.
2. **Faixas por prazo:** faixas de 50%, 80% e 90% para o retorno anual no
   prazo da pessoa (até 10 anos). A base é o CDI esperado hoje. A ela somam-se
   duas incertezas independentes: o erro da previsão do CDI, medido na
   validação histórica, e a diferença da carteira em relação ao CDI nas
   janelas passadas do mesmo prazo.
3. **Garantias (FGC):** quanto fica em Tesouro ou CDB/LCI/LCA, em fundos e
   sem garantia. Mostra quantos bancos são necessários para ficar dentro dos
   R$ 250 mil por CPF e instituição, juros de até 5 anos incluídos, e avisa
   sobre o teto de R$ 1 milhão a cada 4 anos.
4. **Custo de sair antes:** valor líquido de IR para resgate em 6, 12 e 24
   meses, no cenário central e no pior caso. O pior caso usa as 5% piores
   janelas da classe contra o CDI. Também mostra como e quando cada classe
   pode ser resgatada. Previdência usa o regime regressivo; no PGBL o IR
   incide sobre todo o valor.
5. **Entrada parcelada:** compara investir tudo de uma vez com entrar em 6 ou
   12 parcelas mensais, com o dinheiro parado no CDI. Usa todas as datas de
   início desde 2000 e um horizonte de 24 meses.
6. **Meu histórico:** salva a análise com data, carteira e taxas previstas em
   `~/.local/share/arvore_investimentos/decisoes.jsonl`, ou no caminho da
   variável `ARVORE_DIARIO`. Nada sai do computador. Depois, compara o previsto
   com o que os índices da carteira renderam desde então.

## Limites

- Índices não são os seus ativos: um fundo ou ação específico pode ir bem
  melhor ou pior que a média da classe.
- Para prazos longos há pouco histórico independente: só 2 períodos de 10
  anos sem sobreposição desde 2000.
- IR simplificado: não considera a isenção de vendas de até R$ 20 mil por mês
  em ações, a compensação de prejuízos nem o regime progressivo da
  previdência. O cálculo detalhado continua na seção de tributação.
