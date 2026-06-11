$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

Write-Host "Recommended trading desk URL:"
Write-Host "http://127.0.0.1:8765"
Write-Host ""
Write-Host "Start the local market data server with:"
Write-Host "powershell -ExecutionPolicy Bypass -File .\run_trading_desk_server.ps1"
Write-Host ""
Write-Host "The old static file still exists, but the server URL is more reliable for Binance/OKX/Coinbase public K-line data."
