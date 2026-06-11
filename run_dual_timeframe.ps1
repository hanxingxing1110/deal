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
    & python -m crypto_agent.dual_timeframe_cli --days 60
}
elseif (Test-PythonCommand "py") {
    & py -3 -m crypto_agent.dual_timeframe_cli --days 60
}
elseif (Test-Path $bundledPython) {
    & $bundledPython -m crypto_agent.dual_timeframe_cli --days 60
}
else {
    Write-Host "No usable Python runtime was found. Please install Python 3.10+ first."
    exit 1
}
