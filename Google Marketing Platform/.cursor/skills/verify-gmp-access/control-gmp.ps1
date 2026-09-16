param(
    [Parameter(Position = 0)]
    [ValidateSet("help", "doctor", "catalog", "task", "plan", "tamper", "direct-execute-refusal", "history", "verify")]
    [string]$Command = "help",
    [string]$PlanId,
    [string]$Out
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$skillRoot = $PSScriptRoot
$projectRoot = (Resolve-Path (Join-Path $skillRoot "..\..\..")).Path
$gmp = Join-Path $projectRoot ".venv\Scripts\gmp.exe"
$planRoot = Join-Path $projectRoot ".data\plans"
$auditPath = Join-Path $projectRoot ".data\audit.jsonl"
$testEmail = "verify-gmp-plan@example.com"

function Write-Json {
    param([object]$Value)
    $Value | ConvertTo-Json -Depth 24
}

function Assert-True {
    param(
        [bool]$Condition,
        [string]$Message
    )
    if (-not $Condition) {
        throw "ASSERTION FAILED: $Message"
    }
}

function Invoke-Gmp {
    param([string[]]$GmpArgs)

    $text = (& $gmp @GmpArgs 2>&1 | Out-String).Trim()
    $exitCode = $LASTEXITCODE
    return [pscustomobject]@{
        command   = "gmp " + ($GmpArgs -join " ")
        exit_code = $exitCode
        output    = $text
    }
}

function Convert-RunJson {
    param(
        [object]$Run,
        [string]$Label
    )
    try {
        return $Run.output | ConvertFrom-Json
    }
    catch {
        throw "$Label did not return JSON (exit $($Run.exit_code)): $($Run.output)"
    }
}

function Get-FileFingerprint {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        return "missing"
    }
    $item = Get-Item -LiteralPath $Path
    $hash = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
    return "$hash/$($item.Length)"
}

function New-TestPlan {
    param([string]$Email = $testEmail)

    $run = Invoke-Gmp @(
        "task",
        "把 $Email 加入 demo 的 ga gtm gsc ads，按入职只读权限"
    )
    Assert-True ($run.exit_code -eq 0) "task plan generation must exit 0"
    $json = Convert-RunJson $run "task"
    Assert-True ($json.ok -eq $true) "task result must be ok"
    Assert-True ($json.dry_run -eq $true) "task must remain dry_run"
    Assert-True (-not [string]::IsNullOrWhiteSpace([string]$json.plan_id)) "task must return plan_id"

    return [pscustomobject]@{
        run  = $run
        json = $json
    }
}

function Test-GscManualPlan {
    param([object]$TaskJson)

    $gscRows = @($TaskJson.results | Where-Object { $_.action.product -eq "gsc" })
    Assert-True ($gscRows.Count -gt 0) "task plan must include GSC"
    foreach ($row in $gscRows) {
        Assert-True ($row.action.method -eq "manual") "GSC action.method must be manual"
        Assert-True ($row.data.method -eq "manual") "GSC data.method must be manual"
        Assert-True ($row.data.public_user_api -eq $false) "GSC public_user_api must be false"
        Assert-True ($row.next_step -match "manual_required") "GSC preview must state manual_required"
        Assert-True ($row.status -ne "ok") "GSC preview must never claim success"
    }
}

function Test-PlanTamperRefusal {
    $created = New-TestPlan "verify-gmp-tamper@example.com"
    $id = [string]$created.json.plan_id
    $path = Join-Path $planRoot "$id.json"
    Assert-True (Test-Path -LiteralPath $path) "generated plan file must exist"

    $originalBytes = [System.IO.File]::ReadAllBytes($path)
    $beforeHash = Get-FileFingerprint $path
    $run = $null
    try {
        $payload = Get-Content -Raw -LiteralPath $path | ConvertFrom-Json
        $payload.reason = "tampered-by-read-only-verifier"
        $tamperedText = $payload | ConvertTo-Json -Depth 24
        [System.IO.File]::WriteAllText(
            $path,
            $tamperedText,
            [System.Text.UTF8Encoding]::new($false)
        )
        $run = Invoke-Gmp @("plan", $id)
        Assert-True ($run.exit_code -ne 0) "tampered plan must be refused"
        Assert-True ($run.output -match "校验失败|改过|tamper") "tamper refusal must explain integrity failure"
    }
    finally {
        [System.IO.File]::WriteAllBytes($path, $originalBytes)
    }

    $afterHash = Get-FileFingerprint $path
    Assert-True ($beforeHash -eq $afterHash) "tamper fixture must be restored byte-for-byte"
    return [pscustomobject]@{
        ok            = $true
        plan_id       = $id
        refusal       = $run
        restored_hash = $afterHash
    }
}

function Test-DirectExecuteRefusal {
    # Invalid email + nonexistent brand keep this safe even if the dedicated
    # --execute guard regresses: validation must fail before any provider call.
    $run = Invoke-Gmp @(
        "grant",
        "--email", "not-an-email",
        "--brands", "__verification_never_exists__",
        "--products", "ga",
        "--preset", "onboard",
        "--execute"
    )
    Assert-True ($run.exit_code -ne 0) "raw --execute must be refused"
    Assert-True ($run.output -match "--execute") "refusal must identify --execute"
    return [pscustomobject]@{
        ok      = $true
        refusal = $run
    }
}

if (-not (Test-Path -LiteralPath $gmp)) {
    Write-Json @{
        ok        = $false
        error     = "gmp.exe missing"
        next_step = "Run powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1"
        path      = $gmp
    }
    exit 1
}

switch ($Command) {
    "help" {
        Write-Json ([ordered]@{
            ok = $true
            safety = "This harness never invokes gmp apply and never performs a remote write."
            commands = @(
                "doctor",
                "catalog",
                "task",
                "plan [-PlanId ID]",
                "tamper",
                "direct-execute-refusal",
                "history",
                "verify [-Out PATH]"
            )
        })
        exit 0
    }
    "doctor" {
        $run = Invoke-Gmp @("doctor")
        Write-Output $run.output
        exit $run.exit_code
    }
    "catalog" {
        $run = Invoke-Gmp @("catalog", "--brand", "demo")
        Write-Output $run.output
        exit $run.exit_code
    }
    "task" {
        $created = New-TestPlan
        Write-Output $created.run.output
        exit 0
    }
    "plan" {
        if ([string]::IsNullOrWhiteSpace($PlanId)) {
            $created = New-TestPlan
            $PlanId = [string]$created.json.plan_id
        }
        $run = Invoke-Gmp @("plan", $PlanId)
        Write-Output $run.output
        exit $run.exit_code
    }
    "tamper" {
        Write-Json (Test-PlanTamperRefusal)
        exit 0
    }
    "direct-execute-refusal" {
        Write-Json (Test-DirectExecuteRefusal)
        exit 0
    }
    "history" {
        $run = Invoke-Gmp @("history", "--limit", "20")
        Write-Output $run.output
        exit $run.exit_code
    }
    "verify" {
        $startedAt = [DateTime]::UtcNow.ToString("o")
        $auditBefore = Get-FileFingerprint $auditPath
        $steps = [ordered]@{}
        try {
            $doctorRun = Invoke-Gmp @("doctor")
            Assert-True ($doctorRun.exit_code -eq 0) "doctor must exit 0"
            $doctorJson = Convert-RunJson $doctorRun "doctor"
            foreach ($product in @("ga", "gtm", "gsc", "ads")) {
                Assert-True ($null -ne $doctorJson.products.$product) "doctor must include $product"
            }
            Assert-True ($doctorRun.output -notmatch "private_key|client_secret|refresh_token") "doctor must not expose secrets"
            $ads = $doctorJson.products.ads
            $adsPersonnelEmail = "YOUR_GMP_SA@YOUR_GCP_PROJECT.iam.gserviceaccount.com"
            Assert-True ($ads.credential_mode -eq "service_account") "Ads personnel access must use its dedicated service account"
            Assert-True ($ads.credential_email -eq $adsPersonnelEmail) "Ads must not use the ad-serving or OAuth identity"
            Assert-True ($doctorJson.identity.ads_sa -eq $adsPersonnelEmail) "Ads identity summary must match the provider"
            Assert-True ($ads.write_check_scope -eq "mcc_only") "Ads write readiness is only an MCC role precheck"
            Assert-True ($ads.child_write_verified -eq $false) "read-only doctor must not claim child-account writes were verified"
            $steps.doctor = $doctorRun

            $catalogRun = Invoke-Gmp @("catalog", "--brand", "demo")
            Assert-True ($catalogRun.exit_code -eq 0) "catalog must exit 0"
            $catalogJson = Convert-RunJson $catalogRun "catalog"
            $demoProperty = $catalogJson.PSObject.Properties["demo"]
            Assert-True ($null -ne $demoProperty) "filtered catalog must include top-level demo"
            $steps.catalog = $catalogRun

            $created = New-TestPlan
            $taskJson = $created.json
            Assert-True (@($taskJson.results).Count -gt 0) "task must return preview rows"
            Assert-True (@($taskJson.results | Where-Object { $_.status -eq "ok" }).Count -eq 0) "preview must not contain ok writes"
            Test-GscManualPlan $taskJson
            $steps.task = $created.run

            $planIdValue = [string]$taskJson.plan_id
            $planRun = Invoke-Gmp @("plan", $planIdValue)
            Assert-True ($planRun.exit_code -eq 0) "saved plan must be readable"
            $planJson = Convert-RunJson $planRun "plan"
            Assert-True ($planJson.plan_id -eq $planIdValue) "loaded plan_id must match"
            Assert-True (@($planJson.actions).Count -eq @($taskJson.results).Count) "saved plan action count must match preview"
            $planGsc = @($planJson.actions | Where-Object { $_.product -eq "gsc" })
            Assert-True ($planGsc.Count -gt 0 -and $planGsc[0].method -eq "manual") "saved GSC action must remain manual"
            $steps.plan = $planRun

            $steps.tamper = Test-PlanTamperRefusal
            $steps.direct_execute_refusal = Test-DirectExecuteRefusal

            $historyRun = Invoke-Gmp @("history", "--limit", "20")
            Assert-True ($historyRun.exit_code -eq 0) "history must exit 0"
            $historyJson = Convert-RunJson $historyRun "history"
            Assert-True ($historyJson.ok -eq $true) "history must return ok"
            $steps.history = $historyRun

            $auditAfter = Get-FileFingerprint $auditPath
            Assert-True ($auditBefore -eq $auditAfter) "verification must not append apply audit records"

            $payload = [ordered]@{
                ok                     = $true
                started_at             = $startedAt
                finished_at            = [DateTime]::UtcNow.ToString("o")
                remote_write_attempted = $false
                apply_invoked          = $false
                plan_id                = $planIdValue
                audit_unchanged        = $true
                gsc_expected           = "manual_required on apply; preview method=manual"
                steps                  = $steps
            }
        }
        catch {
            $payload = [ordered]@{
                ok                     = $false
                started_at             = $startedAt
                finished_at            = [DateTime]::UtcNow.ToString("o")
                remote_write_attempted = $false
                apply_invoked          = $false
                error                  = $_.Exception.Message
                steps                  = $steps
            }
        }

        if ([string]::IsNullOrWhiteSpace($Out)) {
            $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
            $Out = Join-Path $skillRoot "evidence\$stamp\verification.json"
        }
        $directory = Split-Path -Parent $Out
        New-Item -ItemType Directory -Force -Path $directory | Out-Null
        [System.IO.File]::WriteAllText(
            $Out,
            ($payload | ConvertTo-Json -Depth 24),
            [System.Text.UTF8Encoding]::new($false)
        )
        Write-Json @{
            ok    = $payload.ok
            path  = $Out
            error = $(if ($payload.ok) { $null } else { $payload.error })
        }
        if ($payload.ok) { exit 0 }
        exit 1
    }
}
