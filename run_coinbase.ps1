$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

$bundledPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"

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

if (Test-PythonCommand "python") {
    & python -m crypto_agent.cli --source coinbase --paper-trade --fallback-sample
}
elseif (Test-PythonCommand "py") {
    & py -3 -m crypto_agent.cli --source coinbase --paper-trade --fallback-sample
}
elseif (Test-Path $bundledPython) {
    & $bundledPython -m crypto_agent.cli --source coinbase --paper-trade --fallback-sample
}
else {
    Write-Host "No usable Python runtime was found. Please install Python 3.10+ first."
    exit 1
}
