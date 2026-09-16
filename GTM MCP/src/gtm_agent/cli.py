from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .config import PROJECT_ROOT, get_settings, read_service_account_identity


def _configure_stdio() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")


def _print_json(payload: Any, *, ok: bool = True) -> int:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if ok else 1


def _fail(message: str, *, next_step: str, extra: dict[str, Any] | None = None) -> int:
    payload = {"ok": False, "error": message, "next_step": next_step}
    if extra:
        payload.update(extra)
    return _print_json(payload, ok=False)


def cmd_doctor(_args: argparse.Namespace) -> int:
    settings = get_settings(require_credentials=False)
    identity = {}
    identity_error = None
    try:
        identity = read_service_account_identity(settings.credentials_path)
    except RuntimeError as exc:
        identity_error = str(exc)

    python_ok = sys.version_info >= (3, 10)
    credentials_ok = identity.get("credentials_path_exists") == "true"
    payload: dict[str, Any] = {
        "ok": python_ok and credentials_ok and identity_error is None,
        "app": "gtm-mcp",
        "version": __version__,
        "python": sys.version.split()[0],
        "python_ok": python_ok,
        "project_root": str(PROJECT_ROOT),
        "env_file_exists": (PROJECT_ROOT / ".env").is_file(),
        "credentials_configured": bool(settings.credentials_path),
        "credentials_path_exists": credentials_ok,
        "client_email": identity.get("client_email"),
        "project_id": identity.get("project_id"),
        "read_only_mode": settings.read_only,
        "default_account_id": settings.account_id or None,
        "default_container_id": settings.container_id or None,
        "container_aliases": settings.containers,
    }
    if identity_error:
        payload["identity_error"] = identity_error
    if not python_ok:
        payload["next_step"] = "安装 Python 3.10+，然后重新运行 scripts/setup.ps1。"
        return _print_json(payload, ok=False)
    if not settings.credentials_path:
        payload["next_step"] = "复制 .env.example 为 .env，设置 GOOGLE_APPLICATION_CREDENTIALS。"
        return _print_json(payload, ok=False)
    if not credentials_ok:
        payload["next_step"] = (
            "GOOGLE_APPLICATION_CREDENTIALS 指向的文件不存在。改成服务账号 JSON 的绝对路径。"
        )
        return _print_json(payload, ok=False)
    if identity_error:
        payload["next_step"] = "检查服务账号 JSON 是否是有效的 Google 密钥文件，且不要提交到 Git。"
        return _print_json(payload, ok=False)

    live = _try_live_accounts()
    payload["live_api"] = live
    if live.get("ok"):
        payload["ok"] = True
        payload["next_step"] = "可以运行 gtm-mcp accounts 或在 Cursor 中调用 check_connection。"
        return _print_json(payload, ok=True)
    payload["ok"] = False
    payload["next_step"] = live.get(
        "next_step",
        "启用 Tag Manager API，并把 client_email 加入 GTM User Management。",
    )
    return _print_json(payload, ok=False)


def _try_live_accounts() -> dict[str, Any]:
    try:
        from .client import GtmClient

        client = GtmClient()
        accounts = client.list_accounts()
        return {
            "ok": True,
            "account_count": len(accounts),
            "accounts": [
                {
                    "accountId": item.get("accountId"),
                    "name": item.get("name"),
                    "path": item.get("path"),
                }
                for item in accounts
            ],
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "next_step": str(exc)}


def cmd_tools(_args: argparse.Namespace) -> int:
    from .runtime import list_local_tools

    tools = list_local_tools()
    return _print_json({"ok": True, "count": len(tools), "tools": tools})


def cmd_call(args: argparse.Namespace) -> int:
    arguments = json.loads(args.arguments_json)
    if args.dry_run:
        return _print_json(
            {
                "ok": True,
                "dry_run": True,
                "tool": args.tool_name,
                "arguments": arguments,
                "would_call": "MCP stdio tool via scripts/bootstrap-mcp.ps1",
            }
        )
    from .runtime import call_mcp_tool

    payload = call_mcp_tool(args.tool_name, arguments)
    return _print_json({"ok": True, "tool": args.tool_name, "result": payload})


def cmd_accounts(args: argparse.Namespace) -> int:
    if args.dry_run:
        return _print_json(
            {
                "ok": True,
                "dry_run": True,
                "would_call": "list_accounts",
            }
        )
    try:
        from .client import GtmClient

        accounts = GtmClient().list_accounts()
        return _print_json({"ok": True, "count": len(accounts), "accounts": accounts})
    except Exception as exc:  # noqa: BLE001
        return _fail(str(exc), next_step="先运行 gtm-mcp doctor，按返回的 next_step 配好凭据。")


def cmd_containers(args: argparse.Namespace) -> int:
    if args.dry_run:
        return _print_json(
            {
                "ok": True,
                "dry_run": True,
                "would_call": "list_containers",
                "account": args.account,
            }
        )
    try:
        from .client import GtmClient

        client = GtmClient()
        settings = get_settings(require_credentials=True)
        account = args.account or settings.account_id
        if account:
            containers = client.list_containers(account)
            return _print_json(
                {"ok": True, "account": account, "count": len(containers), "containers": containers}
            )
        grouped = []
        total = 0
        for item in client.list_accounts():
            containers = client.list_containers(item["path"])
            total += len(containers)
            grouped.append(
                {
                    "accountId": item.get("accountId"),
                    "name": item.get("name"),
                    "containers": containers,
                }
            )
        return _print_json({"ok": True, "count": total, "accounts": grouped})
    except Exception as exc:  # noqa: BLE001
        return _fail(str(exc), next_step="先运行 gtm-mcp doctor，再指定 --account。")


def cmd_audit(args: argparse.Namespace) -> int:
    if args.dry_run:
        return _print_json(
            {
                "ok": True,
                "dry_run": True,
                "would_call": "audit_container",
                "container": args.container,
            }
        )
    try:
        from .mcp_server import audit_container

        result = audit_container(container=args.container, account=args.account)
        result["ok"] = True
        return _print_json(result)
    except Exception as exc:  # noqa: BLE001
        return _fail(str(exc), next_step="用 gtm-mcp containers 确认容器 ID，再重试。")


def cmd_snapshot(args: argparse.Namespace) -> int:
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    from .runtime import list_local_tools

    tools = list_local_tools()
    payload = {
        "ok": True,
        "app": "gtm-mcp",
        "version": __version__,
        "tool_count": len(tools),
        "tool_names": [tool["name"] for tool in tools],
        "doctor": _doctor_payload(),
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return _print_json({"ok": True, "written": str(out), "tool_count": len(tools)})


def _doctor_payload() -> dict[str, Any]:
    settings = get_settings(require_credentials=False)
    identity: dict[str, str] = {}
    try:
        identity = read_service_account_identity(settings.credentials_path)
    except RuntimeError as exc:
        identity = {"error": str(exc)}
    return {
        "env_file_exists": (PROJECT_ROOT / ".env").is_file(),
        "credentials_configured": bool(settings.credentials_path),
        "credentials_path_exists": identity.get("credentials_path_exists") == "true",
        "client_email": identity.get("client_email"),
        "read_only_mode": settings.read_only,
    }


def cmd_cleanup(_args: argparse.Namespace) -> int:
    return _print_json(
        {
            "ok": True,
            "cleaned": [],
            "note": "GTM MCP 是短生命周期 stdio 进程，验证运行不会留下常驻服务。",
        }
    )


def cmd_publish(args: argparse.Namespace) -> int:
    preview = {
        "ok": True,
        "dry_run": True,
        "action": "publish_version",
        "version_id": args.version_id,
        "container": args.container,
        "account": args.account,
        "warning": "发布会改变线上流量。CLI 默认 --dry-run。去掉 --dry-run 才会真正发布。",
    }
    if args.dry_run or not args.force:
        if not args.dry_run and not args.force:
            preview["next_step"] = "确认版本无误后，使用 --force 并且不要带 --dry-run。"
        return _print_json(preview)
    try:
        from .mcp_server import publish_version

        result = publish_version(
            version_id=args.version_id,
            container=args.container,
            account=args.account,
            confirm=True,
        )
        result["ok"] = True
        return _print_json(result)
    except Exception as exc:  # noqa: BLE001
        return _fail(str(exc), next_step="先用 gtm-mcp call get_version 核对 version_id。")


def cmd_serve(_args: argparse.Namespace) -> int:
    from .mcp_server import main as serve_main

    serve_main()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gtm-mcp",
        description="Google Tag Manager MCP 的 Agent 友好控制 CLI。默认输出 JSON。",
    )
    parser.add_argument("--version", action="version", version=f"gtm-mcp {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="只读健康检查：Python、.env、服务账号、可选 live API")
    doctor.set_defaults(func=cmd_doctor)

    tools = sub.add_parser("tools", help="列出 MCP 工具，不访问 GTM API")
    tools.set_defaults(func=cmd_tools)

    call = sub.add_parser("call", help="通过 MCP stdio 调用一个工具")
    call.add_argument("tool_name")
    call.add_argument("arguments_json", nargs="?", default="{}")
    call.add_argument("--dry-run", action="store_true", help="只打印将要调用的工具，不执行")
    call.set_defaults(func=cmd_call)

    accounts = sub.add_parser("accounts", help="列出服务账号可见的 GTM 账户")
    accounts.add_argument("--dry-run", action="store_true")
    accounts.set_defaults(func=cmd_accounts)

    containers = sub.add_parser("containers", help="列出容器")
    containers.add_argument("--account", help="数字 accountId 或 accounts/{id}")
    containers.add_argument("--dry-run", action="store_true")
    containers.set_defaults(func=cmd_containers)

    audit = sub.add_parser("audit", help="审计一个容器的标签/触发器/未发布变更")
    audit.add_argument("--container", help="GTM-XXXX、别名或数字 ID")
    audit.add_argument("--account")
    audit.add_argument("--dry-run", action="store_true")
    audit.set_defaults(func=cmd_audit)

    snapshot = sub.add_parser("snapshot", help="把 doctor + 工具清单写成证据文件")
    snapshot.add_argument(
        "--out",
        default=str(PROJECT_ROOT / ".cursor" / "skills" / "verify-gtm-mcp" / "evidence" / "snapshot.json"),
        help="输出 JSON 路径",
    )
    snapshot.set_defaults(func=cmd_snapshot)

    cleanup = sub.add_parser("cleanup", help="清理本轮验证留下的进程；stdio 服务通常无需清理")
    cleanup.set_defaults(func=cmd_cleanup)

    publish = sub.add_parser("publish", help="发布容器版本；默认 --dry-run")
    publish.add_argument("version_id")
    publish.add_argument("--container")
    publish.add_argument("--account")
    publish.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="默认开启。使用 --no-dry-run --force 才会真正发布",
    )
    publish.add_argument("--force", action="store_true", help="确认后真正发布")
    publish.set_defaults(func=cmd_publish)

    serve = sub.add_parser("serve", help="以 stdio 启动 MCP server")
    serve.set_defaults(func=cmd_serve)
    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except BrokenPipeError:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
