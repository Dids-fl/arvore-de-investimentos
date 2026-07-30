# Metodologia de recomendação

## Natureza do método

A recomendação é baseada em regras heurísticas de adequação. Ela não é um
modelo de previsão treinado estatisticamente e ainda não foi validada como
estratégia capaz de superar benchmarks.

Os testes atuais demonstram consistência das regras, não eficácia financeira.

## Etapas

### 1. Normalização do questionário

O engine converte respostas textuais da interface em valores canônicos e
valida:

- prazo;
- tolerância a risco;
- objetivo e necessidade de fluxo;
- liquidez;
- reserva de emergência;
- idade, despesas e dependentes;
- renda e dívidas;
- conhecimento e experiência;
- forma de aporte;
- comportamento diante de perdas;
- declaração de imposto;
- carteira atual;
- capital, aporte mensal e meta;
- contexto fiscal adicional.

Campos condicionais são neutralizados quando não se aplicam. Por exemplo:

- `aporte_mensal` vira zero quando o aporte não é mensal;
- `liquidez_pct` vira zero quando liquidez não foi solicitada;
- meta exige valor e prazo em conjunto.

### 2. Restrições de adequação

Antes de buscar retorno, o motor aplica restrições. Exemplos cobertos por
fixtures:

- dívida de juros altos bloqueia a recomendação;
- prazo curto limita exposição a risco;
- ausência de reserva prioriza proteção;
- investidor iniciante não recebe cripto direta;
- a carteira final deve somar 100%.

Essas regras representam prudência programada. Elas ainda precisam de
justificativa empírica ou normativa documentada para serem tratadas como
política definitiva.

### 3. Recomendação principal

`recomendador.calcular_recomendacao()` combina o questionário com hipóteses de
taxa e devolve:

- categoria principal;
- nível de risco do perfil;
- prazo de referência;
- conhecimento ajustado;
- avisos.

O resultado é uma classificação, não uma ordem de compra.

### 4. Construção da carteira

`portfolio._build_portfolio()` parte de uma alocação-base por nível de risco e
aplica ajustes relacionados a:

- conhecimento;
- objetivo;
- renda e despesas;
- dependentes;
- aportes;
- carteira atual;
- liquidez;
- tributação declarada;
- horizonte;
- necessidade de renda periódica.

Após os ajustes, a carteira é normalizada para 100% e classificada novamente.
A classificação final pode ser mais conservadora que a resposta bruta de
risco.

### 5. Hipóteses de retorno

Para um horizonte de `n` meses:

1. a taxa conservadora é a taxa anual equivalente da curva Selic;
2. a taxa moderada é a média entre essa taxa e o CAGR histórico do Ibovespa;
3. a taxa agressiva é o CAGR histórico do Ibovespa.

Em forma simplificada:

```text
taxa[1] = curva_selic(n)
taxa[2] = (curva_selic(n) + ibov_cagr_10a) / 2
taxa[3] = ibov_cagr_10a
```

A taxa da carteira é a média ponderada pela alocação e pelo risco de cada
categoria.

Essa construção é uma hipótese operacional. O CAGR passado do Ibovespa não é
previsão, e a média do perfil moderado não representa uma fronteira eficiente.

### 6. Curva da Selic

A curva usa:

- Selic atual como ponto inicial;
- medianas anuais do Focus como nós futuros;
- interpolação mensal entre nós;
- composição das taxas ao longo do prazo;
- extrapolação explícita quando o horizonte excede o último ano disponível.

O resultado inclui quantidade de meses extrapolados e avisos. A curva reduz a
simplificação da média direta entre Selic atual e Focus, mas continua sendo uma
aproximação.

### 7. Projeções

As projeções consideram:

- capital inicial;
- aportes mensais;
- prazo;
- taxa bruta da carteira;
- inflação;
- tratamento tributário por categoria.

O sistema produz valores nominais e reais. Quando a classe tributária é
indeterminada, o engine não deve apresentar um valor líquido agregado como se
fosse exato.

O cenário pessimista usa uma redução determinística da taxa central. Ele é um
cenário de sensibilidade, não VaR, estresse probabilístico ou intervalo de
confiança.

### 8. Seleção de ativos

Depois de definir a carteira, `recomendador_ativos.py` chama rankers apenas para
classes com percentual mínimo relevante. Cada ranker possui métricas e fontes
próprias.

O score:

- ordena candidatos dentro de uma classe;
- não torna produtos de classes diferentes diretamente comparáveis;
- depende da qualidade e atualidade da fonte;
- não deve ser interpretado como probabilidade de retorno.

## Meta financeira

Quando valor e prazo são fornecidos, o engine calcula:

- patrimônio projetado;
- diferença para a meta;
- aporte necessário;
- cenários central e pessimista.

O cálculo é sensível às hipóteses de retorno, inflação e tributação. A meta não
é garantia de atingimento.

## O que a metodologia ainda não prova

- superioridade sobre CDI, Ibovespa ou carteira passiva;
- estabilidade dos pesos em diferentes regimes;
- ausência de sobreajuste;
- retorno líquido superior após custos reais;
- adequação regulatória para recomendação profissional;
- causalidade entre respostas do questionário e melhor resultado financeiro.

O protocolo para tratar essas lacunas está em
[Validação financeira](validacao-financeira.md).
