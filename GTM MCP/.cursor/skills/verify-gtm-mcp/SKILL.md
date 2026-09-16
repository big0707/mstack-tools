---
name: verify-gtm-mcp
description: >
  Verify the Google Tag Manager MCP the way an agent or operator uses it:
  local CLI plus stdio MCP. Use after changing tools, startup, auth, or
  confirmation behavior. Primary surface is CLI/MCP, not a browser UI.
---

# Verify GTM MCP

This skill drives the real local product: `gtm-mcp` CLI and the stdio MCP server. It does not open tagmanager.google.com. Live GTM writes are out of scope unless the user explicitly provides a disposable container and asks for a write proof.

## Launch

There is no long-lived HTTP server. Launch means: install the package once, then run each drive as its own process.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

Ready when `.venv\Scripts\gtm-mcp.exe` exists and `.\.venv\Scripts\gtm-mcp.exe --help` exits 0.

Teardown: do not keep a server running. After the run:

```powershell
.\.venv\Scripts\gtm-mcp.exe cleanup
```

`cleanup` must not delete evidence.

## Doctor

Read-only health check. Always run first.

```powershell
.\.cursor\skills\verify-gtm-mcp\control-gtm-mcp.ps1 doctor
```

Equivalent:

```powershell
.\.venv\Scripts\gtm-mcp.exe doctor
```

Worth driving when JSON has `python_ok=true` and the process exits 0 **or** exits 1 only because live GTM credentials are missing. `next_step` must be present on failure. Never treat a missing service account as a product regression.

If `live_api.ok=true`, the instance can also drive the live-read feature. If not, skip live-read and still prove local tools/MCP.

## Drive

Use the control CLI. Do not invent extra wrappers.

```powershell
.\.cursor\skills\verify-gtm-mcp\control-gtm-mcp.ps1 <subcommand>
```

Harness commands:

- `doctor` — health JSON
- `tools` — registered MCP tools
- `help` — CLI help text
- `call-dry-run` — `gtm-mcp call whoami --dry-run`
- `publish-dry-run` — `gtm-mcp publish 0 --dry-run`
- `mcp-check` — stdio initialize + list_tools via `scripts/check_mcp.py`
- `pytest` — unit tests
- `snapshot --out <path>` — write doctor+tool inventory evidence
- `cleanup` — no leftover stdio processes

Feature recipes live in `references/features/`. Drive at least one mapped feature end to end.

## Evidence

Write proof under `.cursor/skills/verify-gtm-mcp/evidence/<run-id>/`. Keep this directory after cleanup.

Proof standards:

- Exercise the real CLI or real stdio MCP. Do not claim success from reading source.
- Capture the command, stdout, stderr, and exit code for every step.
- For MCP, capture the tool list from `scripts/check_mcp.py`, not a handwritten list.
- For dry-run publish/call, assert the JSON contains `"dry_run": true` and that no Tag Manager write occurred (no network write tools invoked).
- Mocks are allowed only in `tests/`. Verification of the product path must run the installed `gtm-mcp` or the bootstrap stdio server.
- If live credentials are absent, record `skipped-live-read` with the doctor `next_step`. Do not mark live-read as passed via another path.

## Cleanup

```powershell
.\.cursor\skills\verify-gtm-mcp\control-gtm-mcp.ps1 cleanup
```

Only reports leftover processes started by this run. Never delete `evidence/`.

## Helpers

- Product CLI: `.\.venv\Scripts\gtm-mcp.exe`
- Agent control CLI: `.cursor/skills/verify-gtm-mcp/control-gtm-mcp.ps1`
- MCP protocol check: `.\.venv\Scripts\python.exe scripts\check_mcp.py`

Both CLIs default to JSON except `--help`. Destructive product commands default to `--dry-run`.
