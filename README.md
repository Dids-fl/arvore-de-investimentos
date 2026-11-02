# Árvore de Investimentos

Recomendador educacional de investimentos para o Brasil. A partir de um
questionário de perfil, o sistema sugere uma alocação por classe de ativo,
projeta o patrimônio (bruto, líquido de impostos e em poder de compra), compara
o resultado com a poupança e, opcionalmente, ranqueia ativos específicos de
cada classe.

Tudo roda com **dados públicos e gratuitos**, sem cadastro obrigatório, e os
dados são atualizados automaticamente ao rodar o app (com cache local):

| Dado | Fonte gratuita |
|---|---|
| Selic, IPCA 12 meses, CDI, poupança | Banco Central (SGS) |
| Expectativas de Selic e IPCA | Banco Central (Focus/Olinda) |
| Ibovespa e históricos | Yahoo Finance (`yfinance`) |
| Títulos públicos (inclui Renda+ e Educa+) | Tesouro Transparente |
| Fundos e previdência (PGBL/VGBL) | Dados abertos da CVM |
| Ações e FIIs | BRAPI (plano gratuito), Fundamentus, Status Invest |
| CRA, CRI e debêntures | B3 (biblioteca `mercados`) |
| Criptoativos | CoinGecko (API gratuita) |

> **Aviso:** projeto educacional e experimental. Não é recomendação individual
> de investimento, consultoria nem orientação tributária. Veja
> [Limitações e riscos](docs/limitacoes.md).

## Instalação

Requer Python 3.11, 3.12 ou 3.13.

```bash
git clone https://github.com/Dids-fl/arvore-de-investimentos.git
cd arvore-de-investimentos

python -m venv .venv
source .venv/bin/activate      # Linux/Mac
# .venv\Scripts\activate       # Windows

pip install -r requirements.txt
```

Opcional: copie `.env.example` para `.env` para ajustar timeouts ou informar um
token gratuito da BRAPI (aumenta o limite de requisições).

## Como usar

**Interface web (Streamlit):**

```bash
streamlit run app.py
```

**Terminal:**

```bash
python main.py
```

Na primeira pergunta do terminal, digite `d` para rodar um perfil de
demonstração. Valores em reais aceitam o formato brasileiro (`1.500,00`).

**Backtest das estratégias:**

```bash
python -m backtest.run_backtest --help
```

## O que a análise entrega

- recomendação principal e alocação por classe, com avisos sobre cada ajuste;
- plano de reserva de emergência (só o déficit é separado);
- projeções em 1, 2, 5, 10, 20 e 30 anos, com cenário pessimista;
- imposto estimado por classe, marcado como *indeterminado* quando faltam
  dados (nunca com alíquota genérica inventada);
- comparativo com a poupança, quando a série do BCB está disponível;
- análise de meta (quanto aportar por mês para chegar a um valor);
- ranking de ativos específicos (Tesouro, fundos, previdência, CRA/CRI/
  debêntures, ações, FIIs, ETFs e cripto) e exportação em JSON.

CDB, LCI, LCA e COE não têm ranking de ativos: não existe fonte pública e
gratuita com as ofertas e taxas dos bancos. Eles continuam cobertos nas
regras de recomendação e no motor tributário.

## Validação com dados do passado

`python -m backtest.validacao_historica` volta a datas passadas, monta os dados
como estavam naquele dia e compara a previsão do app com o que aconteceu. O
resultado mais recente está em
[docs/validacao-historica.md](docs/validacao-historica.md).

## Desenvolvimento

```bash
pip install -r requirements.txt -r requirements-dev.txt

python -m ruff check .
python -m pytest -m "not slow"                      # testes sem internet
python -m validacao.tributacao.validar_tudo --saida relatorios_tributarios
```

Testes marcados como `slow` acessam APIs reais. Os demais rodam sem internet:
qualquer tentativa de conexão em um teste comum falha imediatamente.

## Documentação

A documentação técnica fica em [`docs/`](docs/indice.md): arquitetura,
metodologia, fontes de dados, motor tributário, configuração, testes e
limitações.
