param(
    [string]$Python
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPath = Join-Path $projectRoot ".venv"
$venvPython = Join-Path $venvPath "Scripts\python.exe"

if (-not (Test-Path -LiteralPath $venvPython)) {
    if ($Python) {
        & $Python -m venv $venvPath
    }
    elseif (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -m venv $venvPath
    }
    elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m venv $venvPath
    }
    else {
        throw "Python 3.10+ was not found. Pass the full python.exe path with -Python."
    }
}

& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -e "$projectRoot[dev]"

Write-Host "Installation complete: $venvPython"
Write-Host "Next: copy .env.example to .env and set GOOGLE_APPLICATION_CREDENTIALS."
Write-Host "Then run: .\.venv\Scripts\gtm-mcp.exe doctor"
