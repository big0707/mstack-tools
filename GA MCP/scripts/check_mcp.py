"""Start the local MCP server and verify that its tool schemas are readable."""

from __future__ import annotations

import asyncio
import sys
from datetime import timedelta
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def check() -> None:
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
            response = await session.list_tools()
            expected = {
                "list_properties",
                "check_connection",
                "run_report",
                "run_realtime_report",
                "get_metadata",
            }
            actual = {tool.name for tool in response.tools}
            if actual != expected:
                raise RuntimeError(f"Unexpected MCP tools: {sorted(actual)}")
            for tool in response.tools:
                properties = sorted(tool.inputSchema.get("properties", {}))
                print(f"{tool.name}: {', '.join(properties) or '(no arguments)'}")


if __name__ == "__main__":
    asyncio.run(check())
