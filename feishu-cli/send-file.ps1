param(
    [Parameter(Mandatory = $true)]
    [string]$ChatId,

    [Parameter(Mandatory = $true)]
    [string]$File,

    [switch]$AsDoc,

    [switch]$Public
)

$ErrorActionPreference = "Stop"
$ToolDir = Split-Path -Parent $MyInvocation.MyCommand.Path

if (-not (Test-Path -LiteralPath $File)) {
    throw "Report file not found: $File"
}

$CmdShim = Join-Path $ToolDir "feishu-cli.cmd"
$CliJs = Join-Path $ToolDir "src\cli.js"
if (Test-Path -LiteralPath $CmdShim) {
    $command = @($CmdShim, "send", "--chat-id", $ChatId, "--file", $File)
} elseif (Test-Path -LiteralPath $CliJs) {
    $command = @("node", $CliJs, "send", "--chat-id", $ChatId, "--file", $File)
} else {
    throw "No Feishu CLI found in $ToolDir. Expected feishu-cli.cmd or src\cli.js."
}

if ($AsDoc) {
    $command += "--as-doc"
}
if ($Public) {
    $command += "--public"
}

$Exe = $command[0]
$Args = @($command | Select-Object -Skip 1)
& $Exe @Args
exit $LASTEXITCODE
