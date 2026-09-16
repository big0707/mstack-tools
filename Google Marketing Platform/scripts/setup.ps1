param(
    [string]$Python
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPath = Join-Path $projectRoot ".venv"
$venvPython = Join-Path $venvPath "Scripts\python.exe"
$parent = Split-Path -Parent $projectRoot

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

$envPath = Join-Path $projectRoot ".env"
if (-not (Test-Path -LiteralPath $envPath)) {
    $ga = Join-Path $parent "GA MCP\credentials\ga-service-account.json"
    $gsc = Join-Path $parent "SEO-Agent\credentials\gsc-key.json"
    $ads = Join-Path $parent "Adwords API\google-ads.yaml"
    $lines = @(
        "GMP_OAUTH_CLIENT_FILE=credentials/oauth-client.json",
        "GMP_OAUTH_TOKEN_FILE=credentials/token.json",
        "GMP_ADS_LOGIN_CUSTOMER_ID=1234567890",
        "GMP_ADS_API_VERSION=v24"
    )
    if (Test-Path -LiteralPath $ga) { $lines += "GMP_GA_CREDENTIALS=$ga" }
    if (Test-Path -LiteralPath $gsc) { $lines += "GMP_GSC_CREDENTIALS=$gsc" }
    if (Test-Path -LiteralPath $ads) { $lines += "GMP_ADS_YAML=$ads" }
    $utf8 = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllLines($envPath, $lines, $utf8)
    Write-Host "Wrote .env with sibling credential paths."
}

New-Item -ItemType Directory -Force -Path (Join-Path $projectRoot "credentials") | Out-Null
Write-Host "Installation complete: $venvPython"
Write-Host "Next: .\.venv\Scripts\gmp.exe doctor"
