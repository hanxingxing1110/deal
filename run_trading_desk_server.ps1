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
    $python = "python"
}
elseif (Test-PythonCommand "py") {
    $python = "py"
}
elseif (Test-Path $bundledPython) {
    $python = $bundledPython
}
else {
    Write-Host "No usable Python runtime was found. Please install Python 3.10+ first."
    exit 1
}

Write-Host "Trading desk server started:"
Write-Host "http://127.0.0.1:8765"
Write-Host "Keep this PowerShell window open while using the trading desk. Press Ctrl+C to stop."

if ($python -eq "py") {
    & $python -3 -m crypto_agent.trading_desk_server
}
else {
    & $python -m crypto_agent.trading_desk_server
}
