#!/usr/bin/env python3
"""
Wrapper to call suganthan-gsc-mcp (stdio MCP server) tools from the command line.

Usage:
  python3 scripts/gsc_mcp.py list_tools
  python3 scripts/gsc_mcp.py <tool_name> '<json_args>'

Set GSC_KEY_FILE and either GSC_SITE_URL or GSC_SITE_URLS before running.
"""

import json
import subprocess
import sys
import os
import shutil

# 优先用全局安装的 suganthan-gsc-mcp（npm install -g suganthan-gsc-mcp），
# 找不到时回退到 npx（首次运行会自动下载，稍慢）
_found = shutil.which("suganthan-gsc-mcp")
if _found:
    MCP_CMD = [_found]
else:
    _npx = shutil.which("npx") or "npx"
    MCP_CMD = [_npx, "-y", "suganthan-gsc-mcp"]

def run_mcp_request(method: str, params: dict = None) -> dict:
    """Send a JSON-RPC request to the MCP server via stdio and get the response."""
    env = os.environ.copy()
    if not env.get("GSC_KEY_FILE", "").strip():
        raise ValueError("Set GSC_KEY_FILE to your own service account JSON path.")
    if not (env.get("GSC_SITE_URL", "").strip() or env.get("GSC_SITE_URLS", "").strip()):
        raise ValueError("Set GSC_SITE_URL or GSC_SITE_URLS to your actual GSC property ID(s).")
    if not os.path.isfile(env["GSC_KEY_FILE"]):
        raise ValueError("GSC_KEY_FILE does not point to an existing file.")

    # Build JSON-RPC messages
    messages = []
    
    # Initialize
    init_msg = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "gsc-mcp-cli", "version": "1.0.0"}
        }
    }
    messages.append(json.dumps(init_msg))
    
    # Initialized notification
    init_notif = {
        "jsonrpc": "2.0",
        "method": "notifications/initialized"
    }
    messages.append(json.dumps(init_notif))
    
    # The actual request
    request = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": method,
    }
    if params:
        request["params"] = params
    messages.append(json.dumps(request))
    
    stdin_data = "\n".join(messages) + "\n"
    
    proc = subprocess.run(
        MCP_CMD,
        input=stdin_data,
        capture_output=True,
        text=True,
        env=env,
        timeout=120
    )
    
    # Parse responses - look for our request's response (id=2)
    stderr_output = proc.stderr.strip()
    stdout_output = proc.stdout.strip()
    
    if stderr_output:
        # MCP servers log to stderr
        for line in stderr_output.split("\n"):
            if "error" in line.lower() or "Error" in line:
                print(f"[MCP stderr] {line}", file=sys.stderr)
    
    if not stdout_output:
        return {"error": "No output from MCP server", "stderr": stderr_output}
    
    # Parse all JSON-RPC responses
    responses = []
    for line in stdout_output.split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            resp = json.loads(line)
            responses.append(resp)
        except json.JSONDecodeError:
            continue
    
    # Find response with id=2 (our actual request)
    for resp in responses:
        if resp.get("id") == 2:
            return resp
    
    # If not found, return all responses
    return {"responses": responses, "stderr": stderr_output}


def list_tools():
    """List all available MCP tools."""
    result = run_mcp_request("tools/list")
    if "result" in result and "tools" in result["result"]:
        tools = result["result"]["tools"]
        print(f"\n📦 {len(tools)} GSC MCP Tools Available:\n")
        for t in tools:
            name = t.get("name", "?")
            desc = t.get("description", "")[:80]
            print(f"  • {name}")
            if desc:
                print(f"    {desc}")
        print()
        return tools
    else:
        print(json.dumps(result, indent=2))
        return None


def call_tool(tool_name: str, arguments: dict = None):
    """Call a specific MCP tool."""
    params = {
        "name": tool_name,
        "arguments": arguments or {}
    }
    result = run_mcp_request("tools/call", params)
    
    if "result" in result:
        content = result["result"].get("content", [])
        for item in content:
            if item.get("type") == "text":
                # Try to parse as JSON for pretty printing
                try:
                    data = json.loads(item["text"])
                    print(json.dumps(data, indent=2, ensure_ascii=False))
                except (json.JSONDecodeError, TypeError):
                    print(item["text"])
        return result["result"]
    elif "error" in result:
        print(f"Error: {json.dumps(result['error'], indent=2)}", file=sys.stderr)
        return None
    else:
        print(json.dumps(result, indent=2))
        return result


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 scripts/gsc_mcp.py list_tools")
        print("  python3 scripts/gsc_mcp.py <tool_name> [json_args]")
        print()
        print("Examples:")
        print('  python3 scripts/gsc_mcp.py site_snapshot \'{"siteUrl": "sc-domain:example.com"}\'')
        print('  python3 scripts/gsc_mcp.py quick_wins \'{"siteUrl": "sc-domain:example.com"}\'')
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "list_tools":
        list_tools()
    else:
        args = {}
        if len(sys.argv) > 2:
            try:
                args = json.loads(sys.argv[2])
            except json.JSONDecodeError:
                print(f"Error: Invalid JSON argument: {sys.argv[2]}", file=sys.stderr)
                sys.exit(1)
        call_tool(command, args)


if __name__ == "__main__":
    try:
        main()
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)
