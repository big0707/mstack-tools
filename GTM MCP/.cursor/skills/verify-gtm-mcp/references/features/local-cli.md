# Local CLI and doctor

An operator or agent can install the package and get JSON health, a tool inventory, and a snapshot file without calling Tag Manager.

## Sub-features

- `cli-help` prints subcommands including doctor, tools, call, publish, snapshot, cleanup.
- `cli-doctor` returns JSON with python, env, and credential status.
- `cli-tools` lists registered MCP tools without network access.
- `cli-snapshot` writes doctor + tool names to an evidence file.

## How to get to it (user POV)

- Run `gtm-mcp --help` after setup.
- Run `gtm-mcp doctor` to see why MCP cannot start.
- Run `gtm-mcp tools` to see available agent tools.
- Run `gtm-mcp snapshot --out <file>` to save a proof file.

## Driving it with control-gtm-mcp

Preconditions:

- `scripts/setup.ps1` has been run.
- Working directory is the project root.

- **Help.** Run `control-gtm-mcp.ps1 help`. Exit code `0`. stdout contains `doctor`, `tools`, `publish`.
- **Doctor.** Run `control-gtm-mcp.ps1 doctor`. JSON includes `python_ok` and either `ok=true` or a `next_step`.
- **Tools.** Run `control-gtm-mcp.ps1 tools`. JSON `count` >= 30 and `tools` includes `check_connection`, `create_tag`, `publish_version`.
- **Snapshot.** Run `control-gtm-mcp.ps1 snapshot --Out .cursor/skills/verify-gtm-mcp/evidence/<run-id>/snapshot.json`. File exists and contains `tool_names`.

## Gotchas

- Doctor may exit 1 when the service account is missing. That is a setup gap, not a CLI crash. Capture `next_step`.
- `gtm-mcp.exe` will not exist until setup creates `.venv`.
- Snapshot must be written under `evidence/` so cleanup will not remove it.
