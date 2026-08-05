# Aplicação do pacote

Este ZIP deve ser extraído na raiz de `arvore-de-investimentos`, onde ficam
`engine.py`, `tributacao/` e `tests/`.

## 1. Extrair

```powershell
Expand-Archive `
  -LiteralPath .\validacao_tributaria_cinco_grupos.zip `
  -DestinationPath . `
  -Force
```

## 2. Validar sintaxe e qualidade

```powershell
python -m compileall -q tributacao validacao tests
ruff check .
```

## 3. Executar os cálculos independentes

```powershell
python -m validacao.tributacao.validar_tudo `
  --saida .\validacao\tributacao\relatorios

python .\validacao\tributacao\validar_cripto_independente.py `
  --fixtures .\tests\fixtures\tributacao\cripto.json `
  --saida .\validacao\tributacao\relatorio_cripto_independente.json
```

Resultado de referência dos cinco grupos:

```text
Total: 55
Validados: 17
Pendentes por premissa: 31
Fora do escopo: 7
Divergentes: 0
```

## 4. Executar testes tributários

```powershell
python -m pytest -q `
  .\tests\unit\test_tributacao.py `
  .\tests\unit\test_tributacao_casos_dourados.py `
  .\tests\unit\test_validadores_tributarios_independentes.py `
  --tb=short
```

Depois, valide o conjunto determinístico completo:

```powershell
python -m pytest -q tests -m "not slow" --tb=short
```

## 5. Revisar antes do commit

```powershell
git status --short
git diff --check
git diff --stat
```

Abra também:

- `validacao/tributacao/matriz_validacao_tributaria.xlsx`;
- `validacao/tributacao/RELATORIO_VALIDACAO_TECNICA.md`;
- `validacao/tributacao/relatorios/relatorio_tributario_consolidado.json`.

Somente faça o commit se não houver divergências, os testes passarem e as
alterações do motor tributário forem compatíveis com o restante do seu código.

## Observação essencial

`VALIDADO_PRIMEIRA_CAMADA` significa concordância do cálculo independente com
o caso dourado e o motor para as premissas declaradas. Não significa validação
tributária universal nem substitui revisão profissional de uma operação real.
