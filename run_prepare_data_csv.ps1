$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

$bundledPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$inputCsv = "data\sample_dual_15m_60d.csv"

function Test-PythonCommand {
    param([string]$Command)

    try {
        & $Command --version 2>$null | Out-Null
        return $LASTEXITCODE -eq 0
    }
    catch {
        return $false
    }
}

if (-not (Test-Path $inputCsv)) {
    Write-Host "CSV not found: $inputCsv"
    Write-Host "Run .\run_dual_timeframe.ps1 first, or replace `$inputCsv with your real 15m CSV path."
    exit 1
}

if (Test-PythonCommand "python") {
    & python -m crypto_agent.prepare_data_cli --source csv --input-csv $inputCsv --output-15m data\prepared_real_15m.csv --output-1h data\prepared_real_1h.csv --output runs\prepare_data_csv_result.json --report runs\prepare_data_csv_report.html
}
elseif (Test-PythonCommand "py") {
    & py -3 -m crypto_agent.prepare_data_cli --source csv --input-csv $inputCsv --output-15m data\prepared_real_15m.csv --output-1h data\prepared_real_1h.csv --output runs\prepare_data_csv_result.json --report runs\prepare_data_csv_report.html
}
elseif (Test-Path $bundledPython) {
    & $bundledPython -m crypto_agent.prepare_data_cli --source csv --input-csv $inputCsv --output-15m data\prepared_real_15m.csv --output-1h data\prepared_real_1h.csv --output runs\prepare_data_csv_result.json --report runs\prepare_data_csv_report.html
}
else {
    Write-Host "No usable Python runtime was found. Please install Python 3.10+ first."
    exit 1
}
