---
name: verify-gmp-access
description: >-
  Safely verify the local GMP access CLI's read-only discovery and immutable-plan
  controls: doctor, catalog, task planning, plan integrity, direct-execute
  refusal, and history. Use for GMP CLI acceptance checks without applying any
  Google permission change.
---

# Verify GMP access

This skill validates the real local gmp executable without making a remote
permission change. It never invokes gmp apply. Do not extend it with a live-write
test, disposable mailbox flow, browser fallback, or private Google endpoint.

Read [the feature map](references/features/README.md) before choosing an
individual recipe.

## Preconditions

Run from the project root. Install the editable CLI if needed:

    powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1

The harness is ready when .venv\Scripts\gmp.exe exists.

## Complete safe verification

Run:

    .\.cursor\skills\verify-gmp-access\control-gmp.ps1 verify

The harness checks only:

- doctor;
- the auxiliary gmp_org diagnosis, including manual role evidence and the public
  API's lack of organization personnel ACL endpoints;
- the Demo catalog;
- a Chinese task that creates an immutable plan for a reserved example.com
  address;
- loading that saved plan;
- temporary plan tampering is refused, followed by byte-for-byte restoration;
- a raw mutation --execute attempt is refused using deliberately invalid
  parameters that cannot reach a provider;
- history is readable;
- the audit file is unchanged;
- GSC remains method=manual, public_user_api=false, and is described as
  manual_required rather than successful.

The harness does not call apply, GA/GTM/Ads mutation APIs, a browser, or any
private web API.

## Individual harness commands

    .\.cursor\skills\verify-gmp-access\control-gmp.ps1 help
    .\.cursor\skills\verify-gmp-access\control-gmp.ps1 doctor
    .\.cursor\skills\verify-gmp-access\control-gmp.ps1 catalog
    .\.cursor\skills\verify-gmp-access\control-gmp.ps1 task
    .\.cursor\skills\verify-gmp-access\control-gmp.ps1 plan
    .\.cursor\skills\verify-gmp-access\control-gmp.ps1 plan -PlanId PLAN_ID
    .\.cursor\skills\verify-gmp-access\control-gmp.ps1 tamper
    .\.cursor\skills\verify-gmp-access\control-gmp.ps1 direct-execute-refusal
    .\.cursor\skills\verify-gmp-access\control-gmp.ps1 history

All mutation-shaped test input uses non-production identifiers. Plan creation is
a local persistence operation, not a Google write.

## Evidence

verify writes one result to:

    .cursor/skills/verify-gmp-access/evidence/<run-id>/verification.json

The result records commands, exit codes, output, plan_id, GSC manual assertions,
audit fingerprint stability, remote_write_attempted=false, and
apply_invoked=false.

The existing evidence/20260903-verify JSON files predate the immutable plan/apply
architecture. Preserve them byte-for-byte as historical snapshots only. They do
not prove the current contract and must not be rewritten, relabeled, or cited as
a current pass.

## Pass criteria

- Every expected-success command exits 0 and returns parseable JSON.
- doctor contains ga, gtm, gsc, ads, and the auxiliary gmp_org item without
  secret material.
- Ads provider and identity summary both use the dedicated YOUR_GMP_SA service
  account, not the ad-serving account or OAuth. Ads write readiness is labeled
  mcc_only and child_write_verified remains false in this read-only harness.
- catalog resolves demo.
- task returns dry_run=true and a non-empty plan_id.
- no preview result has status=ok.
- the GSC preview and saved action both use method=manual; the preview states
  manual_required and never claims success.
- gmp plan returns the same plan_id and action count.
- a modified plan is rejected, and its original bytes are restored.
- raw --execute exits nonzero and identifies the forbidden flag.
- gmp history is readable and the audit file fingerprint does not change.

If any assertion fails, report the failed invariant and stop. Never “confirm” the
plan to investigate a verifier failure.

## Safety notes

- Do not read .env, Service Account JSON, Google Ads YAML values, OAuth tokens,
  or private keys.
- doctor may perform official read-only API calls. A product write=false is an
  expected credential capability, not a verifier failure.
- The current gmp_org read may be false because the GMP Admin API is not enabled.
  That is not a verifier failure and does not change the v1alpha schema fact:
  there is no users/memberships/roles/permissions endpoint.
- Stop only processes started by the current run; this harness starts no server.
- Keep evidence. Do not delete plans, audit history, credentials, or historical
  snapshots.
