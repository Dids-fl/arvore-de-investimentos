Testes e integração contínua

Estrutura

tests/
├── fixtures/
│   ├── ativos.json
│   ├── mercado.json
│   └── perfis_validacao.json
├── integration/
│   ├── test_mercado.py
│   └── test_rankers.py
├── unit/
│   ├── test_backtest.py
│   ├── test_calculos.py
│   ├── test_engine.py
│   ├── test_heuristicas.py
│   ├── test_portfolio.py
│   ├── test_recomendador.py
│   └── test_tributacao.py
└── test_*.py

Objetivos

Unitários

Validam funções puras e regras isoladas:

cálculos financeiros;

recomendação;

carteira;

engine;

tributação;

métricas e simulador de backtest.

Integração

Validam contratos entre módulos sem depender de internet:

schema e cache de mercado;

coletores simulados;

falha parcial dos rankers;

roteamento por classe.

Fixtures

mercado.json: payload macroeconômico válido e versionado;

ativos.json: candidatos fictícios para rankers;

perfis_validacao.json: cenários de adequação e restrições.

Fixtures não representam cotação, oferta ou recomendação real.

Comandos

Compilação

python -m compileall -q \
  backtest macroeconomia tributacao tests \
  core calculos.py engine.py mercado.py main.py app.py

Suíte determinística

pytest -q tests/unit tests/integration -m "not slow" --tb=short

Suíte completa

pytest -q --tb=short

Cobertura

pytest -q tests/unit tests/integration -m "not slow" \
  --cov=backtest \
  --cov=tributacao \
  --cov-report=term-missing \
  --cov-report=html

Ruff

ruff check .

Para mudanças pequenas, prefira verificar apenas os arquivos alterados antesde enfrentar a dívida técnica histórica do repositório.

Integração contínua

O workflow .github/workflows/tests.yml executa em:

Python 3.11;

Python 3.12;

push;

pull_request;

execução manual por workflow_dispatch.

Etapas:

checkout;

instalação das dependências;

compilação dos pacotes e módulos centrais;

Ruff em todo o repositório, limitado a erros críticos;

testes unitários, de integração e score determinístico de cripto semmarcador slow;

cobertura de backtest e tributacao;

mínimo de 65% para esses dois pacotes;

relatório XML e HTML publicado pelo job Python 3.12 por 14 dias.

O timeout atual do job é 20 minutos. Execuções antigas do mesmo branch sãocanceladas quando uma nova execução começa.

Estado observado

Na validação local de 30 de julho de 2026:

122 testes haviam sido aprovados considerando a suíte completa e a repetiçãodos casos corrigidos;

62 testes determinísticos passaram na validação do CI;

a cobertura combinada de backtest e tributacao foi de 77,41%;

o limite mínimo configurado de 65% foi atendido;

os cinco warnings conhecidos foram corrigidos;

os arquivos recentes passaram no Ruff;

o repositório possuía dívida técnica histórica fora do conjunto alterado.

Esse número é um snapshot, não um requisito fixo. Ao adicionar funcionalidade,o total deve aumentar e os testes existentes devem permanecer verdes.

Testes externos

Chamadas reais a Yahoo Finance, BRAPI, CoinGecko, BCB e outras fontes sãoinstáveis por natureza. Elas devem:

usar marcador slow ou external;

ficar fora do job determinístico;

rodar sob demanda ou em agenda;

não substituir mocks de contrato;

registrar claramente falha de rede versus regressão lógica.

Regras para novos testes

Não retornar booleano de uma função test_*; usar assert.

Não depender do relógio sem controlar data ou timezone.

Não depender de cache do usuário.

Não compartilhar estado mutável entre testes.

Usar fixture para payloads grandes.

Cobrir entradas válidas, inválidas e limites.

Testar comportamento degradado de fontes externas.

Evitar afirmar retorno financeiro em teste unitário.

Pendências

ampliar cobertura para engine e rankers;

confirmar o workflow verde no GitHub Actions;

separar claramente testes externos no pytest.ini;

reduzir gradualmente os alertas do Ruff.