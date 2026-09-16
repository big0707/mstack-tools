$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPath = Join-Path $projectRoot ".venv"
$venvPython = Join-Path $venvPath "Scripts\python.exe"
$markerPath = Join-Path $venvPath ".ga4-mcp-ready"
$projectFile = Join-Path $projectRoot "pyproject.toml"

# MCP reserves stdout for protocol messages. Send setup diagnostics to stderr.
function Write-Diagnostic([string]$Message) {
    [Console]::Error.WriteLine("[ga4-mcp] $Message")
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Diagnostic "First launch: creating the Python environment."
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -m venv $venvPath | Out-Null
    }
    elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m venv $venvPath | Out-Null
    }
    else {
        Write-Diagnostic "Python 3.10+ was not found. Install Python, then reopen the project."
        exit 1
    }
}

$needsInstall = -not (Test-Path -LiteralPath $markerPath)
if (-not $needsInstall) {
    $needsInstall = (Get-Item -LiteralPath $projectFile).LastWriteTimeUtc -gt `
        (Get-Item -LiteralPath $markerPath).LastWriteTimeUtc
}

if ($needsInstall) {
    Write-Diagnostic "Installing GA4 MCP dependencies. This only happens on first launch or after a dependency update."
    $env:PIP_DISABLE_PIP_VERSION_CHECK = "1"
    & $venvPython -m pip install --quiet -e $projectRoot | ForEach-Object {
        [Console]::Error.WriteLine($_)
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Diagnostic "Dependency installation failed. Check network access and Python, then retry."
        exit $LASTEXITCODE
    }
    New-Item -ItemType File -Path $markerPath -Force | Out-Null
}

Set-Location -LiteralPath $projectRoot
& $venvPython -m ga4_agent.mcp_server
exit $LASTEXITCODE
