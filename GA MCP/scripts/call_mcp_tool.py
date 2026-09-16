"""Call one tool on this project's GA4 MCP server and print JSON."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import timedelta
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def call(tool_name: str, arguments: dict) -> None:
    project_root = Path(__file__).resolve().parents[1]
    params = StdioServerParameters(
        command="powershell.exe",
        args=[
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(project_root / "scripts" / "bootstrap-mcp.ps1"),
        ],
        cwd=project_root,
    )
    async with stdio_client(params, errlog=sys.stderr) as (read_stream, write_stream):
        async with ClientSession(
            read_stream,
            write_stream,
            read_timeout_seconds=timedelta(seconds=180),
        ) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            if result.isError:
                message = "\n".join(
                    block.text for block in result.content if hasattr(block, "text")
                )
                raise RuntimeError(message or f"MCP tool failed: {tool_name}")
            payload = result.structuredContent
            if payload is None:
                text_blocks = [
                    block.text for block in result.content if hasattr(block, "text")
                ]
                payload = json.loads(text_blocks[0]) if text_blocks else None
            print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> None:
    # Windows terminals often default to GBK, which cannot represent emoji or all
    # Unicode characters that may appear in GA4 resource names.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("tool_name")
    parser.add_argument("arguments_json", nargs="?", default="{}")
    args = parser.parse_args()
    asyncio.run(call(args.tool_name, json.loads(args.arguments_json)))


if __name__ == "__main__":
    main()
