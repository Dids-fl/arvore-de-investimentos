# Validação histórica (o que o app previa x o que aconteceu)

Gerado em 2 de novembro de 2026 por `python -m backtest.validacao_historica`.
Os números completos, data a data, ficam em
`backtest/resultados/validacao_historica.json`.

## Como o teste funciona

Para cada data-base no passado, o teste monta os dados de mercado **como
estavam disponíveis naquele dia** e pede ao código a mesma previsão que o app
faria. Depois compara com o que de fato aconteceu.

- **Sem olhar o futuro:** Selic do dia, IPCA 12 meses só até o último mês já
  divulgado, mediana do Focus publicada até a data e Ibovespa até a data.
- **Treino e teste separados:** toda regra nova foi escolhida com um período
  e conferida em outro, que não foi usado na escolha (ações: treino
  2004–2012, teste 2013–2025; Tesouro: 2013–2018 e 2019–2025; ETFs:
  2020–2022 e 2023–2025).
- **Fontes gratuitas:** BCB/SGS (Selic, CDI, IPCA), Focus/Olinda, Tesouro
  Transparente (preços diários desde 2004), CVM (banco local do app) e Yahoo
  Finance.

## 1. Projeções de retorno do engine (2013–2025)

Erro = previsto − realizado, em pontos percentuais ao ano. "Real ≥
pessimista" deveria ficar perto de 80% ou acima.

| Classe | Horizonte | Erro médio antes | Erro médio agora | Viés agora | Real ≥ pessimista (antes → agora) |
|---|---|---|---|---|---|
| Renda fixa (curva Selic/Focus x CDI) | 1 / 3 / 5 anos | 0,9 / 2,7 / 2,7 | 0,9 / 2,7 / 2,7 | −0,2 / −0,6 / −0,3 | 88 / 73 / 78% → 88 / 82 / 83% |
| Misto 50/50 | 1 / 3 / 5 anos | 8,4 / 4,8 / 3,1 | **7,2 / 3,2 / 1,6** | −0,5 / −1,1 / −1,2 | 58 / 73 / 89% → **92 / 100 / 100%** |
| Ações (x Ibovespa) | 1 / 3 / 5 anos | 17,1 / 10,1 / 6,7 | **14,8 / 6,8 / 3,0** | −0,9 / −1,0 / −1,7 | 54 / 55 / 78% → **92 / 95 / 100%** |
| Inflação (x IPCA) | 1 / 3 / 5 anos | 2,4 / 2,8 / 2,4 | **1,9 / 1,7 / 1,4** | −0,8 / −1,2 / −1,1 | — |

O erro de 1 ano em ações continua alto porque a bolsa oscila muito em 12
meses; nenhuma regra simples prevê isso. O que importa é que o viés sumiu e o
cenário pessimista passou a ser de fato pessimista.

### Como a regra de ações foi escolhida

| Regra (erro médio em 5 anos) | Treino 2004–2012 | Teste 2013–2025 |
|---|---|---|
| Antiga: repetir o CAGR do Ibovespa em 10 anos | 15,3 | 6,7 |
| **Curva de juros esperada, sem prêmio (adotada)** | **9,0** | **3,0** |
| Curva + prêmio fixo calibrado no treino (−6,7 p.p.) | 6,8 | 8,4 |
| Curva + prêmio histórico recalculado em cada data | 10,3 | 4,6 |

O prêmio calibrado no treino falhou no teste: o excesso do Ibovespa sobre o
CDI muda muito de uma década para outra. "Ações renderão o mesmo que os
juros esperados" foi a única regra boa nos dois períodos. De 2004 a 2025 o
Ibovespa rendeu, em média, perto do CDI. A diferença de risco entre perfis
passou a aparecer no **cenário pessimista**, que cai com a exposição a ações:
central − 0,84 × volatilidade do Ibovespa ÷ √prazo (0,84 é o percentil 20 da
distribuição normal, não um número ajustado aos dados).

### Inflação

O engine usa o IPCA esperado pelo Focus mês a mês no horizonte
(`engine.ipca_esperado_mercado`). O próprio Focus subestimou a inflação em
cerca de 1 p.p. ao ano no período, então o "poder de compra" projetado tende
a ser um pouco otimista.

## 2. Rankers de ativos

"1º colocado" é o primeiro do ranking. "Perdeu do CDI" conta as vezes em que
ele rendeu mais de 2 p.p. abaixo do CDI.

### Tesouro Direto (26 datas, 2013–2025)

| Horizonte de 1 ano | Antes | Agora |
|---|---|---|
| Conservador: excesso sobre o CDI / perdeu do CDI / bateu a mediana | −0,3 p.p. / 19% / 46% | **+0,6 p.p. / 0% / 62%** |
| Moderado | +0,2 p.p. / 19% / 50% | **+0,5 p.p. / 12% / 69%** |

Regra nova: o Tesouro Selic é a referência; um prefixado ou IPCA+ só fica à
frente se vencer até 1,5 ano depois do prazo do investidor e pagar pelo menos
2 p.p. (conservador) ou 1 p.p. (demais perfis) acima da Selic esperada.

**Custo honesto:** em 3 anos, para moderado e agressivo, o retorno médio caiu
de +1,1 para +0,4 p.p. sobre o CDI, com o mesmo risco. A regra antiga ganhava
apostando em títulos longos durante a queda de juros de 2016–2019. A nova
prioriza não perder do CDI.

Ao refazer este teste foi encontrado e corrigido um erro do próprio backtest:
títulos com taxa 0,00% eram descartados, e o Tesouro Selic negociou assim em
boa parte de 2013–2018.

### ETFs de ações (21 datas, 2020–2025)

| | Antes | Agora |
|---|---|---|
| Retorno do 1º colocado | 9,8% | **15,0%** |
| Média dos 3 primeiros (mediana do universo: 7,3%; CDI: 11,5%) | 5,3% | **11,3%** |
| Pior caso dos 3 primeiros | −22,5% | **−15,2%** |

No treino e no teste, os ETFs de ações de **menor volatilidade** renderam
mais e caíram menos; o retorno e o Sharpe dos últimos 12 meses não previram
nada. O score passou a usar volatilidade (70%), liquidez (15%) e custo (15%).
Fundos regionais (FINOR, FINAM, FUNDES) e ativos que não são fundos de índice
ficam fora.

### Fundos e previdência (CVM, 3 cortes em 2025, 12 meses seguintes)

| | Antes | Agora |
|---|---|---|
| Fundos, conservador: média do 1º colocado | 12,4% | **14,4%** (CDI 14,6%) |
| Fundos, conservador: correlação score × retorno | 0,44 | **0,54** |
| Previdência, conservador: 1º bateu a mediana | 100% | 100% |

O perfil conservador deixou de receber fundos de "Crédito Livre", "Duração
Alta", exterior e incentivados de infraestrutura. Antes, o bônus por isenção
de IR levava ao topo um fundo de debêntures incentivadas que rendeu 6,9%
contra 14,5% do CDI. Nos perfis moderado e agressivo esses fundos continuam
permitidos; com só 3 cortes, mexer mais neles seria ajustar ao acaso.

### FIIs (22 datas trimestrais, 2020–2025)

DY e P/VP de cada data foram reconstruídos com o informe mensal da CVM
(valor patrimonial e rendimento por cota, só os informes já entregues na
data) e o preço do Yahoo; o retorno medido é o total (preço + rendimentos)
dos 12 meses seguintes. Vacância ficou de fora por falta de série gratuita.

Top-10 do ranking, média por data:

| | Treino 2020–2022 | Teste 2023–2025 |
|---|---|---|
| Regra antiga (DY alto + P/VP baixo), conservador: excesso sobre o CDI | −20,4 p.p. | −5,3 p.p. |
| **Regra nova: excesso sobre o CDI** | **−6,3 p.p.** | **−2,0 p.p.** |
| Regra antiga: bateu a mediana dos FIIs | 0% | 33% |
| **Regra nova: bateu a mediana** | **100%** | **58%** |
| Regra antiga: pior resultado | −23,1% | −6,1% |
| **Regra nova: pior resultado** | **−8,4%** | **−3,0%** |

A regra antiga era a pior entre todas as testadas: DY muito acima dos pares
e desconto forte sobre o patrimônio costumam sinalizar fundo em
dificuldade, cujo preço continua caindo. A regra nova ordena pela liquidez e
exclui FIIs com DY mais de 2 p.p. acima da mediana ou P/VP abaixo de 0,8.
Ela foi a melhor no treino e continuou à frente no teste. Mesmo assim, **os
FIIs como classe renderam menos que o CDI em 2020–2025**, um período de
juros altos.

Ao montar este teste, apareceram desdobramentos de cotas não ajustados no
Yahoo (XPML11 e KNCR11 com "retorno" de +700% em um ano). Janelas com salto
diário acima de 35% passaram a ser descartadas na validação de FIIs e ETFs.

### Ações (26 datas semestrais, 2013–2025)

P/L, P/VP, ROE e DY de cada data foram reconstruídos só com dados públicos
da CVM: lucro e patrimônio das DFPs (a DFP de um ano só conta a partir de
abril do ano seguinte), número de ações do FRE e tickers do FCA. Preço e
dividendos vêm do Yahoo. Entram as ações com liquidez média de pelo menos
R$ 1 milhão por dia; o retorno medido é o total dos 12 meses seguintes.

Top-10 do ranking, excesso médio sobre o Ibovespa por ano:

| Perfil | Regra | Treino 2013–2018 | Teste 2019–2025 | Bateu a mediana (treino / teste) | Bateu o Ibovespa (teste) |
|---|---|---|---|---|---|
| Conservador | atual (DY 50%, P/L 25%, ROE 15%, P/VP 10%) | +7,9 p.p. | +2,7 p.p. | 83% / 71% | 64% |
| Moderado | antiga (ROE 40%) | +3,5 p.p. | +1,4 p.p. | 92% / 71% | 43% |
| Moderado | **nova (P/L 35%, DY 25%, P/VP 25%, ROE 15%)** | **+8,7 p.p.** | **+3,1 p.p.** | 100% / 64% | **71%** |
| Agressivo | antiga (ROE 70%) | −0,9 p.p. | −4,4 p.p. | 42% / 36% | 29% |
| Agressivo | **nova (P/L 50%, P/VP 50%, ROE ≥ 10% como filtro)** | **+8,9 p.p.** | **+6,8 p.p.** | **100% / 100%** | **79%** |

Cada regra nova foi a melhor do treino pelo critério "bater a mediana com
mais frequência e, no empate, maior excesso". Pesos vizinhos (por exemplo
P/L 60% e P/VP 40%) dão resultados parecidos, então não é um ajuste fino ao
acaso. Ordenar só por ROE alto foi uma das piores regras nos dois períodos:
empresas muito rentáveis já costumam estar caras. O conservador ficou como
estava, porque já ia bem nos dois períodos.

Cuidados: o Yahoo não tem preços de empresas que saíram da bolsa (só 388
dos 654 tickers tinham preço), o que favorece o universo testado (viés de
sobrevivência), e o pior top-10 ainda perdeu 15% em 12 meses. Ações seguem
sendo de alto risco.

Cripto não foi testado: a CoinGecko gratuita só dá 365 dias.

## 3. Carteiras por perfil (2008–2026, rebalanceadas todo mês)

1.500 perfis sorteados passaram pelo próprio `engine.criar_analise`. Cada
classe da carteira foi representada por um índice: CDI; Tesouro IPCA+ de
cerca de 5 anos (preços do Tesouro, com marcação a mercado); Ibovespa;
média dos FIIs líquidos (desde 2019); dólar. Multimercado e previdência que
não é de renda fixa usam 70% CDI, 15% IPCA+ e 15% Ibovespa, porque não há
índice gratuito para eles.

| | Perfis | Retorno anual | Pior queda média / pior caso | Pior 12 meses (média) | 12 meses abaixo do CDI |
|---|---|---|---|---|---|
| Conservador | 677 | 10,1% | 0% / 0% | +2,2% | 7% |
| Moderado | 402 | 9,9% | −2,7% / −16,9% | +1,8% | 28% |
| "Venderia tudo" numa queda | 399 | 10,1% | 0% / 0% | +2,2% | 7% |
| Prazo curto | 293 | 10,1% | 0% / 0% | +2,2% | 7% |

CDI no período: 10,0% ao ano.

Um segundo teste usou só respostas agressivas (risco alto, compraria mais
na queda, prazo longo). Ele gerou 604 carteiras agressivas, com pior queda
média de −5,4% e pior caso de −28,5%.

O resultado é coerente: quem venderia tudo numa queda e quem tem prazo
curto nunca teve perda, e a queda máxima cresce do conservador ao
agressivo. Os sorteios dão poucos agressivos porque o app usa o menor nível
entre risco declarado, reação a quedas e prazo. Quase metade dos perfis
agressivos ainda fica só em renda fixa, pelo objetivo "reserva" ou pela
falta de reserva de emergência. Isso é intencional.

O resultado honesto é que, de 2008 a 2026, correr mais risco não rendeu
mais que o CDI: a bolsa brasileira ficou perto do CDI no período. As
carteiras com risco servem para quem aceita oscilar esperando prêmio no
futuro, não porque o passado recente pagou esse prêmio. Por isso a
alocação não foi alterada.

## Limitações

- O motor tributário ainda tem casos sem comprovação documental; essa parte
  depende de informes de rendimentos reais ou de um contador.

- Fundos: só 3 cortes e janelas de 12 meses que se sobrepõem; o cadastro é o
  atual (viés de sobrevivência).
- ETFs: universo atual (mesmo viés) e sem taxa de administração histórica.
- Tesouro: títulos com cupom (juros semestrais, Renda+, Educa+) ficaram de
  fora porque o preço cai a cada pagamento.
- Retornos brutos de IR (fundos já descontam a taxa de administração).
- Desempenho passado não garante o futuro: as regras foram escolhidas por
  serem robustas em dois períodos diferentes, não por acertarem o futuro.
