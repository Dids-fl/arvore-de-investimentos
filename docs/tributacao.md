# Motor tributário

## Objetivo

O diretório `tributacao/` estima imposto e valor líquido por produto. O motor
não substitui apuração fiscal, declaração ou análise profissional.

As regras estão versionadas com vigência-base em 1º de janeiro de 2026. Uma
mudança legal deve criar nova regra ou nova vigência; não deve alterar
silenciosamente um cálculo histórico.

## Contrato

### `ContextoTributario`

Campos centrais:

- principal investido;
- valor bruto no resgate;
- data de aplicação;
- data de resgate;
- tipo do produto;
- regime previdenciário;
- renda tributável;
- vendas no mês;
- aportes no ano;
- indicador de day trade;
- pessoa física;
- metadados específicos.

O ganho é limitado a valores positivos para fins da estimativa atual.

### `ResultadoTributario`

O resultado contém:

- imposto estimado;
- valor líquido;
- alíquota efetiva;
- precisão;
- premissas;
- fonte;
- vigência;
- identificador da regra.

## Níveis de precisão

| Precisão | Significado |
|---|---|
| `exata_para_premissas` | A fórmula é determinística se todas as premissas informadas forem verdadeiras |
| `estimada` | Há simplificações relevantes ou contexto agregado |
| `indeterminada` | Faltam dados para produzir valor responsável |

`exata_para_premissas` não significa exatidão fiscal universal. Custos,
compensações, eventos e enquadramentos omitidos continuam fora do cálculo.

## Regras implementadas

### Renda fixa

- tabela regressiva de IR por prazo;
- IOF regressivo para resgates antes de 30 dias;
- hipótese de isenção para pessoa física em LCI, LCA, CRI, CRA e debênture
  incentivada;
- perdas, custos e desenquadramentos não são reconstruídos.

### Fundos

- fundo de ações;
- curto prazo;
- longo prazo;
- renda fixa;
- abatimento de `come_cotas_pago` quando informado;
- simulação prospectiva dos eventos futuros de come-cotas em maio e novembro;
- complemento de IR no resgate por lote e prazo.

O retorno calculado pela variação da cota é tratado como líquido das despesas
internas já refletidas na própria cota. Taxa de administração e performance
não são descontadas novamente. Sem histórico de cotas e eventos anteriores, o
resultado é estimado: o motor simula o futuro, mas não reconstrói come-cotas
passados.

### Previdência

- PGBL e VGBL;
- regimes regressivo e progressivo;
- PGBL tributado sobre o saldo conforme a premissa atual;
- VGBL tributado sobre o rendimento;
- tabela regressiva por prazo;
- estimativa incremental do regime progressivo.

Na comparação econômica entre PGBL e VGBL, o limite de dedução do PGBL é 12%
da renda tributável anual e é reduzido pelo valor de PGBL/FAPI já utilizado no
primeiro ano. A dedução somente é considerada quando declaração completa e
elegibilidade legal são confirmadas. O benefício anual é um fluxo fiscal fora
do plano e não aumenta automaticamente o saldo previdenciário.

As contribuições são agrupadas pelo ano-calendário de sua data. Uma projeção
iniciada em julho separa os pagamentos de julho a dezembro daqueles feitos no
ano seguinte. A renda pode ser informada por ano ou derivada de um crescimento
anual definido pelo usuário. A tabela de 2026 aplicada a anos futuros é sempre
identificada como cenário extrapolado, não como legislação conhecida.

Lotes previdenciários existentes podem ser informados em
`lotes_previdencia_existentes` com:

- `principal`: contribuição/custo original do lote;
- `saldo_atual`: valor atual incluído no capital da categoria;
- `data_aplicacao`: data ISO `AAAA-MM-DD`.

A soma de `saldo_atual` deve coincidir com o capital atual destinado àquela
categoria. O motor preserva a idade de cada lote e não converte
automaticamente PGBL em VGBL ou VGBL em PGBL.

No regime regressivo, aportes reais possuem idades distintas. Tratar o saldo
como lote único é uma aproximação e deve ser identificado como tal.

### Renda variável

- ações;
- ETFs;
- FIIs;
- operações comuns e day trade;
- prejuízo compensável e IRRF quando informados;
- hipótese de isenção mensal de ações para pessoa física, sem estender a ETFs,
  FIIs ou day trade.

O motor não reconstrói notas de corretagem, emolumentos ou todas as operações
do período.

### Criptoativos

- exige jurisdição de custódia;
- calcula faixas progressivas de ganho de capital;
- aceita isenção somente quando confirmada externamente;
- não decide automaticamente enquadramentos controversos.

Permutas, staking, offshore, compensações e obrigações acessórias exigem
tratamento próprio.

### Estruturados

COE, CRI, CRA e debêntures são encaminhados conforme subtipo. Um produto
estruturado genérico permanece indeterminado porque não existe alíquota única
para toda a classe.

## Integração

O catálogo associa cada categoria a um tratamento tributário. `calculos.py`
liquida os fluxos e o `engine.py` agrega:

- valor líquido;
- pior nível de precisão;
- premissas;
- fontes;
- enquadramento por categoria.

Se uma parcela relevante da carteira for indeterminada, o engine não deve
apresentar total líquido como exato.

## Fontes

As URLs oficiais ficam em `tributacao/regras.py` e incluem Receita Federal,
Previdência e Susep. Cada resultado carrega fonte, vigência e `regra_id`.

## Como adicionar ou alterar regra

1. Confirmar fonte primária e vigência.
2. Criar tabela ou função versionada.
3. Não sobrescrever regra histórica.
4. Atualizar o roteamento em `tributacao/__init__.py`.
5. Atualizar o catálogo quando houver novo produto.
6. Criar testes de limite, datas, isenção e contexto ausente.
7. Documentar premissas e casos não cobertos.
8. Revisar integração em `calculos.py` e `engine.py`.

## Validação ainda necessária

- casos reais calculados manualmente;
- revisão por profissional tributário;
- mudanças legais posteriores à vigência-base;
- conferência externa do estado histórico dos lotes importados;
- calendários de mercado posteriores ao último ano confirmado;
- compensações de renda variável;
- cripto no exterior e eventos não monetários;
- produtos estruturados com documentação específica.

## Ranking líquido

O ranking tributário é subordinado à adequação. Em fundos, o score de
eficiência líquida tem peso de 15%; os 85% restantes continuam ligados a
retorno, risco, fluxo, patrimônio, Sharpe e Sortino conforme o perfil. Em
previdência, PGBL e VGBL só são comparados depois de a finalidade
previdenciária ter sido definida, e a escolha ocorre pela maior TIR líquida
anual dos mesmos fluxos.
# Projeções por fluxo

## Previdência regressiva com múltiplos lotes

Quando a projeção possui capital inicial e aportes mensais, cada fluxo é
tratado como um lote separado. No regime regressivo, a alíquota de cada lote é
definida pelo tempo entre a data daquele aporte e o resgate projetado. PGBL é
tributado sobre o saldo do lote; VGBL, apenas sobre o rendimento do lote.

O regime progressivo continua agregado, pois depende da renda tributável e do
ajuste anual, não apenas da idade individual de cada aporte.

## Come-cotas prospectivo

Fundos de curto prazo, longo prazo e renda fixa passam a simular os eventos
futuros de come-cotas em maio e novembro. O imposto é retirado do saldo na data
projetada e, por isso, deixa de participar da capitalização posterior. No
resgate, o cálculo aplica por lote o eventual complemento para a alíquota final
e o IOF quando cabível.

A simulação não descobre eventos passados. Sem lotes importados, o capital
inicial é tratado como nova aplicação na data de referência. Os aportes ocorrem
no fim de cada mês. O calendário B3 confirmado e feriados adicionais
informados ajustam os eventos futuros. Fundos de ações não entram nessa rotina.

Quando houver dados de uma carteira real, a continuação prospectiva pode partir
de `lotes_fundo_existentes`. Cada lote exige:

- `principal`;
- `saldo_atual`;
- `base_tributaria_atual`, isto é, a base após o último evento informado;
- `ganho_antecipado` já submetido ao come-cotas;
- `come_cotas_pago_historico`;
- `data_aplicacao`.

O imposto histórico é informativo e não é descontado novamente do saldo atual.
Os eventos futuros continuam sendo simulados sobre o estado importado. O
calendário oficial da B3 de 2026 é incorporado; anos adicionais podem ser
confirmados por `anos_calendario_mercado_confirmados` e complementados por
`feriados_mercado`.
