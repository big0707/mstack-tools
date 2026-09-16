# GMP access verification map

This directory maps the safe acceptance surface of the GMP access CLI. Verification
stops before apply and never performs a real permission write.

## Invariants shared by every feature

- Start at the project root and use control-gmp.ps1.
- Do not invoke gmp apply.
- Do not use Browser, Chrome, Playwright, DOM extraction, cookies, or private web
  APIs.
- Do not read .env or credential contents.
- Use only verify-gmp-plan@example.com or another reserved example.com address.
- Plan files created by tests are local artifacts. Do not manually confirm them.
- Capture command, output, and exit code. A write=false doctor result is allowed.
- Treat the user's 2026-09-02 screenshot as manual evidence that YOUR_GMP_SA has
  direct Org Admin, User Admin, and Billing Admin in Your Organization. Verification
  must not relabel it as a public-API role lookup.
- GMP Admin API enablement and GMP organization personnel ACL support are
  separate questions. The current API-disabled result is allowed; v1alpha has
  no organization users/memberships/roles/permissions endpoint either way.

## Features

- [Doctor](doctor.md): official read-only connectivity and capability reporting.
- [Catalog](catalog.md): brand and resource resolution.
- [Natural-language task](task.md): Chinese request parsing and plan creation.
- [Saved plan](plan.md): immutable plan persistence and GSC manual semantics.
- [Tamper refusal](tamper.md): integrity validation with byte-for-byte restore.
- [Direct execute refusal](direct-execute-refusal.md): prove raw --execute cannot
  bypass planning.
- [History](history.md): read the audit surface without appending to it.

Run all mapped features:

    .\.cursor\skills\verify-gmp-access\control-gmp.ps1 verify

## Evidence policy

New runs write verification.json under evidence/<run-id>/.

The evidence/20260903-verify directory is a historical snapshot from the former
dry-run/browser design. Preserve those JSON files unchanged. Their fields such as
grant-dry-run, users_url, or old status values are evidence of the past, not the
current acceptance contract.
