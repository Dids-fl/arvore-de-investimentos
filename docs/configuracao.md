# Configuração

## Ambiente

O projeto lê variáveis do sistema e, quando `python-dotenv` está instalado, de
um arquivo `.env`. O arquivo `.env` é local e não deve ser versionado.

Valores numéricos aceitam ponto ou vírgula. Valores inválidos, não finitos ou
abaixo do mínimo geram erro no carregamento.

## HTTP

| Variável | Padrão | Restrição |
|---|---:|---:|
| `REQUEST_CONNECT_TIMEOUT` | `5.0` segundos | maior ou igual a `0.1` |
| `REQUEST_READ_TIMEOUT` | `15.0` segundos | maior ou igual a `0.1` |
| `MAX_RETRIES` | `3` | inteiro maior ou igual a zero |
| `RETRY_BACKOFF` | `0.5` | maior ou igual a zero |
| `MAX_WORKERS_ATIVOS` | `4` | inteiro maior ou igual a um |

O coletor de mercado aplica retry somente a `GET`, respeita `Retry-After` e
trata 429, 500, 502, 503 e 504 como respostas recuperáveis.

## Credenciais opcionais

| Variável | Finalidade |
|---|---|
| `BRAPI_TOKEN` | Aumentar ou habilitar acesso à BRAPI conforme o plano |
| `FMP_API_KEY` | Integrações que utilizem Financial Modeling Prep |

Nunca registre valores reais em logs, fixtures, commits ou documentação.

## Ações e FIIs

| Variável | Padrão | Finalidade |
|---|---|---|
| `USE_FUNDAMENTUS` | `true` | Habilita a fonte Fundamentus |
| `FILTRO_SETORES` | vazio | Lista separada por vírgulas |
| `FILTRO_GOVERNANCA` | vazio | Lista separada por vírgulas |
| `MKTCAP_CONSERVADOR` | `2000000000` | Corte mínimo do perfil 1 |
| `MKTCAP_MODERADO` | `1000000000` | Corte mínimo do perfil 2 |
| `MKTCAP_AGRESSIVO` | `500000000` | Corte mínimo do perfil 3 |

Os cortes são heurísticos. Alterá-los exige novo teste de sensibilidade e
backtest.

## Saída

`main.py` lê `INVEST_OUTPUT_DIR` para definir o diretório de exportação. Quando
ausente, usa o diretório atual.

## Exemplo de `.env.example`

```dotenv
REQUEST_CONNECT_TIMEOUT=5
REQUEST_READ_TIMEOUT=15
MAX_RETRIES=3
RETRY_BACKOFF=0.5
MAX_WORKERS_ATIVOS=4

BRAPI_TOKEN=
FMP_API_KEY=

USE_FUNDAMENTUS=true
FILTRO_SETORES=
FILTRO_GOVERNANCA=

MKTCAP_CONSERVADOR=2000000000
MKTCAP_MODERADO=1000000000
MKTCAP_AGRESSIVO=500000000

INVEST_OUTPUT_DIR=.
```

## Booleans aceitos

Verdadeiro:

```text
1, true, sim, yes, on
```

Falso:

```text
0, false, não, nao, no, off
```

## Recomendações operacionais

- use timeouts menores no desenvolvimento somente se as APIs responderem bem;
- evite paralelismo alto para não provocar rate limit;
- mantenha tokens fora do repositório;
- registre configuração usada em backtests;
- não mude cortes de ranking sem validar o efeito fora da amostra.
