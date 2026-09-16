# Stdio MCP handshake

Cursor and Codex start the server through `scripts/bootstrap-mcp.ps1`. A client can initialize and list the same tools the CLI advertises.

## Sub-features

- `mcp-initialize` completes the MCP handshake over stdio.
- `mcp-list-tools` returns the registered GTM tools.
- `mcp-schema` includes create/publish tools with a confirm field.

## How to get to it (user POV)

- Open the folder in Cursor and enable the `gtm` MCP.
- Or run `python scripts/check_mcp.py` from the project root.

## Driving it with control-gtm-mcp

Preconditions:

- `.venv` is installed.
- First launch may install dependencies; allow up to 180 seconds.

- **Handshake.** Run `control-gtm-mcp.ps1 mcp-check`. Exit code `0`. stdout contains `ok:` and `check_connection`.
- **Parity.** Compare tool names from `mcp-check` with `control-gtm-mcp.ps1 tools`. The sets must match.
- **Proof.** Save the mcp-check JSON/text under `evidence/<run-id>/mcp-check.txt`.

## Gotchas

- MCP uses stdout for protocol. Bootstrap diagnostics go to stderr. Do not treat stderr install lines as failure if exit code is 0.
- Opening the Cursor UI is not a substitute for `check_mcp.py`.
- This feature does not require GTM credentials. `whoami` is registered even when `.env` is missing; calling live tools will fail later.
