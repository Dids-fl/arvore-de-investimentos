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
- abatimento de `come_cotas_pago` quando informado.

Sem histórico de cotas e eventos, o resultado é estimado. O motor não reproduz
automaticamente todos os come-cotas passados.

### Previdência

- PGBL e VGBL;
- regimes regressivo e progressivo;
- PGBL tributado sobre o saldo conforme a premissa atual;
- VGBL tributado sobre o rendimento;
- tabela regressiva por prazo;
- estimativa incremental do regime progressivo.

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
- come-cotas com histórico de cotas;
- previdência por lote;
- compensações de renda variável;
- cripto no exterior e eventos não monetários;
- produtos estruturados com documentação específica.
