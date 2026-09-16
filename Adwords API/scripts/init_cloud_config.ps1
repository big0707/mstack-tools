param()

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Required = @(
    "GOOGLE_ADS_DEVELOPER_TOKEN",
    "GOOGLE_ADS_SERVICE_ACCOUNT_JSON",
    "GOOGLE_ADS_LOGIN_CUSTOMER_ID",
    "GOOGLE_ADS_DEFAULT_CUSTOMER_ID"
)

$Missing = @()
foreach ($Name in $Required) {
    if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($Name))) {
        $Missing += $Name
    }
}

if ($Missing.Count -gt 0) {
    Write-Host "Skipped config generation. Missing env vars:"
    $Missing | ForEach-Object { Write-Host "  $_" }
    exit 0
}

$ServiceAccountPath = Join-Path $Root "google-ads-service-account.json"
[Environment]::GetEnvironmentVariable("GOOGLE_ADS_SERVICE_ACCOUNT_JSON") |
    Set-Content -LiteralPath $ServiceAccountPath -Encoding UTF8 -NoNewline

$ApiVersion = [Environment]::GetEnvironmentVariable("GOOGLE_ADS_API_VERSION")
if ([string]::IsNullOrWhiteSpace($ApiVersion)) {
    $ApiVersion = "v24"
}

$FeishuChatId = [Environment]::GetEnvironmentVariable("FEISHU_CHAT_ID")

@"
developer_token: "$([Environment]::GetEnvironmentVariable("GOOGLE_ADS_DEVELOPER_TOKEN"))"
json_key_file_path: "google-ads-service-account.json"
login_customer_id: "$([Environment]::GetEnvironmentVariable("GOOGLE_ADS_LOGIN_CUSTOMER_ID"))"
use_proto_plus: true
"@ | Set-Content -LiteralPath (Join-Path $Root "google-ads.yaml") -Encoding UTF8

@"
google_ads:
  yaml_path: google-ads.yaml
  api_version: $ApiVersion
  default_customer_id: "$([Environment]::GetEnvironmentVariable("GOOGLE_ADS_DEFAULT_CUSTOMER_ID"))"

reports:
  dir: reports

feishu:
  cli_path: tools/feishu-cli/send-file.ps1
  default_chat_id: "$FeishuChatId"
  send_command:
    - "powershell.exe"
    - "-NoProfile"
    - "-ExecutionPolicy"
    - "Bypass"
    - "-File"
    - "{cli_path}"
    - "-ChatId"
    - "{chat_id}"
    - "-File"
    - "{file}"
"@ | Set-Content -LiteralPath (Join-Path $Root "config.yaml") -Encoding UTF8

New-Item -ItemType Directory -Force -Path (Join-Path $Root "reports") | Out-Null
Write-Host "Generated google-ads.yaml and config.yaml."
