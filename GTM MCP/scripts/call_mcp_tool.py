"""Call one tool on this project's GTM MCP server and print JSON."""

from __future__ import annotations

import argparse
import json
import sys

from gtm_agent.runtime import call_mcp_tool


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("tool_name")
    parser.add_argument("arguments_json", nargs="?", default="{}")
    args = parser.parse_args()
    payload = call_mcp_tool(args.tool_name, json.loads(args.arguments_json))
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
