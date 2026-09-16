from __future__ import annotations

import asyncio
import inspect
import json
from datetime import timedelta
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .config import PROJECT_ROOT


BOOTSTRAP = PROJECT_ROOT / "scripts" / "bootstrap-mcp.ps1"


def list_local_tools() -> list[dict[str, Any]]:
    from .mcp_server import mcp

    manager = getattr(mcp, "_tool_manager")
    tools = []
    raw_tools = []
    if hasattr(manager, "list_tools"):
        listed = manager.list_tools()
        if inspect.isawaitable(listed):
            raw_tools = list(getattr(manager, "_tools").values())
        else:
            raw_tools = list(listed)
    elif hasattr(manager, "_tools"):
        raw_tools = list(manager._tools.values())
    for tool in raw_tools:
        annotations = getattr(tool, "annotations", None)
        annotation_dict = {}
        if annotations is not None:
            annotation_dict = {
                "readOnlyHint": bool(getattr(annotations, "readOnlyHint", False)),
                "destructiveHint": bool(getattr(annotations, "destructiveHint", False)),
            }
            if isinstance(annotations, dict):
                annotation_dict = {
                    "readOnlyHint": bool(annotations.get("readOnlyHint")),
                    "destructiveHint": bool(annotations.get("destructiveHint")),
                }
        tools.append(
            {
                "name": tool.name,
                "description": (tool.description or "").splitlines()[0],
                "read_only": annotation_dict.get("readOnlyHint", False),
                "destructive": annotation_dict.get("destructiveHint", False),
            }
        )
    return sorted(tools, key=lambda item: item["name"])


async def _call_tool(tool_name: str, arguments: dict[str, Any]) -> Any:
    params = StdioServerParameters(
        command="powershell.exe",
        args=[
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(BOOTSTRAP),
        ],
        cwd=str(PROJECT_ROOT),
    )
    async with stdio_client(params) as (read_stream, write_stream):
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
            return payload


def call_mcp_tool(tool_name: str, arguments: dict[str, Any] | None = None) -> Any:
    return asyncio.run(_call_tool(tool_name, arguments or {}))
