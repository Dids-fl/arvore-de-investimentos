# Documentação técnica

Esta pasta descreve o funcionamento interno do recomendador de investimentos.
O `README.md` não faz parte deste conjunto e deve permanecer como apresentação
curta do projeto.

## Navegação

- [Arquitetura](arquitetura.md): componentes, responsabilidades e fluxo de
  execução.
- [Metodologia de recomendação](metodologia.md): formação do perfil, carteira,
  taxas e projeções.
- [Fontes e política de dados](fontes-dados.md): origem, validação, cache e
  indisponibilidade.
- [Motor tributário](tributacao.md): contratos, escopo, precisão e limitações
  fiscais.
- [Configuração](configuracao.md): variáveis de ambiente e parâmetros
  operacionais.
- [Testes e integração contínua](testes-ci.md): organização da suíte, comandos
  e workflow.
- [Validação financeira](validacao-financeira.md): o que já existe e o
  protocolo necessário para medir eficácia.
- [Limitações e riscos](limitacoes.md): restrições técnicas, financeiras,
  tributárias e operacionais.

## Estado da documentação

Esta documentação representa o código observado em 30 de julho de 2026. Em
caso de divergência, o comportamento do código e os testes automatizados são a
fonte de verdade.

## Escopo do sistema

O sistema:

1. coleta indicadores macroeconômicos;
2. valida um questionário de perfil;
3. aplica regras de adequação e restrições;
4. constrói uma alocação por categorias;
5. calcula projeções brutas, líquidas e reais;
6. estima o tratamento tributário quando há contexto suficiente;
7. consulta rankers de ativos compatíveis com a carteira;
8. permite análise por CLI e Streamlit;
9. oferece infraestrutura de backtest separada do motor de recomendação.

O sistema não substitui avaliação profissional, não garante retorno e ainda não
possui evidência quantitativa suficiente para afirmar que suas recomendações
superam benchmarks.
