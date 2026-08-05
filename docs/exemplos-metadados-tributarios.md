# Exemplos de metadados tributários avançados

Os campos abaixo são opcionais. Eles devem ser usados somente quando os dados
forem conhecidos; preencher valores estimados como se fossem históricos reduz
a qualidade do resultado.

## Lotes previdenciários existentes

```json
{
  "prev_pgbl": {
    "lotes_previdencia_existentes": [
      {
        "principal": 6000.0,
        "saldo_atual": 10000.0,
        "data_aplicacao": "2017-07-01"
      }
    ]
  }
}
```

`saldo_atual` é o valor econômico presente. `principal` é o custo/contribuição
original usado na base do VGBL. A soma dos saldos deve ser igual ao capital da
categoria. Lotes existentes impedem conversão automática entre PGBL e VGBL.

## Fundo com estado histórico de come-cotas

```json
{
  "fundos_rf": {
    "lotes_fundo_existentes": [
      {
        "principal": 8000.0,
        "saldo_atual": 10000.0,
        "base_tributaria_atual": 9800.0,
        "ganho_antecipado": 1800.0,
        "come_cotas_pago_historico": 270.0,
        "data_aplicacao": "2024-01-10"
      }
    ],
    "feriados_mercado": [
      "2027-05-31"
    ],
    "anos_calendario_mercado_confirmados": [
      2027
    ]
  }
}
```

`base_tributaria_atual` representa a base do saldo remanescente após os eventos
históricos informados. `ganho_antecipado` é o rendimento já alcançado pelo
come-cotas e necessário para calcular eventual complemento no resgate. O valor
histórico pago não é descontado novamente.

## Renda tributável anual do PGBL

Na chamada do engine, o questionário pode conter:

```json
{
  "renda_tributavel_anual": 100000.0,
  "renda_tributavel_por_ano": {
    "2026": 100000.0,
    "2027": 110000.0,
    "2028": 120000.0
  },
  "crescimento_renda_tributavel_anual": 0.03
}
```

Valores específicos por ano prevalecem sobre o crescimento. A tabela
tributária de 2026 aplicada além de 2026 continua sendo apenas um cenário e é
marcada como extrapolada.
