# Live container read

When a service account is configured and added to GTM, an operator can list real accounts and audit a container.

## Sub-features

- `live-doctor` reaches Tag Manager API and reports account_count.
- `live-accounts` lists accountId/name/path.
- `live-audit` summarizes tags and unpublished changes for a configured container.

## How to get to it (user POV)

- Configure `.env` as in README.md.
- Run `gtm-mcp doctor` until `live_api.ok` is true.
- Run `gtm-mcp accounts` or `gtm-mcp audit --container GTM-XXXX`.

## Driving it with control-gtm-mcp

Preconditions:

- `doctor` JSON has `credentials_path_exists=true` and `live_api.ok=true`.
- If that precondition is missing, skip this feature and record the doctor `next_step`.

- **Doctor live.** Run `control-gtm-mcp.ps1 doctor`. `live_api.account_count` is an integer >= 0.
- **Accounts.** Run `.\.venv\Scripts\gtm-mcp.exe accounts`. Exit code `0`. JSON contains `accounts`.
- **Audit.** Only if `GTM_CONTAINER_ID` is set. Run `.\.venv\Scripts\gtm-mcp.exe audit`. JSON contains `counts.tags`.
- **Proof.** Save redacted JSON (no secrets; `client_email` is allowed) under `evidence/<run-id>/live-read.json`.

## Gotchas

- Zero accounts can still be a valid API success: the service account is authenticated but not added to any GTM account. Report that as setup, not as an API outage.
- Never create or publish during this feature.
- Do not paste service-account JSON into evidence.
