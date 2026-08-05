Validação tributária independente

Este diretório mantém cálculos de conferência separados das fórmulas deprodução. O objetivo é detectar regressões e tornar explícitas as premissasque impedem uma conclusão tributária automática.

Escopo deste pacote

Os validadores independentes cobrem cinco grupos:

renda fixa;

fundos;

previdência privada;

renda variável;

produtos estruturados.

O validador de criptoativos já existente continua separado porque cobrequatro casos críticos com uma estrutura de relatório anterior.

Os módulos de cálculo independente não importam tributacao.regras. A camadacomum.py importa somente a fachada pública do motor para comparar trêsresultados: cálculo independente, saída do motor e caso dourado da fixture.

Como executar

Na raiz do repositório:

python -m validacao.tributacao.validar_tudo `
  --saida .\validacao\tributacao\relatorios

python -m pytest -q `
  .\tests\unit\test_tributacao.py `
  .\tests\unit\test_tributacao_casos_dourados.py `
  .\tests\unit\test_validadores_tributarios_independentes.py `
  --tb=short

ruff check .

O comando consolidado retorna código diferente de zero quando encontraDIVERGENTE. Pendências e casos fora do escopo são registrados, mas nãoderrubam o CI porque representam limitações declaradas, não regressões.

Significado dos estados

Estado

Significado

VALIDADO_PRIMEIRA_CAMADA

Fórmula independente, fixture e motor coincidem e não há premissa pendente no caso simplificado.

PENDENTE_PREMISSA

A aritmética coincide, mas falta confirmar vigência, classificação, documento ou dado obrigatório. Resultados indeterminados por falta de entrada permanecem neste estado.

FORA_DO_ESCOPO

A pessoa, o produto ou o regime tributário não é suportado pelo escopo declarado do motor. Não deve ser usado apenas porque faltou um dado de entrada.

DIVERGENTE

Cálculo independente, fixture ou motor não coincidem dentro da tolerância.

Resultado de referência do lote

Os 55 casos dos cinco grupos produziram:

17 validados na primeira camada;

35 pendentes por premissa ou dado obrigatório;

3 fora do escopo;

0 divergências.

Quatro casos anteriormente classificados como fora do escopo foramreclassificados como pendentes:

cri_sem_confirmacao_de_elegibilidade;

estruturado_generico_indeterminado;

pgbl_progressivo_sem_renda;

pgbl_regime_ausente.

Esses números não significam validação fiscal universal. Eles demonstram que,para as entradas e simplificações declaradas, os cálculos independentes e omotor concordam.

Limitações que permanecem

Renda fixa: resgates posteriores a 2026 mantêm a legislação de 2026 comohipótese; pessoa jurídica não é calculada.

Fundos: o valor de come-cotas é informado externamente, sem reconstrução dohistórico de cotas, eventos e classificação concreta do fundo.

Previdência: o regressivo usa um lote único; o progressivo depende da baseanual e de deduções informadas.

Renda variável: vendas, custos, IRRF e prejuízos por modalidade são dados deentrada; notas de corretagem e operações simultâneas não são reconstruídas.

Estruturados: CRI, CRA e debênture incentivada só recebem isenção quando aelegibilidade do instrumento é confirmada explicitamente.

Revisão humana

A planilha matriz_validacao_tributaria.xlsx concentra resultados, fontes,pendências e campos para revisor/data. Marcar um caso como revisado exige:

abrir a fonte oficial e confirmar a vigência;

conferir o enquadramento do produto e da pessoa;

refazer a memória de cálculo fora do motor;

registrar o revisor, a data e a evidência;

tratar qualquer divergência antes de aprovar.

Esta validação é técnica e de primeira camada. Ela não substitui apuraçãooficial nem parecer contábil ou jurídico para uma operação real.