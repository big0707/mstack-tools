"""Start the local MCP server and verify that its tool schemas are readable."""

from __future__ import annotations

import asyncio
import sys
from datetime import timedelta
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from gtm_agent.runtime import list_local_tools


async def check() -> None:
    project_root = Path(__file__).resolve().parents[1]
    expected = {item["name"] for item in list_local_tools()}
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
            response = await session.list_tools()
            actual = {tool.name for tool in response.tools}
            if actual != expected:
                raise RuntimeError(
                    f"Unexpected MCP tools. missing={sorted(expected - actual)} "
                    f"extra={sorted(actual - expected)}"
                )
            print(f"ok: {len(actual)} tools")
            for tool in sorted(response.tools, key=lambda item: item.name):
                properties = sorted(tool.inputSchema.get("properties", {}))
                print(f"{tool.name}: {', '.join(properties) or '(no arguments)'}")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(check())
