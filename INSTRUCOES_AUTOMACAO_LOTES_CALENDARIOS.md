# Automação de lotes, come-cotas histórico e calendários B3

## Aplicação do pacote

Na raiz do repositório, com o ZIP também na raiz:

```powershell
Expand-Archive `
  -LiteralPath .\automacao_calendario_b3_automatico.zip `
  -DestinationPath . `
  -Force

python -m pip install --upgrade -r requirements.txt
```

Novas dependências:

- `openpyxl`: leitura de XLSX/XLSM;
- `holidays`: fallback provisório de feriados nacionais quando ainda não há
  calendário anual da B3 versionado.

`pandas`, já usado pelo projeto, faz a leitura e normalização tabular.

## Importação dos lotes

A interface aceita CSV, XLSX ou XLSM. Use como base:

```text
modelos/lotes_tributarios_exemplo.csv
```

Colunas obrigatórias:

- `categoria`: chave canônica do catálogo, como `fundos_rf`, `prev_pgbl` ou
  `prev_vgbl`;
- `tipo_lote`: `fundo` ou `previdencia`;
- `principal`;
- `saldo_atual`;
- `data_aplicacao`.

Para fundos também são obrigatórios:

- `base_tributaria_atual`;
- `ganho_antecipado` (pode ser zero);
- `come_cotas_pago_historico` (pode ser zero).

`saldo_categoria_esperado` é recomendado. Quando informado, o importador
confere se a soma dos lotes fecha com o extrato. O engine faz uma segunda
reconciliação contra o capital destinado à categoria na projeção.

O importador rejeita datas futuras, números negativos, IDs duplicados,
categorias sem saldo reconciliado e conflito entre lotes da planilha e lotes
digitados no JSON avançado.

## Sincronização automática dos calendários da B3

Ao iniciar `python main.py` ou `streamlit run app.py`, o sistema consulta a
página estável do calendário oficial da B3 e procura as seções do ano atual e
do ano seguinte. Não é necessário informar manualmente o ano.

O sincronizador:

- aceita somente uma resposta HTTPS no domínio oficial `b3.com.br`;
- extrai somente dias em que a própria tabela informa que não haverá
  negociação no segmento `Listado B3`;
- ignora horários especiais e feriados que afetam apenas mercados externos;
- exige quantidade plausível de fechamentos e a presença dos fechamentos
  nacionais mínimos esperados;
- aceita somente o ano atual ou o seguinte;
- grava o JSON em cache por troca atômica e mantém uma cópia `.bak`;
- preserva integralmente o calendário anterior quando a rede, a estrutura da
  página ou qualquer validação falha.

O cache validado fica, por padrão, em:

```text
~/.cache/recomendador_investimentos/calendarios/b3/
```

É possível mudar o diretório com a variável
`RECOMENDADOR_CALENDARIOS_CACHE_DIR`. O arquivo empacotado
`calendarios/b3/2026.json` continua sendo o fallback versionado.

Enquanto a B3 ainda não tiver publicado a seção do próximo ano, `holidays`
calcula somente os feriados nacionais e o resultado permanece explicitamente
provisório. Ele nunca é promovido automaticamente a calendário oficial.

Para conferir a sincronização sem abrir a interface:

```powershell
python -m calendarios.sincronizar_b3
```

Os estados `atualizado` e `sem_alteracao` indicam sucesso. `nao_publicado` é
esperado para o ano seguinte enquanto a seção ainda não existir.
`fonte_indisponivel` e `rejeitado` preservam o cache e fazem o comando terminar
com código de erro, para que CI e automações percebam o problema.

### Registro manual de contingência

O comando abaixo permanece disponível somente se a B3 publicar o calendário
em um formato que o extrator ainda não reconheça. Depois de revisão humana,
crie um arquivo com uma data ISO por linha e execute:

```powershell
python -m calendarios.registrar_b3 `
  --ano 2027 `
  --fonte "https://www.b3.com.br/URL-OFICIAL" `
  --datas .\datas_b3_2027.txt
```

O comando recusa fonte fora do domínio oficial, datas inválidas e datas de
outro ano. O arquivo gerado deve ser revisado antes de ser versionado no Git.

## Validação

```powershell
ruff check .

python -m pytest -q `
  .\tests\unit\test_importacao_lotes_calendarios.py `
  .\tests\unit\test_projecoes_tributarias.py `
  --tb=short

python -m pytest -q tests -m "not slow" --tb=short
git diff --check
git status --short
```

## Limites que permanecem

- A planilha automatiza a transcrição, não certifica a base fiscal fornecida
  pela instituição.
- O Open Finance pode complementar posição e movimentações, mas não garante
  base tributária completa nem histórico anterior ao período disponibilizado.
- O fallback de `holidays` não inclui necessariamente fechamentos especiais da
  B3; por isso anos sem JSON oficial continuam sinalizados como provisórios.
- Mudanças relevantes no texto ou na estrutura da página oficial são tratadas
  como rejeição segura; o sistema não tenta adivinhar um novo formato.
- Não há extração automática de PDF ou OCR, porque isso criaria risco de erro
  silencioso em valores tributários.
