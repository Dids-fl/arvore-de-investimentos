# Validação tributária independente

Este diretório mantém uma segunda implementação das fórmulas, separada das
tabelas de produção, e ferramentas de governança para auditar o motor.

## O que o pacote cobre

- 63 casos dourados de renda fixa, fundos, previdência, renda variável,
  estruturados e criptoativos;
- comparação entre cálculo independente, fixture e motor de produção;
- registro versionado de fontes oficiais e auditoria estrutural offline;
- reconciliação com informes ou memórias de cálculo reais anonimizados;
- registro de revisão humana vinculado ao SHA-256 do relatório;
- execução determinística no CI.

## Estados

| Estado | Significado |
|---|---|
| `VALIDADO_CALCULO` | Fórmula independente, fixture e motor coincidem, sem evidência pendente no caso simplificado. |
| `VALIDADO_GUARDRAIL` | O motor recusou corretamente calcular porque faltou um dado essencial. |
| `PENDENTE_EVIDENCIA` | A aritmética coincide, mas uma classificação, documento, vigência futura ou dado externo ainda precisa ser comprovado. |
| `FORA_DO_ESCOPO` | O caso não pertence ao produto declarado, como pessoa jurídica ou BDR. |
| `DIVERGENTE` | O independente, a fixture ou o motor não coincidem dentro da tolerância. |

## Execução

```powershell
python -m validacao.tributacao.validar_tudo `
  --saida .\validacao\tributacao\relatorios

python -m validacao.tributacao.auditar_fontes `
  --saida .\validacao\tributacao\relatorios\auditoria_fontes.json

python -m validacao.tributacao.reconciliar_documentos `
  .\modelos\casos_tributarios_reais_anonimizados.json `
  --saida .\validacao\tributacao\relatorios\reconciliacao_exemplo.json

python -m pytest -q `
  .\tests\unit\test_tributacao.py `
  .\tests\unit\test_tributacao_casos_dourados.py `
  .\tests\unit\test_validadores_tributarios_independentes.py `
  .\tests\unit\test_governanca_tributaria.py `
  --tb=short
```

Opcionalmente, `auditar_fontes --online` registra status HTTP, URL final,
ETag, Last-Modified e SHA-256 do conteúdo consultado. Essa verificação ajuda a
detectar mudança ou indisponibilidade, mas não interpreta a norma e não deve
ser obrigatória no CI, pois depende de rede e de proteção antibot dos portais.

## Reconciliação com documentos reais

Copie o modelo em `modelos/casos_tributarios_reais_anonimizados.json` e
substitua apenas valores já anonimizados. O importador bloqueia chaves comuns
de identificação pessoal. A reconciliação compara imposto e valor líquido do
documento com o motor, registra a regra, fonte, vigência e diferenças.

Não envie CPF, CNPJ, nome, conta, agência, endereço ou documento integral ao
repositório. Guarde a evidência original em ambiente restrito e registre no
JSON somente um identificador anonimizado.

## Revisão profissional

Depois de revisar fontes e documentos, o profissional pode registrar sua
decisão:

```powershell
python -m validacao.tributacao.registrar_revisao `
  .\validacao\tributacao\relatorios\relatorio_tributario_consolidado.json `
  --saida .\validacao\tributacao\revisoes\revisao_2026.json `
  --revisor "NOME DO REVISOR" `
  --credencial "OAB ou CRC" `
  --registro-profissional "UF 000000" `
  --decisao aprovado_com_ressalvas `
  --escopo "Pessoa física residente no Brasil; casos listados" `
  --ressalva "Legislação futura deve ser revalidada" `
  --declaro-responsabilidade
```

O registro guarda o hash do relatório para detectar alteração posterior. O
software não autentica identidade, habilitação ou situação do registro.

## Limite jurídico

Este pacote é evidência de engenharia e apoio à revisão. Ele não constitui
certificação jurídica, parecer legal, apuração fiscal oficial ou garantia de
tratamento para qualquer operação real. A conclusão jurídica exige documento
da operação, legislação vigente na data relevante e profissional habilitado.
