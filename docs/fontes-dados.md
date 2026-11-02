# Fontes e política de dados

## Indicadores macroeconômicos

| Dado | Fonte | Identificador | Uso |
|---|---|---|---|
| Selic meta | Banco Central do Brasil, SGS | Série 432 | Base da curva conservadora |
| IPCA em 12 meses | Banco Central do Brasil, SGS | Série 13522 | Retorno real e cenário |
| Expectativas da Selic | Banco Central, Olinda/Focus | `ExpectativasMercadoAnuais` | Nós anuais da curva |
| Ibovespa (opcional) | Yahoo Finance via `yfinance` | `^BVSP` | Volatilidade de 10 anos (cenário pessimista) e CAGR informativo |
| CDI anualizado (opcional) | Banco Central do Brasil, SGS | Série 4389 | Exibição e normalização de taxas em % do CDI |
| Poupança (opcional) | Banco Central do Brasil, SGS | Série 195 | Comparativo da projeção com a poupança |
| Expectativas do IPCA (opcional) | Banco Central, Olinda/Focus | `ExpectativasMercadoAnuais` | Exibição da inflação esperada |

As séries do SGS são consultadas em janela recente. Registros vazios,
malformados, não finitos ou com data futura são descartados.

O Focus é obtido pela biblioteca `python-bcb`. A ausência do Focus é tolerada;
Selic e IPCA são obrigatórios na implementação atual; o Ibovespa é opcional. CDI, poupança e
Focus IPCA são opcionais: quando faltam, o campo fica `None`, um aviso é
registrado e o comparativo correspondente é omitido.

Todas as fontes macroeconômicas são públicas e gratuitas, sem cadastro.

## Fontes de ativos

Os conectores variam por classe. Entre as integrações presentes no projeto
estão:

- BRAPI para listagem e dados de mercado;
- Yahoo Finance para históricos;
- Fundamentus e Status Invest nos módulos de ações e FIIs;
- dados públicos da CVM para fundos e para fundos previdenciários (FIEs
  de PGBL/VGBL), filtrados pela interseção cadastro ∩ informe diário;
- Tesouro Transparente para títulos públicos, incluindo Renda+ e Educa+
  (classificados como indexados ao IPCA);
- B3, via biblioteca `mercados`, para CRA, CRI e debêntures;
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

## Produtos sem fonte gratuita

CDB, LCI, LCA, LCD e COE não possuem base pública e gratuita com ofertas e
taxas atualizadas: cada emissor e cada plataforma publica as suas. Por isso
não há ranker automático para eles; o projeto prefere não exibir um ativo a
inventar uma taxa.

## Comportamento observado com dados reais (novembro de 2026)

- **Banco Central, Tesouro, CVM, CoinGecko, Fundamentus e Yahoo** responderam
  normalmente.
- **Status Invest e os sistemas da B3** (balcão, CRA/CRI/debêntures) usam
  proteção do Cloudflare que bloqueia IPs de servidores em nuvem. Em conexões
  residenciais costumam funcionar. Quando bloqueados, o app mostra a classe
  como indisponível em vez de inventar dados; a coleta de negociação de
  balcão para após alguns dias seguidos de falha.
- **CoinGecko (plano gratuito)** limita requisições por minuto. A listagem de
  mercado fica em cache por 10 minutos e as categorias usadas para excluir
  stablecoins, tokens embrulhados e de staking ficam em cache por 7 dias, em
  `~/.cache/arvore_investimentos/`.
- **Yahoo Finance** também limita consultas em sequência. O enriquecimento das
  ações é feito em paralelo moderado (6 consultas simultâneas).
- **CVM:** a primeira execução baixa cerca de 3 anos de informes diários
  (vários GB em `fundos/data/`) e leva alguns minutos; as seguintes usam o
  banco local. O arquivo do mês corrente só é publicado após os primeiros dias
  úteis, e a ausência dele não é tratada como erro.

## Filtros de investibilidade dos fundos

O ranking de fundos comuns exclui fundos para investidor profissional ou
qualificado, fundos fechados e fundos "master". No ranking de previdência, o
filtro de público-alvo não se aplica: o cotista de um FIE é a seguradora, e a
pessoa física compra o plano PGBL/VGBL.

## ETFs

A fatia "Fundos de Ações/ETF" da carteira só recebe ETFs de ações. A
classificação usa o nome oficial do fundo (Tesouro, IPCA, DAP, boi gordo,
ouro, bitcoin etc.) e, quando o nome é genérico, a volatilidade anual
observada: abaixo de 8% o ETF é tratado como renda fixa.
