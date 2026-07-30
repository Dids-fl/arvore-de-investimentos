# Fontes e política de dados

## Indicadores macroeconômicos

| Dado | Fonte | Identificador | Uso |
|---|---|---|---|
| Selic meta | Banco Central do Brasil, SGS | Série 432 | Base da curva conservadora |
| IPCA em 12 meses | Banco Central do Brasil, SGS | Série 13522 | Retorno real e cenário |
| Expectativas da Selic | Banco Central, Olinda/Focus | `ExpectativasMercadoAnuais` | Nós anuais da curva |
| Ibovespa | Yahoo Finance via `yfinance` | `^BVSP` | CAGR histórico de 10 anos |

As séries do SGS são consultadas em janela recente. Registros vazios,
malformados, não finitos ou com data futura são descartados.

O Focus é obtido pela biblioteca `python-bcb`. A ausência do Focus é tolerada;
Selic, IPCA e Ibovespa são obrigatórios na implementação atual.

## Fontes de ativos

Os conectores variam por classe. Entre as integrações presentes no projeto
estão:

- BRAPI para listagem e dados de mercado;
- Yahoo Finance para históricos;
- Fundamentus e Status Invest nos módulos de ações e FIIs;
- dados públicos da CVM para fundos;
- CoinGecko para criptoativos.

Cada ranker deve registrar sua fonte e degradar de forma independente. A
existência de um conector não garante cobertura completa, estabilidade do
contrato ou direito de redistribuição dos dados.

## Cache de mercado

O cache de mercado:

- é salvo em
  `~/.cache/recomendador_investimentos_market.json`;
- possui TTL fresco de 6 horas;
- pode ser reutilizado por até 7 dias quando a atualização falha;
- recebe `cache_status = "fresh"` ou `"stale"`;
- inclui horário de coleta, fontes e avisos;
- usa schema versionado;
- é escrito de forma atômica.

O schema atual é `4`, que inclui `focus_selic_por_ano`. Um cache com schema
antigo ou campos inválidos é rejeitado.

## Política de indisponibilidade

1. Não substituir dado ausente por taxa fixa inventada.
2. Usar cache real anterior somente dentro do limite de idade.
3. Marcar cache antigo e explicar quais campos não foram atualizados.
4. Tratar Focus como opcional.
5. Interromper projeções quando um indicador obrigatório não puder ser obtido.
6. Permitir falha parcial dos rankers de ativos.

## Validação

Taxas são representadas em decimal:

```text
0.1425 = 14,25% ao ano
```

O coletor verifica:

- tipo numérico;
- finitude;
- intervalo plausível;
- presença de referência temporal;
- estrutura do payload;
- versão do cache.

Essas verificações detectam corrupção e respostas inesperadas, mas não
certificam que a fonte publicou um número economicamente correto.

## Reprodutibilidade

Execuções em datas diferentes podem produzir recomendações diferentes porque:

- indicadores macroeconômicos mudam;
- universos de ativos mudam;
- históricos recebem ajustes;
- APIs podem corrigir dados retroativamente;
- fundos podem surgir, encerrar ou mudar de classe.

Uma validação reproduzível deve armazenar:

- data e hora de coleta;
- payload bruto ou snapshot autorizado;
- versão do código;
- parâmetros;
- universo elegível;
- versões das regras tributárias;
- resultados e logs.

## Credenciais e configuração

Credenciais opcionais são lidas do ambiente, nunca devem ser commitadas. Entre
as variáveis reconhecidas estão:

- `BRAPI_TOKEN`;
- `FMP_API_KEY`.

Use `.env` apenas localmente e mantenha `.env.example` sem segredos.

## Riscos conhecidos

- alteração de contrato de API;
- rate limit;
- indisponibilidade;
- ticker incorreto ou descontinuado;
- campo ausente em metadados;
- viés de sobrevivência;
- dados sem informação point-in-time;
- diferenças de calendário, timezone e ajustes de preço.

Consulte também [Limitações e riscos](limitacoes.md).
