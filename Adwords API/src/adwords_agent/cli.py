from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

from .ads import AdsManager
from .config import load_config
from .feishu import build_feishu_command, send_file
from .google_ads import GoogleAdsGateway, GoogleAdsRuntimeError, format_google_ads_exception
from .models import (
    CreateResponsiveSearchAdRequest,
    PauseAdRequest,
    ReportDefinition,
    TextAssetSpec,
    UpdateResponsiveSearchAdRequest,
)
from .reports import REPORT_QUERIES, ReportRunner, build_query
from .task_parser import parse_natural_task

console = Console()


def _load_json_or_file(value: str) -> dict[str, Any]:
    path = Path(value)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return json.loads(value)


def _assets(items: list[dict[str, Any] | str]) -> list[TextAssetSpec]:
    assets: list[TextAssetSpec] = []
    for item in items:
        if isinstance(item, str):
            assets.append(TextAssetSpec(text=item))
        else:
            assets.append(
                TextAssetSpec(
                    text=str(item["text"]),
                    pinned_field=item.get("pinned_field"),
                )
            )
    return assets


def _gateway(config_path: str | None) -> GoogleAdsGateway:
    config = load_config(config_path)
    return GoogleAdsGateway(
        yaml_path=config.google_ads_yaml_path,
        api_version=config.google_ads_api_version,
    )


def _print_json(value: Any) -> None:
    console.print_json(json.dumps(value, ensure_ascii=False, default=str))


def cmd_task(args: argparse.Namespace) -> int:
    parsed = parse_natural_task(args.text)
    _print_json(asdict(parsed))
    if parsed.missing_fields:
        return 2
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    payload = _load_json_or_file(args.input)
    action = payload.get("task_type")
    _print_json(payload)
    if action not in {
        "create_responsive_search_ad",
        "update_responsive_search_ad",
        "pause_ad",
        "report",
    }:
        console.print("[red]Unknown task_type.[/red]")
        return 2
    return 0


def cmd_create_rsa(args: argparse.Namespace) -> int:
    payload = _load_json_or_file(args.input)
    request = CreateResponsiveSearchAdRequest(
        customer_id=str(payload["customer_id"]),
        ad_group_id=str(payload["ad_group_id"]),
        final_urls=list(payload["final_urls"]),
        headlines=_assets(payload["headlines"]),
        descriptions=_assets(payload["descriptions"]),
        status=payload.get("status", "PAUSED"),
        path1=payload.get("path1"),
        path2=payload.get("path2"),
    )
    result = AdsManager(_gateway(args.config)).create_responsive_search_ad(
        request, dry_run=args.dry_run
    )
    _print_json(asdict(result))
    return 0 if result.ok else 2


def cmd_update_rsa(args: argparse.Namespace) -> int:
    payload = _load_json_or_file(args.input)
    request = UpdateResponsiveSearchAdRequest(
        customer_id=str(payload["customer_id"]),
        ad_id=str(payload["ad_id"]),
        final_urls=list(payload.get("final_urls", [])),
        final_mobile_urls=list(payload.get("final_mobile_urls", [])),
        headlines=_assets(payload.get("headlines", [])),
        descriptions=_assets(payload.get("descriptions", [])),
    )
    result = AdsManager(_gateway(args.config)).update_responsive_search_ad(
        request, dry_run=args.dry_run
    )
    _print_json(asdict(result))
    return 0 if result.ok else 2


def cmd_pause_ad(args: argparse.Namespace) -> int:
    request = PauseAdRequest(
        customer_id=args.customer_id,
        ad_group_id=args.ad_group_id,
        ad_id=args.ad_id,
    )
    result = AdsManager(_gateway(args.config)).pause_ad(request, dry_run=args.dry_run)
    _print_json(asdict(result))
    return 0 if result.ok else 2


def cmd_report(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    customer_id = args.customer_id or config.default_customer_id
    if not customer_id:
        console.print("[red]customer_id is required.[/red]")
        return 2
    definition = ReportDefinition(
        customer_id=customer_id,
        name=args.name,
        date_range=args.date_range,
        limit=args.limit,
        output=args.output,
        send_feishu=args.send_feishu,
    )
    runner = ReportRunner(
        GoogleAdsGateway(
            yaml_path=config.google_ads_yaml_path,
            api_version=config.google_ads_api_version,
        ),
        reports_dir=config.reports_dir,
    )
    rendered = runner.run(definition)
    console.print(f"[green]Report written:[/green] {rendered.path}")
    if args.send_feishu:
        output = send_file(
            config.feishu,
            file=rendered.path,
            chat_id=args.chat_id,
            dry_run=args.feishu_dry_run,
        )
        console.print(output or "[green]Sent to Feishu.[/green]")
    return 0


def cmd_list_reports(_: argparse.Namespace) -> int:
    table = Table(title="Built-in GAQL reports")
    table.add_column("Name")
    table.add_column("GAQL")
    for name in sorted(REPORT_QUERIES):
        table.add_row(name, build_query(ReportDefinition(customer_id="0", name=name)))
    console.print(table)
    return 0


def cmd_accounts(args: argparse.Namespace) -> int:
    resources = _gateway(args.config).list_accessible_customers()
    if not resources:
        console.print("[yellow]No accessible Google Ads customers returned.[/yellow]")
        return 0

    table = Table(title="Accessible Google Ads customers")
    table.add_column("Resource name")
    table.add_column("Customer ID")
    for resource_name in resources:
        table.add_row(resource_name, resource_name.rsplit("/", 1)[-1])
    console.print(table)
    return 0


def _latest_report_path(reports_dir: str) -> Path | None:
    paths = sorted(
        Path(reports_dir).glob("*.md"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return paths[0] if paths else None


def cmd_send_report(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    report_path = Path(args.file) if args.file else _latest_report_path(config.reports_dir)
    if report_path is None:
        console.print("[red]No report file found. Generate one with the report command first.[/red]")
        return 2
    output = send_file(
        config.feishu,
        file=report_path,
        chat_id=args.chat_id,
        dry_run=args.dry_run,
    )
    console.print(output or "[green]Sent to Feishu.[/green]")
    return 0


def cmd_feishu_test(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    chat_id = args.chat_id or config.feishu.default_chat_id
    if not chat_id:
        console.print("[red]Feishu chat_id is required.[/red]")
        return 2
    command = build_feishu_command(config.feishu, chat_id=chat_id, file=args.file)
    console.print(" ".join(command))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="adwords-agent",
        description="Google Ads API automation CLI for Codex and Feishu reporting.",
    )
    parser.add_argument("--config", help="Path to config.yaml.")
    sub = parser.add_subparsers(dest="command", required=True)

    task = sub.add_parser("task", help="Parse a natural-language task into a JSON plan.")
    task.add_argument("text")
    task.set_defaults(func=cmd_task)

    plan = sub.add_parser("plan", help="Validate and print a structured JSON task.")
    plan.add_argument("input", help="JSON string or JSON file path.")
    plan.set_defaults(func=cmd_plan)

    create = sub.add_parser("create-rsa", help="Create a responsive search ad.")
    create.add_argument("input", help="JSON string or JSON file path.")
    create.add_argument("--execute", dest="dry_run", action="store_false")
    create.set_defaults(func=cmd_create_rsa, dry_run=True)

    update = sub.add_parser("update-rsa", help="Update a responsive search ad.")
    update.add_argument("input", help="JSON string or JSON file path.")
    update.add_argument("--execute", dest="dry_run", action="store_false")
    update.set_defaults(func=cmd_update_rsa, dry_run=True)

    pause = sub.add_parser("pause-ad", help="Pause an ad group ad.")
    pause.add_argument("--customer-id", required=True)
    pause.add_argument("--ad-group-id", required=True)
    pause.add_argument("--ad-id", required=True)
    pause.add_argument("--execute", dest="dry_run", action="store_false")
    pause.set_defaults(func=cmd_pause_ad, dry_run=True)

    report = sub.add_parser("report", help="Run a GAQL report and write Markdown.")
    report.add_argument("--customer-id")
    report.add_argument("--name", choices=sorted(REPORT_QUERIES), default="daily_campaign")
    report.add_argument("--date-range", default="YESTERDAY")
    report.add_argument("--limit", type=int, default=100)
    report.add_argument("--output")
    report.add_argument("--send-feishu", action="store_true")
    report.add_argument("--chat-id")
    report.add_argument("--feishu-dry-run", action="store_true")
    report.set_defaults(func=cmd_report)

    list_reports = sub.add_parser("list-reports", help="Show built-in report queries.")
    list_reports.set_defaults(func=cmd_list_reports)

    accounts = sub.add_parser("accounts", help="List customers accessible to the configured credentials.")
    accounts.set_defaults(func=cmd_accounts)

    send_report = sub.add_parser("send-report", help="Send an existing Markdown report to Feishu.")
    send_report.add_argument("file", nargs="?", help="Report file path. Defaults to the latest reports/*.md.")
    send_report.add_argument("--chat-id")
    send_report.add_argument("--dry-run", action="store_true")
    send_report.set_defaults(func=cmd_send_report)

    feishu_test = sub.add_parser("feishu-test", help="Print the configured Feishu CLI command.")
    feishu_test.add_argument("--chat-id")
    feishu_test.add_argument("--file", default="reports/example.md")
    feishu_test.set_defaults(func=cmd_feishu_test)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except GoogleAdsRuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        return 1
    except Exception as exc:
        console.print(f"[red]{format_google_ads_exception(exc)}[/red]")
        return 1


if __name__ == "__main__":
    sys.exit(main())
