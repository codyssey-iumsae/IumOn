@echo off
cd /d "%~dp0app"
powershell -NoProfile -ExecutionPolicy Bypass -File ".\start.ps1"
pause
