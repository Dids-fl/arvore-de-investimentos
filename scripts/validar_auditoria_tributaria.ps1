param(
    [switch]$Online,
    [switch]$SuiteCompleta
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if (-not (Test-Path -LiteralPath ".\tributacao")) {
    throw "Execute este script na raiz do repositório."
}

$python = if (Test-Path -LiteralPath ".\.venv\Scripts\python.exe") {
    ".\.venv\Scripts\python.exe"
}
else {
    "python"
}

$ruff = if (Test-Path -LiteralPath ".\.venv\Scripts\ruff.exe") {
    ".\.venv\Scripts\ruff.exe"
}
else {
    "ruff"
}

$relatorios = ".\validacao\tributacao\relatorios"
New-Item -ItemType Directory -Path $relatorios -Force | Out-Null

Write-Host "1/6 - Compilação"
& $python -m compileall -q tributacao validacao tests
if ($LASTEXITCODE -ne 0) { throw "Falha na compilação." }

Write-Host "2/6 - Análise estática"
& $ruff check .
if ($LASTEXITCODE -ne 0) { throw "Falha no Ruff." }

Write-Host "3/6 - Testes tributários"
& $python -m pytest -q `
    .\tests\unit\test_tributacao.py `
    .\tests\unit\test_tributacao_casos_dourados.py `
    .\tests\unit\test_validadores_tributarios_independentes.py `
    .\tests\unit\test_governanca_tributaria.py `
    --tb=short
if ($LASTEXITCODE -ne 0) { throw "Falha nos testes tributários." }

if ($SuiteCompleta) {
    Write-Host "4/6 - Suíte determinística completa"
    & $python -m pytest -q tests -m "not slow" --tb=short
    if ($LASTEXITCODE -ne 0) { throw "Falha na suíte completa." }
}
else {
    Write-Host "4/6 - Suíte completa ignorada; use -SuiteCompleta para executá-la."
}

Write-Host "5/6 - Validação independente"
& $python -m validacao.tributacao.validar_tudo --saida $relatorios
if ($LASTEXITCODE -ne 0) { throw "O validador encontrou divergência." }

Write-Host "6/6 - Fontes e conciliação"
$argumentosFontes = @(
    "-m",
    "validacao.tributacao.auditar_fontes",
    "--saida",
    "$relatorios\auditoria_fontes.json"
)
if ($Online) {
    $argumentosFontes += "--online"
}
& $python @argumentosFontes
if ($LASTEXITCODE -ne 0) { throw "Falha na auditoria de fontes." }

& $python -m validacao.tributacao.reconciliar_documentos `
    .\modelos\casos_tributarios_reais_anonimizados.json `
    --saida "$relatorios\reconciliacao_exemplo.json"
if ($LASTEXITCODE -ne 0) { throw "Falha na conciliação de exemplo." }

Write-Host ""
Write-Host "Auditoria técnica concluída com sucesso."
Write-Host "Relatórios: $relatorios"
Write-Host "A revisão jurídica/contábil humana continua obrigatória para aprovação profissional."
