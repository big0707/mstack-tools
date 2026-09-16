param(
    [string]$TaskName = "Google Ads Daily Feishu Report",
    [string]$At = "09:00",
    [string]$Config = "config.yaml",
    [string]$CustomerId = "",
    [string]$ReportName = "daily_campaign",
    [string]$ChatId = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Runner = Join-Path $PSScriptRoot "run_daily_report.ps1"

$ScriptArgs = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", "`"$Runner`"",
    "-Config", "`"$Config`"",
    "-ReportName", "`"$ReportName`""
)

if ($CustomerId -ne "") {
    $ScriptArgs += @("-CustomerId", "`"$CustomerId`"")
}

if ($ChatId -ne "") {
    $ScriptArgs += @("-ChatId", "`"$ChatId`"")
}

$Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument ($ScriptArgs -join " ") -WorkingDirectory $Root
$Trigger = New-ScheduledTaskTrigger -Daily -At $At
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description "Run Google Ads report and send it to Feishu." -Force
Write-Host "Registered scheduled task '$TaskName' at $At."
