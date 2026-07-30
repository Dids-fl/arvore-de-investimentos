# Validação financeira

## Estado atual

O projeto possui infraestrutura para:

- carregar preços;
- validar séries;
- calcular retornos;
- simular carteira;
- aplicar custos em pontos-base;
- calcular turnover;
- executar walk-forward;
- montar benchmarks;
- calcular métricas de retorno e risco.

Isso não significa que as recomendações do engine já foram validadas. A CLI de
backtest atual executa uma estratégia de momentum genérica. É necessário criar
um adaptador que transforme as regras reais do recomendador em decisões
históricas point-in-time.

## O que deve ser respondido

1. A recomendação supera alternativas simples após custos?
2. O resultado persiste fora da amostra?
3. O ganho depende de poucos períodos ou ativos?
4. Pequenas mudanças nos pesos destroem o resultado?
5. O risco observado é compatível com o perfil indicado?
6. A estratégia funciona em regimes diferentes?
7. O resultado permanece após tributação aproximada?

## Protocolo mínimo

### 1. Definir a hipótese antes de testar

Exemplo:

> Para investidores moderados com horizonte superior a cinco anos, a carteira
> recomendada apresenta retorno ajustado ao risco superior a uma carteira
> passiva de referência após custos.

Defina previamente:

- população;
- período;
- universo;
- benchmark;
- frequência de rebalanceamento;
- custos;
- métricas;
- critério de aprovação.

Não escolha critérios depois de observar o resultado.

### 2. Construir universo point-in-time

O universo de cada data deve conter apenas ativos existentes e elegíveis
naquela data. É necessário tratar:

- entrada e saída de ativos;
- fundos encerrados;
- troca de ticker;
- desdobramentos e proventos;
- liquidez histórica;
- indisponibilidade real da informação;
- mudanças de classificação.

Usar somente os ativos sobreviventes atuais cria viés de sobrevivência.

### 3. Impedir vazamento temporal

Uma decisão em `t` só pode usar dados conhecidos até `t`. Atenção a:

- balanços publicados depois da data-base;
- revisões de séries;
- metadados atuais aplicados ao passado;
- retorno do próprio período de decisão;
- normalização calculada com toda a amostra.

### 4. Separar desenvolvimento e avaliação

Use:

- período de desenvolvimento;
- período de validação;
- período final fora da amostra;
- janelas walk-forward.

O período final não deve ser reutilizado para ajustar pesos.

### 5. Modelar execução

Inclua:

- corretagem, quando aplicável;
- emolumentos;
- bid-ask spread;
- slippage;
- taxa de administração;
- turnover;
- atraso entre sinal e execução;
- impostos coerentes com a classe;
- aportes e retiradas.

### 6. Comparar benchmarks

No mínimo:

- CDI;
- Ibovespa;
- carteira passiva compatível com o perfil;
- estratégia ingênua de pesos fixos;
- versão sem o ranker, para medir valor incremental.

Comparar um perfil conservador apenas com Ibovespa produz conclusão enviesada.

### 7. Medir retorno e risco

O pacote já calcula:

- retorno anualizado;
- volatilidade anualizada;
- Sharpe;
- Sortino;
- drawdown máximo;
- Calmar;
- VaR histórico;
- CVaR histórico;
- proporção de períodos positivos.

Também devem ser registrados:

- turnover;
- custos totais;
- tempo de recuperação;
- concentração;
- pior mês e pior ano;
- estabilidade por janela;
- diferença para o benchmark.

### 8. Medir incerteza

Não aceite uma estratégia por uma diferença pequena em uma única amostra. Use,
quando adequado:

- bootstrap de retornos;
- intervalos de confiança;
- análise por subperíodo;
- testes de sensibilidade;
- múltiplos regimes;
- correção para múltiplas tentativas.

## Critérios de aceitação

Os critérios devem ser definidos por perfil. Um protocolo responsável exige:

- resultado fora da amostra;
- retorno líquido comparado a benchmark adequado;
- drawdown compatível com o risco declarado;
- estabilidade em diferentes janelas;
- ausência de dependência extrema de um ativo;
- desempenho que sobreviva a custos maiores;
- melhoria que não desapareça com pequenas mudanças de parâmetros;
- documentação de resultados negativos.

Não use apenas “Sharpe maior que 1” ou “bateu o CDI” como aprovação universal.

## Experimentos recomendados

### A. Valor da alocação

Compare a carteira do engine com uma carteira-base fixa por perfil.

### B. Valor dos rankers

Mantenha a alocação e compare:

- ativos escolhidos pelo ranker;
- ativos escolhidos aleatoriamente;
- ETF amplo da classe;
- pesos iguais.

### C. Valor das restrições

Remova uma regra por vez e meça efeito em risco e retorno.

### D. Sensibilidade

Varie:

- cortes de market cap;
- peso das métricas;
- frequência de rebalanceamento;
- tamanho do top;
- custos;
- horizonte.

### E. Regimes

Avalie separadamente:

- alta e queda de juros;
- inflação elevada;
- crise de liquidez;
- mercado de alta e baixa;
- períodos laterais.

## Artefatos esperados

Cada execução deve gerar:

- arquivo de configuração;
- hash ou commit do código;
- intervalo de dados;
- universo por data;
- transações;
- pesos;
- retornos;
- benchmarks;
- métricas;
- custos;
- gráficos;
- avisos;
- relatório final.

## Comando disponível

A CLI atual aceita um CSV de preços:

```bash
python -m backtest.run_backtest dados/precos.csv \
  --lookback 252 \
  --rebalanceamento 63 \
  --top 5 \
  --custos-bps 10 \
  --capital 100000 \
  --aporte-mensal 1000
```

Ela valida a infraestrutura de walk-forward, mas ainda não representa o engine
completo.

## Definição de concluído

A eficácia financeira só pode ser considerada validada quando:

1. as regras reais do engine forem reproduzidas historicamente;
2. os dados forem point-in-time;
3. custos e impostos forem incluídos;
4. houver avaliação fora da amostra;
5. benchmarks adequados forem usados;
6. resultados e limitações forem reproduzíveis;
7. o processo registrar também experimentos que falharam.
