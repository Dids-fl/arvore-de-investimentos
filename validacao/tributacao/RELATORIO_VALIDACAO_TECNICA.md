# Relatório técnico — validação tributária independente

Data-base: 2026-08-05.

## Resultado automatizado

| Estado | Casos |
|---|---:|
| Cálculos validados | 21 |
| Guardrails validados | 5 |
| Pendentes por evidência | 34 |
| Fora do escopo | 3 |
| Divergentes | 0 |
| **Total** | **63** |

Todos os seis grupos são processados pelo mesmo consolidado. O validador de
cripto deixou de comparar apenas quatro valores esperados e passou a executar
os oito casos contra a fachada real do motor.

## Controles acrescentados

- taxonomia separa falta de dado de produto realmente não suportado;
- registro `fontes_oficiais.json` contém autoridade, URL, vigência, consulta,
  escopo e estado de revisão;
- auditoria offline bloqueia fonte não oficial, HTTP, data futura, ID ausente
  ou URL divergente;
- reconciliação aceita documentos anonimizados e mede diferença monetária;
- dados pessoais comuns são rejeitados antes da reconciliação;
- termo de revisão guarda o SHA-256 do relatório e detecta adulteração;
- CI executa consolidado, auditoria de fontes e reconciliação de referência.

## O que os números comprovam

`DIVERGENTE = 0` comprova apenas que, nos 63 cenários versionados, a segunda
implementação, as fixtures e o motor atual coincidem dentro da tolerância.
`VALIDADO_GUARDRAIL` comprova que o software se recusou a inventar imposto
quando uma informação obrigatória não existia.

## O que ainda exige ser humano

Os 34 casos pendentes não são defeitos aritméticos. Eles dependem de uma ou
mais evidências externas: classificação do instrumento, extrato e histórico
de cotas, notas de corretagem, identidade de lotes, confirmação de isenção,
memória de alienações ou vigência legal na data futura.

Os três casos fora do escopo são pessoa jurídica (dois casos) e BDR (um caso).
Eles devem continuar bloqueados enquanto o produto não declarar suporte.

## Critério de aproximação a uma revisão profissional

Para elevar um caso de `PENDENTE_EVIDENCIA`, o revisor deve:

1. confirmar a fonte primária e a vigência na data do fato gerador;
2. conferir o enquadramento material do produto e do contribuinte;
3. reconciliar o resultado com documento real anonimizado;
4. registrar divergências e ressalvas;
5. assinar o registro de revisão com sua credencial declarada;
6. arquivar a evidência original fora do Git.

Mesmo após isso, o resultado será uma revisão documentada do escopo testado,
não uma certificação universal do sistema nem aconselhamento para operação
individual.
