# Dry-run guards

Write and publish paths default to preview. The CLI must not publish just because a version id was passed.

## Sub-features

- `call-dry-run` prints the tool and arguments without starting a live GTM write.
- `publish-dry-run` defaults to dry-run and refuses to publish without `--force`.
- `confirm-false` create/publish tools return `requires_confirmation` in unit tests.

## How to get to it (user POV)

- Run `gtm-mcp call whoami --dry-run`.
- Run `gtm-mcp publish 12` or `gtm-mcp publish 12 --dry-run`.
- Ask an agent to preview a tag without creating it.

## Driving it with control-gtm-mcp

Preconditions:

- Local CLI is installed.
- No disposable GTM container is required.

- **Call dry-run.** Run `control-gtm-mcp.ps1 call-dry-run`. Exit code `0`. JSON has `dry_run=true` and `tool=whoami`.
- **Publish dry-run.** Run `control-gtm-mcp.ps1 publish-dry-run`. Exit code `0`. JSON has `dry_run=true` and `action=publish_version`.
- **Unit confirmation.** Run `control-gtm-mcp.ps1 pytest`. Exit code `0`. `test_create_tag_preview_does_not_write` and `test_read_only_blocks_publish` pass.

## Gotchas

- `publish` without `--force` must stay dry-run even if someone passes `--no-dry-run` incorrectly in docs. The implemented CLI requires both `--no-dry-run` and `--force`.
- Dry-run must not invoke Tag Manager API.
- Do not turn this feature into a live publish to "make the proof stronger".
