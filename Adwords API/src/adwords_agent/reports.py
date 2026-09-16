from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from google.protobuf.json_format import MessageToDict

from .google_ads import GoogleAdsGateway
from .models import ReportDefinition


REPORT_QUERIES: dict[str, str] = {
    "daily_campaign": """
        SELECT
          segments.date,
          customer.descriptive_name,
          campaign.id,
          campaign.name,
          campaign.status,
          metrics.impressions,
          metrics.clicks,
          metrics.cost_micros,
          metrics.conversions,
          metrics.conversions_value
        FROM campaign
        WHERE segments.date DURING {date_range}
        ORDER BY metrics.cost_micros DESC
        LIMIT {limit}
    """,
    "daily_ad_group": """
        SELECT
          segments.date,
          campaign.name,
          ad_group.id,
          ad_group.name,
          ad_group.status,
          metrics.impressions,
          metrics.clicks,
          metrics.cost_micros,
          metrics.conversions,
          metrics.conversions_value
        FROM ad_group
        WHERE segments.date DURING {date_range}
        ORDER BY metrics.cost_micros DESC
        LIMIT {limit}
    """,
    "daily_ad": """
        SELECT
          segments.date,
          campaign.name,
          ad_group.name,
          ad_group_ad.ad.id,
          ad_group_ad.status,
          metrics.impressions,
          metrics.clicks,
          metrics.cost_micros,
          metrics.conversions,
          metrics.conversions_value
        FROM ad_group_ad
        WHERE segments.date DURING {date_range}
        ORDER BY metrics.cost_micros DESC
        LIMIT {limit}
    """,
    "daily_change_event": """
        SELECT
          change_event.change_date_time,
          change_event.user_email,
          change_event.client_type,
          change_event.change_resource_type,
          change_event.change_resource_name,
          change_event.resource_change_operation,
          change_event.changed_fields,
          change_event.old_resource,
          change_event.new_resource
        FROM change_event
        WHERE change_event.change_date_time DURING {date_range}
        ORDER BY change_event.change_date_time DESC
        LIMIT {limit}
    """,
}


@dataclass(frozen=True)
class RenderedReport:
    path: Path
    row_count: int
    query: str


def build_query(definition: ReportDefinition) -> str:
    if definition.name not in REPORT_QUERIES:
        names = ", ".join(sorted(REPORT_QUERIES))
        raise ValueError(f"Unknown report '{definition.name}'. Available: {names}")
    return " ".join(
        REPORT_QUERIES[definition.name]
        .format(date_range=definition.date_range, limit=definition.limit)
        .split()
    )


def _row_to_dict(row: Any) -> dict[str, Any]:
    return MessageToDict(
        row._pb,
        preserving_proto_field_name=True,
        always_print_fields_with_no_presence=False,
    )


def _micros_to_currency(value: Any) -> float:
    try:
        return round(float(value) / 1_000_000, 2)
    except (TypeError, ValueError):
        return 0.0


def _get_path(data: dict[str, Any], path: str, default: Any = "") -> Any:
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def render_markdown(
    *,
    definition: ReportDefinition,
    rows: list[Any],
    query: str,
    output_dir: str | Path,
) -> RenderedReport:
    records = [_row_to_dict(row) for row in rows]
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_path = Path(definition.output) if definition.output else output_root / f"{definition.name}-{timestamp}.md"

    if definition.name == "daily_change_event":
        output_path.parent.mkdir(parents=True, exist_ok=True)
        query = query
        lines = _render_change_event_markdown(definition, records, query)
        output_path.write_text("\n".join(lines), encoding="utf-8")
        return RenderedReport(path=output_path, row_count=len(records), query=query)

    lines = [
        f"# Google Ads {definition.name} report",
        "",
        f"- Customer ID: `{definition.customer_id}`",
        f"- Date range: `{definition.date_range}`",
        f"- Rows: `{len(records)}`",
        "",
        "## Summary",
        "",
    ]

    total_impressions = sum(int(_get_path(row, "metrics.impressions", 0)) for row in records)
    total_clicks = sum(int(_get_path(row, "metrics.clicks", 0)) for row in records)
    total_cost = sum(_micros_to_currency(_get_path(row, "metrics.cost_micros", 0)) for row in records)
    total_conversions = sum(float(_get_path(row, "metrics.conversions", 0)) for row in records)
    ctr = round((total_clicks / total_impressions) * 100, 2) if total_impressions else 0
    cpa = round(total_cost / total_conversions, 2) if total_conversions else 0

    lines.extend(
        [
            f"- Impressions: `{total_impressions}`",
            f"- Clicks: `{total_clicks}`",
            f"- CTR: `{ctr}%`",
            f"- Cost: `{total_cost}`",
            f"- Conversions: `{round(total_conversions, 2)}`",
            f"- CPA: `{cpa}`",
            "",
            "## Rows",
            "",
            "| Date | Campaign | Ad group | Ad ID | Status | Impr. | Clicks | Cost | Conv. |",
            "| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: |",
        ]
    )

    for row in records:
        lines.append(
            "| {date} | {campaign} | {ad_group} | {ad_id} | {status} | {impressions} | {clicks} | {cost} | {conversions} |".format(
                date=_get_path(row, "segments.date"),
                campaign=_get_path(row, "campaign.name"),
                ad_group=_get_path(row, "ad_group.name", "-"),
                ad_id=_get_path(row, "ad_group_ad.ad.id", "-"),
                status=_get_path(row, "campaign.status")
                or _get_path(row, "ad_group.status")
                or _get_path(row, "ad_group_ad.status"),
                impressions=_get_path(row, "metrics.impressions", 0),
                clicks=_get_path(row, "metrics.clicks", 0),
                cost=_micros_to_currency(_get_path(row, "metrics.cost_micros", 0)),
                conversions=_get_path(row, "metrics.conversions", 0),
            )
        )

    lines.extend(["", "## GAQL", "", "```sql", query, "```", ""])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return RenderedReport(path=output_path, row_count=len(records), query=query)


def _format_paths(value: Any) -> str:
    paths = value.get("paths", []) if isinstance(value, dict) else []
    if not paths:
        return "-"
    return ", ".join(str(path) for path in paths)


def _json_block(value: Any) -> str:
    if not value:
        return "{}"
    import json

    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def _render_change_event_markdown(
    definition: ReportDefinition, records: list[dict[str, Any]], query: str
) -> list[str]:
    by_operation: dict[str, int] = {}
    by_resource: dict[str, int] = {}
    by_user: dict[str, int] = {}

    for row in records:
        event = row.get("change_event", {})
        operation = str(event.get("resource_change_operation", "UNKNOWN"))
        resource_type = str(event.get("change_resource_type", "UNKNOWN"))
        user = str(event.get("user_email", "UNKNOWN"))
        by_operation[operation] = by_operation.get(operation, 0) + 1
        by_resource[resource_type] = by_resource.get(resource_type, 0) + 1
        by_user[user] = by_user.get(user, 0) + 1

    lines = [
        f"# Google Ads 操作记录报告",
        "",
        f"- Customer ID: `{definition.customer_id}`",
        f"- Date range: `{definition.date_range}`",
        f"- Rows: `{len(records)}`",
        "",
        "## 汇总",
        "",
        "### 按操作类型",
        "",
        "| Operation | Count |",
        "| --- | ---: |",
    ]

    for operation, count in sorted(by_operation.items()):
        lines.append(f"| {operation} | {count} |")

    lines.extend(["", "### 按资源类型", "", "| Resource type | Count |", "| --- | ---: |"])
    for resource_type, count in sorted(by_resource.items()):
        lines.append(f"| {resource_type} | {count} |")

    lines.extend(["", "### 按操作用户", "", "| User | Count |", "| --- | ---: |"])
    for user, count in sorted(by_user.items()):
        lines.append(f"| {user} | {count} |")

    lines.extend(
        [
            "",
            "## 操作明细",
            "",
            "| Time | User | Client | Operation | Resource type | Resource | Changed fields |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )

    for row in records:
        event = row.get("change_event", {})
        lines.append(
            "| {time} | {user} | {client} | {operation} | {resource_type} | `{resource}` | {fields} |".format(
                time=event.get("change_date_time", ""),
                user=event.get("user_email", ""),
                client=event.get("client_type", ""),
                operation=event.get("resource_change_operation", ""),
                resource_type=event.get("change_resource_type", ""),
                resource=event.get("change_resource_name", ""),
                fields=_format_paths(event.get("changed_fields", {})),
            )
        )

    if records:
        lines.extend(["", "## 变更详情", ""])
        for index, row in enumerate(records, start=1):
            event = row.get("change_event", {})
            lines.extend(
                [
                    f"### {index}. {event.get('change_date_time', '')} - {event.get('resource_change_operation', '')} {event.get('change_resource_type', '')}",
                    "",
                    f"- User: `{event.get('user_email', '')}`",
                    f"- Client: `{event.get('client_type', '')}`",
                    f"- Resource: `{event.get('change_resource_name', '')}`",
                    f"- Changed fields: `{_format_paths(event.get('changed_fields', {}))}`",
                    "",
                    "Old resource:",
                    "",
                    "```json",
                    _json_block(event.get("old_resource", {})),
                    "```",
                    "",
                    "New resource:",
                    "",
                    "```json",
                    _json_block(event.get("new_resource", {})),
                    "```",
                    "",
                ]
            )

    lines.extend(["", "## GAQL", "", "```sql", query, "```", ""])
    return lines


class ReportRunner:
    def __init__(self, gateway: GoogleAdsGateway, reports_dir: str | Path) -> None:
        self.gateway = gateway
        self.reports_dir = reports_dir

    def run(self, definition: ReportDefinition) -> RenderedReport:
        query = build_query(definition)
        rows = self.gateway.search_stream(customer_id=definition.customer_id, query=query)
        return render_markdown(
            definition=definition,
            rows=rows,
            query=query,
            output_dir=self.reports_dir,
        )
