# Arquitetura

## Objetivo

A arquitetura separa interface, coleta de dados, decisão, projeção, tributação
e seleção de ativos. O `engine.py` funciona como fachada da lógica de negócio:
as interfaces enviam respostas e dados de mercado e recebem uma análise
estruturada.

## Fluxo principal

```text
main.py / app.py
       |
       +--> mercado.py ------------------------------+
       |                                             |
       +--> engine.criar_analise(respostas, market)  |
                         |                           |
                         +--> recomendador.py        |
                         +--> portfolio.py           |
                         +--> core/catalogo.py       |
                         +--> macroeconomia/         |
                         +--> calculos.py            |
                         +--> tributacao/            |
                         |                           |
                         +--> resultado estruturado <-+
                                      |
                                      +--> recomendador_ativos.py
                                      +--> exportação JSON
```

O diretório `backtest/` não participa desse caminho em produção. Ele existe
para avaliar estratégias com dados históricos sem acoplar o experimento ao
motor de recomendação.

## Componentes

| Componente | Responsabilidade |
|---|---|
| `main.py` | Questionário em terminal, apresentação e exportação local |
| `app.py` | Interface Streamlit e visualização da análise |
| `mercado.py` | Coleta, validação, concorrência e cache de indicadores |
| `engine.py` | Validação de entrada, orquestração e contrato da análise |
| `recomendador.py` | Regras de adequação e recomendação principal |
| `portfolio.py` | Construção, normalização e classificação da alocação |
| `core/catalogo.py` | Catálogo de categorias, produtos, risco e tratamento fiscal |
| `calculos.py` | Valor futuro, fluxos, inflação e liquidação tributada |
| `macroeconomia/curva_selic.py` | Curva mensal composta a partir da Selic e Focus |
| `tributacao/` | Motor fiscal por classe de produto |
| `recomendador_ativos.py` | Orquestração dos rankers por classe relevante |
| `acoes_fiis/`, `etfs/`, `fundos/`, `renda_fixa/`, `cripto/` | Coletores e rankers especializados |
| `backtest/` | Simulação histórica, benchmarks, métricas e walk-forward |
| `tests/` | Testes unitários, integração e fixtures determinísticos |

## Contratos centrais

### Dados de mercado

`mercado.load_market_data()` devolve um dicionário versionado. Os principais
campos são:

- `selic`;
- `focus_selic`;
- `focus_selic_por_ano`;
- `ipca`;
- `ibov_cagr`;
- `data_ref`;
- `fontes`;
- `avisos`;
- `fetched_at`;
- `cache_status`;
- `_schema_version`.

Selic, IPCA e CAGR do Ibovespa são obrigatórios para o motor atual. A curva do
Focus é opcional e sua ausência deve gerar aviso, não um número fictício.

### Análise

`engine.criar_analise()` é o ponto de entrada recomendado para consumidores. A
resposta contém:

- respostas normalizadas;
- resultado da recomendação;
- carteira e categorias;
- hipóteses de retorno;
- projeções por prazo;
- cenários central e pessimista;
- estimativas tributárias e nível de precisão;
- análise de meta, quando solicitada;
- fontes, premissas e avisos.

As interfaces não devem duplicar regras de negócio. Alterações de adequação,
taxa, meta ou tributação pertencem ao engine ou ao módulo especializado.

### Ativos sugeridos

`recomendador_ativos.recomendar_por_portfolio()` consulta somente classes com
alocação relevante. Uma falha isolada deve ser registrada em
`_indisponiveis`, sem apagar resultados obtidos de outras classes.

## Tratamento de erros

- Entrada inválida gera `TypeError` ou `ValueError`.
- Dívida de juros altos pode bloquear a recomendação por uma exceção de
  domínio.
- Ausência de dados obrigatórios gera `DadosIndisponiveisError`.
- Dados opcionais indisponíveis geram avisos.
- O cache antigo só pode ser usado dentro do limite configurado e deve ser
  identificado como `stale`.
- Rankers externos devem degradar parcialmente em vez de derrubar toda a
  análise.

## Decisões de projeto

1. **Sem fallback numérico inventado:** uma fonte real anterior pode ser usada
   com aviso; uma constante arbitrária não.
2. **Engine independente da interface:** CLI e Streamlit consomem o mesmo
   contrato.
3. **Tributação com precisão explícita:** resultado indeterminado é preferível
   a uma falsa exatidão.
4. **Backtest separado:** resultados históricos não alteram automaticamente as
   regras de produção.
5. **Fixtures locais:** testes determinísticos não dependem de APIs externas.

## Pontos de atenção arquiteturais

- `engine.py` concentra muitas responsabilidades e deve ser decomposto
  gradualmente se continuar crescendo.
- Os rankers dependem de fontes com contratos e disponibilidade diferentes.
- A consistência entre o catálogo e o motor tributário precisa ser testada
  sempre que uma categoria for adicionada.
- Mudanças no schema de mercado devem incrementar `CACHE_SCHEMA_VERSION`.
