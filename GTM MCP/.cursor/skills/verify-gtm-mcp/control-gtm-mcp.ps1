param(
    [Parameter(Position = 0)]
    [string]$Command = "help",
    [string]$Out,
    [string]$Tool = "whoami",
    [string]$ArgumentsJson = "{}"
)

$ErrorActionPreference = "Stop"
$skillRoot = $PSScriptRoot
$projectRoot = (Resolve-Path (Join-Path $skillRoot "..\..\..")).Path
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$gtmMcp = Join-Path $projectRoot ".venv\Scripts\gtm-mcp.exe"

function Write-JsonResult {
    param(
        [bool]$Ok,
        [int]$Code,
        [string]$Ran,
        [string]$StdoutText,
        [string]$ErrorText,
        [string]$NextStep
    )
    $payload = [ordered]@{
        ok        = $Ok
        exit_code = $Code
        command   = $Ran
        stdout    = $StdoutText
    }
    if ($ErrorText) { $payload.error = $ErrorText }
    if ($NextStep) { $payload.next_step = $NextStep }
    $payload | ConvertTo-Json -Depth 6
}

if (-not (Test-Path -LiteralPath $gtmMcp)) {
    Write-JsonResult -Ok:$false -Code 1 -Ran $gtmMcp -StdoutText "" -ErrorText "gtm-mcp.exe is missing" -NextStep "Run scripts/setup.ps1 from the project root"
    exit 1
}

switch ($Command) {
    "help" {
        & $gtmMcp --help
        exit $LASTEXITCODE
    }
    "doctor" {
        & $gtmMcp doctor
        exit $LASTEXITCODE
    }
    "tools" {
        & $gtmMcp tools
        exit $LASTEXITCODE
    }
    "call-dry-run" {
        & $gtmMcp call $Tool $ArgumentsJson --dry-run
        exit $LASTEXITCODE
    }
    "publish-dry-run" {
        & $gtmMcp publish 0 --dry-run
        exit $LASTEXITCODE
    }
    "snapshot" {
        if (-not $Out) {
            $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
            $Out = Join-Path $skillRoot "evidence\$stamp\snapshot.json"
        }
        & $gtmMcp snapshot --out $Out
        exit $LASTEXITCODE
    }
    "pytest" {
        $ran = "$venvPython -m pytest -q"
        $output = & $venvPython -m pytest -q 2>&1 | Out-String
        $code = $LASTEXITCODE
        Write-JsonResult -Ok:($code -eq 0) -Code $code -Ran $ran -StdoutText $output -ErrorText $(if ($code -ne 0) { "pytest failed" } else { "" }) -NextStep $(if ($code -ne 0) { "Fix failing tests, then rerun control-gtm-mcp.ps1 pytest" } else { "" })
        exit $code
    }
    "mcp-check" {
        $script = Join-Path $projectRoot "scripts\check_mcp.py"
        $ran = "$venvPython $script"
        $output = & $venvPython $script 2>&1 | Out-String
        $code = $LASTEXITCODE
        Write-JsonResult -Ok:($code -eq 0) -Code $code -Ran $ran -StdoutText $output -ErrorText $(if ($code -ne 0) { "MCP handshake failed" } else { "" }) -NextStep $(if ($code -ne 0) { "Read scripts/bootstrap-mcp.ps1 stderr and rerun after setup.ps1" } else { "" })
        exit $code
    }
    "cleanup" {
        & $gtmMcp cleanup
        exit $LASTEXITCODE
    }
    default {
        Write-JsonResult -Ok:$false -Code 2 -Ran $Command -StdoutText "" -ErrorText "unknown subcommand: $Command" -NextStep "Use help|doctor|tools|call-dry-run|publish-dry-run|snapshot|pytest|mcp-check|cleanup"
        exit 2
    }
}
