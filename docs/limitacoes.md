# Limitações e riscos

## Aviso

O projeto é educacional e experimental. Ele não constitui recomendação
individual de investimento, consultoria, análise certificada, oferta, promessa
de rentabilidade ou orientação tributária.

## Limitações da recomendação

- As decisões são heurísticas.
- Os pesos não resultam de otimização de carteira.
- Respostas do questionário podem ser imprecisas ou inconsistentes.
- A classificação de risco não substitui suitability regulatório.
- Restrições prudenciais ainda não possuem validação empírica completa.
- O score de um ativo não é probabilidade de retorno.

## Limitações das projeções

- Retornos são hipóteses, não previsões.
- CAGR histórico pode não se repetir.
- A curva do Focus pode mudar rapidamente.
- A extrapolação além do último nó aumenta incerteza.
- O cenário pessimista não é uma distribuição probabilística.
- Inflação, aportes e reinvestimentos podem divergir.
- Valores reais dependem do índice e período escolhidos.

## Limitações tributárias

- Regras podem mudar após a vigência documentada.
- O come-cotas histórico só é considerado quando o estado tributário de cada
  lote é fornecido; o motor não o descobre a partir do saldo atual.
- Lotes previdenciários existentes dependem de principal, saldo e data
  informados corretamente pelo usuário.
- Regime progressivo depende da declaração completa.
- O benefício do PGBL depende da elegibilidade legal confirmada, da renda
  tributável e das deduções já utilizadas.
- Compensações de renda variável exigem histórico operacional.
- Cripto depende de custódia, natureza do evento e jurisdição.
- Estruturados dependem do subtipo e documentação.

Quando o contexto é insuficiente, o resultado correto é `indeterminada`.

## Limitações dos dados

- APIs podem falhar, limitar ou alterar campos.
- Dados podem ser revisados.
- Tickers podem ser descontinuados.
- Metadados do Yahoo podem estar ausentes.
- Universos atuais produzem viés de sobrevivência no passado.
- Fontes diferentes podem usar definições diferentes.
- Cache antigo preserva continuidade, não atualidade.

## Limitações dos rankers

- Métricas são específicas de cada classe.
- Scores entre classes não são diretamente comparáveis.
- Taxa de administração pode não estar disponível.
- Liquidez recente não garante liquidez futura.
- Rankings podem mudar com pequenas diferenças de dados.
- O melhor score não implica adequação ao usuário.
- A eficiência líquida usa uma taxa-cenário do engine; ela não é previsão.
- A classificação tributária de fundos depende da nomenclatura cadastral.
- Calendários de mercado posteriores a 2026 precisam ser confirmados ou
  fornecidos; o sistema identifica os anos sem calendário confirmado.

## Limitações do backtest

- A infraestrutura atual não reproduz automaticamente o engine completo.
- A CLI disponível usa momentum como exemplo.
- Sem dados point-in-time, há risco de vazamento.
- Custos, impostos e slippage podem ser subestimados.
- Muitos testes de parâmetros aumentam risco de sobreajuste.
- Desempenho passado não garante resultado futuro.

## Riscos operacionais

- indisponibilidade de fonte obrigatória;
- cache corrompido;
- credencial expirada;
- alteração de contrato;
- rate limit;
- execução parcial de rankers;
- timezone incorreto;
- versão tributária desatualizada;
- divergência entre interfaces;
- exportação de dados pessoais.

## Privacidade

O questionário pode conter informações financeiras pessoais. Recomendações:

- não enviar respostas para serviços externos sem necessidade;
- não registrar dados pessoais em logs;
- não versionar exportações de usuário;
- evitar armazenar tokens;
- definir política de retenção;
- anonimizar dados usados em análise.

## Uso responsável

Antes de usar uma saída:

1. leia fontes e avisos;
2. confirme a data de referência;
3. verifique se houve cache antigo;
4. confira a precisão tributária;
5. considere custos ausentes;
6. compare com alternativa simples;
7. não concentre decisão em um único score;
8. procure profissional habilitado quando necessário.

## Lacunas prioritárias

1. validar financeiramente as regras fora da amostra;
2. revisar tributação com profissional;
3. corrigir warnings e dívida técnica;
4. ampliar documentação pública e histórico de decisões;
5. monitorar drift, fontes e alterações legais.
