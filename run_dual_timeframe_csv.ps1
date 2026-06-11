$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

$bundledPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$csv15m = "data\sample_dual_15m_60d.csv"

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

if (-not (Test-Path $csv15m)) {
    Write-Host "CSV not found: $csv15m"
    Write-Host "Run .\run_dual_timeframe.ps1 first, or replace `$csv15m with your real 15m CSV path."
    exit 1
}

if (Test-PythonCommand "python") {
    & python -m crypto_agent.dual_timeframe_cli --source csv --csv-15m $csv15m --output runs/dual_timeframe_csv_result.json --report runs/dual_timeframe_csv_report.html
}
elseif (Test-PythonCommand "py") {
    & py -3 -m crypto_agent.dual_timeframe_cli --source csv --csv-15m $csv15m --output runs/dual_timeframe_csv_result.json --report runs/dual_timeframe_csv_report.html
}
elseif (Test-Path $bundledPython) {
    & $bundledPython -m crypto_agent.dual_timeframe_cli --source csv --csv-15m $csv15m --output runs/dual_timeframe_csv_result.json --report runs/dual_timeframe_csv_report.html
}
else {
    Write-Host "No usable Python runtime was found. Please install Python 3.10+ first."
    exit 1
}
