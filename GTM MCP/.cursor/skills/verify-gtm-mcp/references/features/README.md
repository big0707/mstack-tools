# GTM MCP verification map

This directory is the maintained source for verifying the user-facing behavior of GTM MCP. Read the index before driving, then use the matching feature file.

## Baseline preconditions

- Working directory is the GTM MCP project root.
- `.venv\Scripts\gtm-mcp.exe` exists after `scripts/setup.ps1`.
- Control CLI is `.cursor/skills/verify-gtm-mcp/control-gtm-mcp.ps1`.
- Run `control-gtm-mcp.ps1 doctor` first.
- Do not publish, create tags, or delete GTM resources during ordinary verification.
- Live Tag Manager reads require a configured service account. Local tool/MCP proofs do not.

## Driving conventions

- Start from the project root.
- Treat every command as literal.
- Prefer JSON assertions (`ok`, `dry_run`, `tool_names`, `next_step`).
- Restore nothing on the GTM side because the default path is read-only or dry-run.
- Keep evidence files after cleanup.

## Proof and skip reporting

- CLI proof includes command, stdout, and exit code.
- MCP proof includes `scripts/check_mcp.py` output showing the live tool list.
- Mutation proof is not required for the default map. If a later feature writes to GTM, it must preview with `confirm=false` first and use a disposable container.
- Record the feature ID with every artifact.
- If live credentials are missing, report `live-read` as skipped with doctor `next_step`.

## Features

- [Local CLI and doctor](./local-cli.md) covers help, doctor, tools, and snapshot.
- [Dry-run guards](./dry-run-guards.md) covers call/publish dry-run and confirmation defaults.
- [Stdio MCP handshake](./stdio-mcp.md) covers initialize + list_tools.
- [Live container read](./live-read.md) covers accounts/containers when credentials exist.
