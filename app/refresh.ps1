$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Test-Path '.venv/Scripts/python.exe')) {
    throw '먼저 start.ps1로 실행 환경을 설치해 주세요.'
}
& '.venv/Scripts/python.exe' collect.py
