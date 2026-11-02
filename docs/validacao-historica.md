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
- **Fontes gratuitas:** BCB/SGS (Selic, CDI, IPCA), Focus/Olinda, Tesouro
  Transparente (preços diários desde 2004), CVM (banco local do app) e Yahoo
  Finance.
- **Datas-base:** semestrais de 2013 a 2025 para projeções e Tesouro;
  trimestrais de 2020 a 2025 para ETFs; três cortes em 2025 para fundos (o
  banco da CVM guarda 3 anos).

## 1. Projeções de retorno do engine

Erro = previsto − realizado, em pontos percentuais ao ano.

| Classe (nível de risco) | Horizonte | Previsto | Realizado | Viés | Erro médio | Real ≥ pessimista |
|---|---|---|---|---|---|---|
| Renda fixa (curva Selic/Focus x CDI) | 1 ano | 9,64% | 9,85% | −0,2 | 0,9 | 88% |
| | 3 anos | 8,88% | 9,50% | −0,6 | 2,7 | 73% |
| | 5 anos | 8,57% | 8,83% | −0,3 | 2,7 | 78% |
| Misto (50/50) | 1 ano | 8,34% | 10,19% | −1,9 | 8,4 | 58% |
| | 3 anos | 7,72% | 9,95% | −2,2 | 4,8 | 73% |
| | 5 anos | 7,53% | 9,72% | −2,2 | 3,1 | 89% |
| Ações (CAGR Ibov 10 anos x Ibovespa) | 1 ano | 7,04% | 10,52% | −3,5 | 17,1 | 54% |
| | 3 anos | 6,57% | 9,92% | −3,3 | 10,1 | 55% |
| | 5 anos | 6,50% | 10,26% | −3,8 | 6,7 | 78% |

**Renda fixa: bom.** A curva da Selic montada com o Focus quase não tem viés e
erra menos que simplesmente repetir a Selic atual (erro de 1,4 / 3,2 / 4,1
p.p. em 1 / 3 / 5 anos, contra 0,9 / 2,7 / 2,7 p.p. do engine).

**Ações: o ponto mais fraco.** Repetir o CAGR dos últimos 10 anos do
Ibovespa subestimou o retorno em cerca de 3,5 p.p. ao ano em todos os
horizontes. Em vários momentos o app previa que ações renderiam menos que o
CDI. O "cenário pessimista" de ações também não foi pessimista: em 1 e 3
anos, quase metade das vezes o resultado real ficou abaixo dele.

Regras alternativas testadas no mesmo período (erro médio, p.p. ao ano):

| Regra para ações | 1 ano | 3 anos | 5 anos |
|---|---|---|---|
| Atual: CAGR do Ibovespa em 10 anos | 17,1 | 10,1 | 6,7 |
| Curva Selic/Focus (= renda fixa) | 14,8 | 6,8 | 3,0 |
| Curva Selic/Focus + 2 p.p. | 14,6 | 6,8 | 2,8 |
| Média (CAGR 10a, curva + 3 p.p.) | 15,8 | 8,3 | 4,3 |

O prêmio de 2 p.p. foi escolhido olhando este mesmo período, então o ganho
dele sobre "curva sem prêmio" não é evidência forte. O resultado robusto é
que **ancorar ações na curva de juros esperada erra bem menos que repetir os
últimos 10 anos**. A regra do engine não foi alterada: a escolha fica para
decisão explícita.

### Inflação

| Horizonte | IPCA usado hoje (Focus) | Realizado | Erro médio | Erro do método antigo (IPCA 12m repetido) |
|---|---|---|---|---|
| 1 ano | 4,93% | 5,74% | 1,85 | 2,42 |
| 3 anos | 4,54% | 5,72% | 1,68 | 2,80 |
| 5 anos | 4,51% | 5,62% | 1,42 | 2,36 |

Com base nisso, **o engine passou a usar o IPCA esperado pelo Focus**
(`engine.ipca_esperado_mercado`) no poder de compra, no cenário pessimista e
na meta. O próprio Focus subestimou a inflação em cerca de 1 p.p. ao ano no
período, então o "poder de compra" projetado tende a ser um pouco otimista.

## 2. Rankers de ativos

"Escolhido" é o 1º do ranking; "bateu a mediana" compara com o ativo mediano
do universo elegível na mesma data; Spearman mede se a ordem do score acompanha
a ordem dos retornos (0 = nenhuma relação, 1 = perfeita).

| Ranker (perfil moderado) | Datas | Retorno do 1º | Mediana do universo | CDI | 1º bateu a mediana | Spearman |
|---|---|---|---|---|---|---|
| Tesouro, 1 ano | 26 | 8,02% | 10,62% | 9,86% | 46% | 0,01 |
| Tesouro, 3 anos | 21 | 11,11% | 11,42% | 9,45% | 48% | 0,21 |
| Fundos (CVM), 1 ano | 3 | 12,40% | 14,10% | 14,57% | 67% | 0,42 |
| Previdência (CVM), 1 ano | 3 | 14,87% | 13,47% | 14,57% | 100% | 0,49 |
| ETFs de ações, 1 ano | 21 | 9,83% | 7,26% | 11,46% | 52% | −0,03 |

- **Tesouro:** o score não prevê o retorno de 1 ano. A marcação a mercado dos
  prefixados e IPCA+ longos domina. Em 3 anos aparece uma relação fraca
  (0,2).
- **Fundos e previdência:** o score tem relação real com o retorno seguinte
  (0,4 a 0,5). Na previdência, o 1º colocado bateu a mediana nas 3 datas. Nos
  fundos comuns, em set/2025 o 1º para **todos os perfis, inclusive o
  conservador**, foi um fundo de debêntures incentivadas (6,9% contra 14,5% do
  CDI): o bônus por isenção de IR leva ao topo fundos com risco de crédito e
  de marcação.
- **ETFs:** o score não prevê o retorno. Na prática ele escolhe quase sempre o
  IVVB11 (S&P 500), por liquidez e Sharpe.

Ações, FIIs e cripto não foram testados: não há fonte gratuita com os
indicadores fundamentalistas "como eram" em cada data (Fundamentus e
CoinGecko gratuitos só dão o dado atual ou 365 dias).

## Limitações

- Fundos: só 3 cortes e janelas de 12 meses que se sobrepõem; o cadastro é o
  atual, então fundos encerrados não entram (viés de sobrevivência).
- ETFs: universo atual (mesmo viés) e sem taxa de administração histórica.
- Tesouro: títulos com cupom (juros semestrais, Renda+, Educa+) ficaram de
  fora porque o preço cai a cada pagamento.
- Retornos brutos de IR (fundos já descontam a taxa de administração).
- 2013–2025 inclui juros muito altos e muito baixos, mas é um único período
  histórico; desempenho passado não garante o futuro.

## Próximos passos sugeridos

1. Trocar a regra de ações por "curva Selic/Focus + prêmio" e calibrar o
   prêmio fora da amostra (por exemplo, com dados anteriores a 2013).
2. Tornar o cenário pessimista de ações mais pessimista nos horizontes de 1 a
   3 anos.
3. Limitar o bônus de isenção de IR nos fundos para o perfil conservador, ou
   exigir risco de crédito compatível.
4. Repetir este teste periodicamente para acompanhar a evolução.
