param(
    [ValidateSet('start', 'refresh', 'analyze', 'test')]
    [string]$Action = 'start',
    [ValidateRange(1, 65535)][int]$Port = 8765,
    [ValidateRange(0, 1000000)][int]$Limit = 48
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
$pythonExe = Join-Path $repoRoot '.venv/Scripts/python.exe'

function Invoke-AppPython {
    & $pythonExe @args
    if ($LASTEXITCODE -ne 0) { throw "Python command failed ($LASTEXITCODE)." }
}

Push-Location $repoRoot
$previousDataDir = $env:IUMON_DATA_DIR
$previousEnvFile = $env:APP_ENV_FILE
$previousPort = $env:PORT
try {
    if (-not (Test-Path -LiteralPath $pythonExe)) {
        & python -m venv (Join-Path $repoRoot '.venv')
        if ($LASTEXITCODE -ne 0) { throw 'Virtual environment setup failed. Check Python installation and folder permissions.' }
    }
    & $pythonExe -c "import fastapi, uvicorn; from zoneinfo import ZoneInfo; ZoneInfo('Asia/Seoul')"
    if ($LASTEXITCODE -ne 0) {
        Invoke-AppPython -m pip install -r app/requirements.txt
    }
    if ($Action -eq 'test') {
        # Keep synthetic test data separate from real policy data.
        $testDataDir = Join-Path $repoRoot 'work/test-data'
        New-Item -ItemType Directory -Path $testDataDir -Force | Out-Null
        Copy-Item tests/fixtures/snapshot.json (Join-Path $testDataDir 'snapshot.json') -Force
        $env:IUMON_DATA_DIR = $testDataDir
        $env:APP_ENV_FILE = Join-Path $testDataDir 'unused.env'
        Invoke-AppPython scripts/check_repo.py
        Invoke-AppPython -m unittest discover -s tests -p test_repo_policy.py -v
        Invoke-AppPython -m unittest discover -s app -p test_app.py -v
        if (Get-Command node -ErrorAction SilentlyContinue) {
            foreach ($jsFile in @('app/static/app.js', 'app/static/journey.js')) {
                & node --check $jsFile
                if ($LASTEXITCODE -ne 0) { throw "JavaScript check failed: $jsFile" }
            }
        } else { Write-Host 'Node.js unavailable: JavaScript syntax is checked in CI.' }
    } else {
        $appEnv = Join-Path $repoRoot 'app/.env'
        $legacyEnv = Join-Path $repoRoot '.config.env'
        if (-not $env:APP_ENV_FILE -and -not (Test-Path -LiteralPath $appEnv) -and (Test-Path -LiteralPath $legacyEnv)) {
            $env:APP_ENV_FILE = $legacyEnv
        }
        switch ($Action) {
            'start' { $env:PORT = "$Port"; Invoke-AppPython app/server.py }
            'refresh' { Invoke-AppPython app/collect.py }
            'analyze' { Invoke-AppPython app/warm_analysis.py --limit $Limit }
        }
    }
} finally {
    $env:IUMON_DATA_DIR = $previousDataDir
    $env:APP_ENV_FILE = $previousEnvFile
    $env:PORT = $previousPort
    Pop-Location
}
