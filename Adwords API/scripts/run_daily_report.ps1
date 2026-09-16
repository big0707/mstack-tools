param(
    [string]$Config = "config.yaml",
    [string]$CustomerId = "",
    [string]$ReportName = "daily_campaign",
    [string]$DateRange = "YESTERDAY",
    [string]$ChatId = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    throw "Virtual environment not found. Run: python -m venv .venv; .\.venv\Scripts\python -m pip install -e .[dev]"
}

$ArgsList = @(
    "-m", "adwords_agent.cli",
    "--config", (Join-Path $Root $Config),
    "report",
    "--name", $ReportName,
    "--date-range", $DateRange,
    "--send-feishu"
)

if ($CustomerId -ne "") {
    $ArgsList += @("--customer-id", $CustomerId)
}

if ($ChatId -ne "") {
    $ArgsList += @("--chat-id", $ChatId)
}

Push-Location $Root
try {
    & $Python @ArgsList
}
finally {
    Pop-Location
}
