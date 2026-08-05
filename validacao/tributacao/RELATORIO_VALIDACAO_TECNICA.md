# Relatório técnico — validação tributária independente

Data-base do pacote: 2026-08-04.

## Resultado

| Grupo | Casos | Validados | Pendentes | Fora do escopo | Divergentes |
|---|---:|---:|---:|---:|---:|
| Renda fixa | 13 | 8 | 4 | 1 | 0 |
| Fundos | 12 | 7 | 5 | 0 | 0 |
| Previdência | 11 | 0 | 11 | 0 | 0 |
| Renda variável | 10 | 0 | 9 | 1 | 0 |
| Estruturados | 9 | 2 | 6 | 1 | 0 |
| **Total** | **55** | **17** | **35** | **3** | **0** |

Os 63 casos dourados das seis categorias, incluindo criptoativos, também
coincidem com o contrato atual do motor dentro das tolerâncias declaradas nas
fixtures.

## Correção de classificação

Resultados indeterminados por ausência de informação obrigatória não são,
automaticamente, casos fora do escopo. Os seguintes casos foram
reclassificados como `PENDENTE_PREMISSA`:

- `cri_sem_confirmacao_de_elegibilidade`;
- `estruturado_generico_indeterminado`;
- `pgbl_progressivo_sem_renda`;
- `pgbl_regime_ausente`.

Permanecem efetivamente fora do escopo deste lote:

- tributação de pessoa jurídica no caso de CRA;
- tributação de pessoa jurídica no caso de LCI;
- BDR, ainda não suportado pela fachada de renda variável.

Essa correção altera somente a taxonomia do relatório. Os impostos, valores
líquidos, regras tributárias e resultados de comparação não foram alterados.

## O que foi comprovado

- As faixas regressivas e o IOF modelados para renda fixa coincidem nos
  limites de 1, 29, 30, 180, 181, 360, 361, 720 e 721 dias.
- Os casos de fundos coincidem para curto e longo prazo, fundos de ações e o
  abatimento simplificado do come-cotas informado.
- PGBL e VGBL usam bases distintas e os regimes progressivo/regressivo
  coincidem nos exemplos documentados.
- Renda variável mantém prejuízo e IRRF separados por modalidade e não aplica
  a isenção mensal de ações a ETF, FII ou day trade.
- Produtos estruturados tributáveis seguem a tabela regressiva; a isenção de
  instrumentos condicionais depende de confirmação explícita.
- Casos indeterminados permanecem sem imposto e valor líquido inventados.
- Nenhuma divergência foi encontrada nos 55 casos dos cinco validadores.

## O que não foi comprovado

- vigência futura das regras após 2026;
- apuração de pessoa jurídica;
- reconstrução de eventos reais de fundos e come-cotas;
- previdência regressiva com múltiplos aportes e idades de lote;
- apuração completa de bolsa a partir de notas de corretagem;
- elegibilidade documental de cada CRI, CRA ou debênture incentivada;
- aderência universal a toda interpretação administrativa ou judicial.

## Integração revisada

`calculos.py` envia o contexto ao motor por lote ou de forma agregada conforme
o produto, preserva resultados indeterminados e não aplica alíquota de
fallback. `engine.py` aceita metadados tributários por categoria e agrega os
valores líquidos somente quando os cálculos necessários são determinados.
`core/catalogo.py` limita a precisão de categorias amplas e mantém produtos
estruturados genéricos como indeterminados.

## Critério de entrega

O pacote é considerado tecnicamente consistente quando:

- os validadores consolidam com `DIVERGENTE = 0`;
- os testes tributários passam;
- o Ruff não encontra erro nos arquivos alterados;
- a matriz não contém erro de fórmula;
- casos sem dados obrigatórios permanecem pendentes;
- somente produtos ou regimes não suportados ficam fora do escopo;
- as pendências continuam visíveis e não são convertidas em validação plena.

O resultado atende aos critérios técnicos acima, mas a revisão humana integral
permanece pendente.
