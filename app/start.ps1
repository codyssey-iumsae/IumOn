param([int]$Port = 8765)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$taskEnv = Join-Path $PSScriptRoot '..\.config.env'
if (-not $env:APP_ENV_FILE -and -not (Test-Path '.env') -and (Test-Path $taskEnv)) {
    $env:APP_ENV_FILE = (Resolve-Path $taskEnv).Path
}
if (-not (Test-Path '.venv/Scripts/python.exe')) {
    python -m venv .venv
    & '.venv/Scripts/python.exe' -m pip install -r requirements.txt
}
$env:PORT = "$Port"
& '.venv/Scripts/python.exe' server.py
