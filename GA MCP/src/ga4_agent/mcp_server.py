from __future__ import annotations

import warnings
from functools import lru_cache
from typing import Literal

from google.analytics import admin_v1alpha
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    DateRange,
    Dimension,
    Filter,
    FilterExpression,
    FilterExpressionList,
    GetMetadataRequest,
    Metric,
    MinuteRange,
    OrderBy,
    RunRealtimeReportRequest,
    RunReportRequest,
)
from google.protobuf.field_mask_pb2 import FieldMask
from pydantic import BaseModel, Field, model_validator
from pydantic_settings.exceptions import IncompleteFieldDefinitionWarning

warnings.filterwarnings("ignore", category=IncompleteFieldDefinitionWarning)

from mcp.server.fastmcp import FastMCP  # noqa: E402

from .config import get_settings


SERVER_INSTRUCTIONS = """Google Analytics 4 reporting and controlled Audience-management server.
Use list_properties to resolve a site name before querying when needed.
Use get_metadata before querying when a dimension or metric API name is uncertain.
Use run_report for historical data and run_realtime_report only for the current 30 minutes.
Every number must come from a tool result; never invent missing data. Keep result limits small,
state the queried date range, and remember that GA4 attribution and thresholding can affect totals.
Reporting tools are read-only. Before creating, updating, or archiving an Audience, show the exact
Property and proposed definition to the user and obtain explicit confirmation. First call the write
tool with confirm=false for a non-mutating preview, then repeat it with confirm=true only after the
user confirms. Never guess an Audience definition or claim it is ad-ready unless the returned
ads_personalization_enabled field and Google Ads link settings support that conclusion."""

mcp = FastMCP("Google Analytics 4", instructions=SERVER_INSTRUCTIONS)


class DimensionFilterInput(BaseModel):
    """A string filter applied to a GA4 dimension. Multiple filters are ANDed."""

    field_name: str = Field(description="GA4 dimension API name, for example country or eventName")
    value: str = Field(description="Value to match")
    match_type: Literal[
        "EXACT", "BEGINS_WITH", "ENDS_WITH", "CONTAINS", "FULL_REGEXP", "PARTIAL_REGEXP"
    ] = "EXACT"
    case_sensitive: bool = False
    exclude: bool = False


class OrderByInput(BaseModel):
    """Sort a report by one requested dimension or metric."""

    field_name: str
    descending: bool = True


class AudienceConditionInput(BaseModel):
    """One leaf condition in a GA4 Audience simple filter."""

    kind: Literal["event", "string", "in_list", "numeric", "between"]
    field_name: str | None = Field(
        default=None,
        description="GA4 dimension or metric API name for non-event conditions",
    )
    event_name: str | None = Field(
        default=None,
        description="GA4 event name when kind=event",
    )
    match_type: Literal[
        "EXACT", "BEGINS_WITH", "ENDS_WITH", "CONTAINS", "FULL_REGEXP"
    ] = "EXACT"
    numeric_operation: Literal["EQUAL", "LESS_THAN", "GREATER_THAN"] = "EQUAL"
    value: str | int | float | None = None
    values: list[str] | None = None
    to_value: int | float | None = None
    case_sensitive: bool = False
    negate: bool = False
    at_any_point_in_time: bool | None = None
    in_any_n_day_period: int | None = Field(default=None, ge=1, le=60)

    @model_validator(mode="after")
    def validate_condition(self) -> "AudienceConditionInput":
        if self.kind == "event":
            if not self.event_name or not self.event_name.strip():
                raise ValueError("kind=event 时必须提供 event_name。")
            if self.field_name:
                raise ValueError("kind=event 时不要提供 field_name。")
            if (
                self.at_any_point_in_time is not None
                or self.in_any_n_day_period is not None
            ):
                raise ValueError(
                    "kind=event 不支持 at_any_point_in_time 或 in_any_n_day_period。"
                )
            return self

        if not self.field_name or not self.field_name.strip():
            raise ValueError(f"kind={self.kind} 时必须提供 field_name。")
        if self.event_name:
            raise ValueError(f"kind={self.kind} 时不要提供 event_name。")
        if self.kind == "string" and not isinstance(self.value, str):
            raise ValueError("kind=string 时 value 必须是字符串。")
        if self.kind == "in_list" and not self.values:
            raise ValueError("kind=in_list 时 values 必须是非空字符串列表。")
        if self.kind in ("numeric", "between"):
            if isinstance(self.value, bool) or not isinstance(self.value, (int, float)):
                raise ValueError(f"kind={self.kind} 时 value 必须是数字。")
        if self.kind == "between" and (
            isinstance(self.to_value, bool) or not isinstance(self.to_value, (int, float))
        ):
            raise ValueError("kind=between 时 to_value 必须是数字。")
        return self


class AudienceClauseInput(BaseModel):
    """An INCLUDE or EXCLUDE clause; groups are ANDed and members are ORed."""

    clause_type: Literal["INCLUDE", "EXCLUDE"] = "INCLUDE"
    scope: Literal[
        "WITHIN_SAME_EVENT", "WITHIN_SAME_SESSION", "ACROSS_ALL_SESSIONS"
    ] = "ACROSS_ALL_SESSIONS"
    condition_groups: list[list[AudienceConditionInput]] = Field(
        min_length=1,
        description=(
            "Outer list is AND; each inner non-empty list is OR. "
            "Example: [[event A, event B], [country=US]] means (A OR B) AND country=US."
        ),
    )

    @model_validator(mode="after")
    def validate_groups(self) -> "AudienceClauseInput":
        if any(not group for group in self.condition_groups):
            raise ValueError("condition_groups 中的每个 OR 分组都不能为空。")
        if self.scope != "ACROSS_ALL_SESSIONS":
            for condition in (item for group in self.condition_groups for item in group):
                if (
                    condition.at_any_point_in_time is not None
                    or condition.in_any_n_day_period is not None
                ):
                    raise ValueError(
                        "at_any_point_in_time 和 in_any_n_day_period 只能用于 "
                        "ACROSS_ALL_SESSIONS。"
                    )
        return self


@lru_cache(maxsize=1)
def _client() -> BetaAnalyticsDataClient:
    # The Google client automatically uses Application Default Credentials,
    # including GOOGLE_APPLICATION_CREDENTIALS when it is configured.
    get_settings(require_ga4=True)
    return BetaAnalyticsDataClient()


@lru_cache(maxsize=1)
def _admin_client() -> admin_v1alpha.AnalyticsAdminServiceClient:
    # The Admin client requests the analytics.edit OAuth scope through its
    # standard transport. GA4 roles still determine which operations are allowed.
    get_settings(require_ga4=True)
    return admin_v1alpha.AnalyticsAdminServiceClient()


def _property_name(property: str | None = None) -> str:
    return get_settings(require_ga4=True).resolve_property_name(property)


def _audience_name(audience: str, property: str | None = None) -> str:
    value = audience.strip()
    if value.startswith("properties/"):
        parts = value.split("/")
        if len(parts) != 4 or parts[2] != "audiences" or not (
            parts[1].isdigit() and parts[3].isdigit()
        ):
            raise ValueError(
                "Audience 资源名格式必须是 properties/{propertyId}/audiences/{audienceId}。"
            )
        if property is not None and "/".join(parts[:2]) != _property_name(property):
            raise ValueError("Audience 资源名与指定 Property 不一致。")
        return value
    if not value.isdigit():
        raise ValueError("audience 必须是数字 Audience ID 或完整资源名。")
    return f"{_property_name(property)}/audiences/{value}"


def _numeric_value(value: int | float) -> admin_v1alpha.NumericValue:
    if isinstance(value, int) and not isinstance(value, bool):
        return admin_v1alpha.NumericValue(int64_value=value)
    return admin_v1alpha.NumericValue(double_value=float(value))


def _audience_condition_expression(
    condition: AudienceConditionInput,
) -> admin_v1alpha.AudienceFilterExpression:
    if condition.kind == "event":
        expression = admin_v1alpha.AudienceFilterExpression(
            event_filter=admin_v1alpha.AudienceEventFilter(
                event_name=condition.event_name.strip()
            )
        )
    else:
        kwargs: dict[str, object] = {"field_name": condition.field_name.strip()}
        if condition.at_any_point_in_time is not None:
            kwargs["at_any_point_in_time"] = condition.at_any_point_in_time
        if condition.in_any_n_day_period is not None:
            kwargs["in_any_n_day_period"] = condition.in_any_n_day_period

        if condition.kind == "string":
            kwargs["string_filter"] = (
                admin_v1alpha.AudienceDimensionOrMetricFilter.StringFilter(
                    match_type=getattr(
                        admin_v1alpha.AudienceDimensionOrMetricFilter.StringFilter.MatchType,
                        condition.match_type,
                    ),
                    value=condition.value,
                    case_sensitive=condition.case_sensitive,
                )
            )
        elif condition.kind == "in_list":
            kwargs["in_list_filter"] = (
                admin_v1alpha.AudienceDimensionOrMetricFilter.InListFilter(
                    values=condition.values,
                    case_sensitive=condition.case_sensitive,
                )
            )
        elif condition.kind == "numeric":
            kwargs["numeric_filter"] = (
                admin_v1alpha.AudienceDimensionOrMetricFilter.NumericFilter(
                    operation=getattr(
                        admin_v1alpha.AudienceDimensionOrMetricFilter.NumericFilter.Operation,
                        condition.numeric_operation,
                    ),
                    value=_numeric_value(condition.value),
                )
            )
        elif condition.kind == "between":
            kwargs["between_filter"] = (
                admin_v1alpha.AudienceDimensionOrMetricFilter.BetweenFilter(
                    from_value=_numeric_value(condition.value),
                    to_value=_numeric_value(condition.to_value),
                )
            )
        dimension_filter = admin_v1alpha.AudienceDimensionOrMetricFilter(**kwargs)
        expression = admin_v1alpha.AudienceFilterExpression(
            dimension_or_metric_filter=dimension_filter
        )

    if condition.negate:
        return admin_v1alpha.AudienceFilterExpression(not_expression=expression)
    return expression


def _audience_filter_clause(
    clause: AudienceClauseInput,
) -> admin_v1alpha.AudienceFilterClause:
    and_expressions = []
    for group in clause.condition_groups:
        and_expressions.append(
            admin_v1alpha.AudienceFilterExpression(
                or_group=admin_v1alpha.AudienceFilterExpressionList(
                    filter_expressions=[
                        _audience_condition_expression(condition)
                        for condition in group
                    ]
                )
            )
        )

    scope = getattr(
        admin_v1alpha.AudienceFilterScope,
        f"AUDIENCE_FILTER_SCOPE_{clause.scope}",
    )
    return admin_v1alpha.AudienceFilterClause(
        clause_type=getattr(
            admin_v1alpha.AudienceFilterClause.AudienceClauseType,
            clause.clause_type,
        ),
        simple_filter=admin_v1alpha.AudienceSimpleFilter(
            scope=scope,
            filter_expression=admin_v1alpha.AudienceFilterExpression(
                and_group=admin_v1alpha.AudienceFilterExpressionList(
                    filter_expressions=and_expressions
                )
            ),
        ),
    )


def _build_audience(
    display_name: str,
    description: str,
    membership_duration_days: int,
    filter_clauses: list[AudienceClauseInput],
    exclusion_duration_mode: Literal[
        "EXCLUDE_TEMPORARILY", "EXCLUDE_PERMANENTLY"
    ] = "EXCLUDE_PERMANENTLY",
    event_trigger_name: str | None = None,
    event_trigger_log_condition: Literal[
        "AUDIENCE_JOINED", "AUDIENCE_MEMBERSHIP_RENEWED"
    ] = "AUDIENCE_JOINED",
) -> admin_v1alpha.Audience:
    kwargs: dict[str, object] = {
        "display_name": display_name.strip(),
        "description": description.strip(),
        "membership_duration_days": membership_duration_days,
        "filter_clauses": [
            _audience_filter_clause(clause) for clause in filter_clauses
        ],
    }
    if any(clause.clause_type == "EXCLUDE" for clause in filter_clauses):
        kwargs["exclusion_duration_mode"] = getattr(
            admin_v1alpha.Audience.AudienceExclusionDurationMode,
            exclusion_duration_mode,
        )
    if event_trigger_name:
        kwargs["event_trigger"] = admin_v1alpha.AudienceEventTrigger(
            event_name=event_trigger_name.strip(),
            log_condition=getattr(
                admin_v1alpha.AudienceEventTrigger.LogCondition,
                event_trigger_log_condition,
            ),
        )
    return admin_v1alpha.Audience(**kwargs)


def _admin_message_to_dict(message: object) -> dict:
    return type(message).to_dict(message, use_integers_for_enums=False)


def _dimension_filter_expression(
    filters: list[DimensionFilterInput] | None,
) -> FilterExpression | None:
    if not filters:
        return None

    expressions: list[FilterExpression] = []
    for item in filters:
        match_type = getattr(Filter.StringFilter.MatchType, item.match_type)
        leaf = FilterExpression(
            filter=Filter(
                field_name=item.field_name,
                string_filter=Filter.StringFilter(
                    match_type=match_type,
                    value=item.value,
                    case_sensitive=item.case_sensitive,
                ),
            )
        )
        expressions.append(FilterExpression(not_expression=leaf) if item.exclude else leaf)

    if len(expressions) == 1:
        return expressions[0]
    return FilterExpression(and_group=FilterExpressionList(expressions=expressions))


def _order_bys(
    specs: list[OrderByInput] | None,
    metric_names: set[str],
) -> list[OrderBy]:
    result: list[OrderBy] = []
    for spec in specs or []:
        if spec.field_name in metric_names:
            result.append(
                OrderBy(
                    metric=OrderBy.MetricOrderBy(metric_name=spec.field_name),
                    desc=spec.descending,
                )
            )
        else:
            result.append(
                OrderBy(
                    dimension=OrderBy.DimensionOrderBy(dimension_name=spec.field_name),
                    desc=spec.descending,
                )
            )
    return result


def _quota_to_dict(quota: object | None) -> dict[str, dict[str, int]] | None:
    if not quota:
        return None
    fields = (
        "tokens_per_day",
        "tokens_per_hour",
        "concurrent_requests",
        "server_errors_per_project_per_hour",
        "potentially_thresholded_requests_per_hour",
        "tokens_per_project_per_hour",
    )
    result: dict[str, dict[str, int]] = {}
    for field_name in fields:
        status = getattr(quota, field_name, None)
        if status:
            result[field_name] = {
                "consumed": int(status.consumed),
                "remaining": int(status.remaining),
            }
    return result or None


def _report_to_dict(response: object) -> dict:
    dimension_names = [header.name for header in response.dimension_headers]
    metric_names = [header.name for header in response.metric_headers]
    rows = []
    for row in response.rows:
        rows.append(
            {
                "dimensions": {
                    name: value.value
                    for name, value in zip(dimension_names, row.dimension_values, strict=True)
                },
                "metrics": {
                    name: value.value
                    for name, value in zip(metric_names, row.metric_values, strict=True)
                },
            }
        )

    metadata = getattr(response, "metadata", None)
    output = {
        "dimension_headers": dimension_names,
        "metric_headers": metric_names,
        "rows": rows,
        "row_count": int(getattr(response, "row_count", len(rows))),
    }
    if metadata:
        output["metadata"] = {
            "currency_code": getattr(metadata, "currency_code", ""),
            "time_zone": getattr(metadata, "time_zone", ""),
            "data_loss_from_other_row": bool(
                getattr(metadata, "data_loss_from_other_row", False)
            ),
            "subject_to_thresholding": bool(
                getattr(metadata, "subject_to_thresholding", False)
            ),
        }
    quota = _quota_to_dict(getattr(response, "property_quota", None))
    if quota:
        output["property_quota"] = quota
    return output


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
def list_properties() -> dict:
    """List configured GA4 site aliases and Property IDs."""
    settings = get_settings(require_ga4=True)
    default_property = settings.resolve_property_name()
    return {
        "default_property": default_property,
        "properties": {
            alias: (
                property_id
                if property_id.startswith("properties/")
                else f"properties/{property_id}"
            )
            for alias, property_id in sorted(settings.properties.items())
        },
    }


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
def check_connection(property: str | None = None) -> dict:
    """Check credentials and one configured Property with a small 7-day query.

    Property accepts a configured site alias such as demo or a numeric ID.
    """
    property_name = _property_name(property)
    response = _client().run_report(
        RunReportRequest(
            property=property_name,
            metrics=[Metric(name="activeUsers")],
            date_ranges=[DateRange(start_date="7daysAgo", end_date="yesterday")],
            limit=1,
        )
    )
    report = _report_to_dict(response)
    return {
        "ok": True,
        "property": property_name,
        "date_range": {"start_date": "7daysAgo", "end_date": "yesterday"},
        "sample": report,
    }


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
def run_report(
    metrics: list[str],
    property: str | None = None,
    dimensions: list[str] | None = None,
    start_date: str = "7daysAgo",
    end_date: str = "yesterday",
    dimension_filters: list[DimensionFilterInput] | None = None,
    order_by: list[OrderByInput] | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """Run a historical GA4 report.

    Property accepts a configured site alias or numeric ID. Dates accept YYYY-MM-DD
    or relative values such as 7daysAgo, yesterday, or today.
    Use GA4 API names for dimensions and metrics. Up to 9 dimensions and 10 metrics
    are allowed. Results are read-only and the returned row count may exceed this page.
    """
    dimensions = dimensions or []
    if not metrics:
        raise ValueError("metrics 至少需要一个 GA4 metric API name。")
    if len(dimensions) > 9:
        raise ValueError("GA4 每次查询最多支持 9 个 dimensions。")
    if len(metrics) > 10:
        raise ValueError("GA4 每次查询最多支持 10 个 metrics。")
    if not 1 <= limit <= 10_000:
        raise ValueError("limit 必须在 1 到 10000 之间。")
    if offset < 0:
        raise ValueError("offset 不能小于 0。")

    property_name = _property_name(property)
    request = RunReportRequest(
        property=property_name,
        dimensions=[Dimension(name=name) for name in dimensions],
        metrics=[Metric(name=name) for name in metrics],
        date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
        dimension_filter=_dimension_filter_expression(dimension_filters),
        order_bys=_order_bys(order_by, set(metrics)),
        limit=limit,
        offset=offset,
        return_property_quota=True,
    )
    result = _report_to_dict(_client().run_report(request))
    result["query"] = {
        "property": property_name,
        "start_date": start_date,
        "end_date": end_date,
        "dimensions": dimensions,
        "metrics": metrics,
        "limit": limit,
        "offset": offset,
    }
    return result


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
def run_realtime_report(
    metrics: list[str],
    property: str | None = None,
    dimensions: list[str] | None = None,
    minutes_ago: int = 30,
    dimension_filters: list[DimensionFilterInput] | None = None,
    order_by: list[OrderByInput] | None = None,
    limit: int = 100,
) -> dict:
    """Run a GA4 realtime report for the last 1-30 minutes.

    Property accepts a configured site alias or numeric ID. Only realtime-compatible
    dimension and metric API names are valid. Standard
    properties expose up to 30 minutes of realtime data.
    """
    dimensions = dimensions or []
    if not metrics:
        raise ValueError("metrics 至少需要一个 realtime metric API name。")
    if not 1 <= minutes_ago <= 30:
        raise ValueError("minutes_ago 必须在 1 到 30 之间。")
    if not 1 <= limit <= 10_000:
        raise ValueError("limit 必须在 1 到 10000 之间。")

    property_name = _property_name(property)
    request = RunRealtimeReportRequest(
        property=property_name,
        dimensions=[Dimension(name=name) for name in dimensions],
        metrics=[Metric(name=name) for name in metrics],
        dimension_filter=_dimension_filter_expression(dimension_filters),
        order_bys=_order_bys(order_by, set(metrics)),
        minute_ranges=[
            MinuteRange(
                name=f"last_{minutes_ago}_minutes",
                start_minutes_ago=minutes_ago - 1,
                end_minutes_ago=0,
            )
        ],
        limit=limit,
        return_property_quota=True,
    )
    result = _report_to_dict(_client().run_realtime_report(request))
    result["query"] = {
        "property": property_name,
        "minutes_ago": minutes_ago,
        "dimensions": dimensions,
        "metrics": metrics,
        "limit": limit,
    }
    return result


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
def get_metadata(
    property: str | None = None,
    search: str = "",
    kind: Literal["dimensions", "metrics", "both"] = "both",
    include_deprecated_aliases: bool = False,
    limit: int = 100,
) -> dict:
    """List/search dimensions and metrics available to this GA4 property.

    Property accepts a configured site alias or numeric ID. Search matches API name,
    UI name, category, and description. This includes
    property-specific custom definitions and should be used before guessing names.
    """
    if not 1 <= limit <= 1_000:
        raise ValueError("limit 必须在 1 到 1000 之间。")

    property_name = _property_name(property)
    response = _client().get_metadata(GetMetadataRequest(name=f"{property_name}/metadata"))
    needle = search.casefold().strip()

    def matches(item: object) -> bool:
        haystack = " ".join(
            str(getattr(item, field, ""))
            for field in ("api_name", "ui_name", "category", "description")
        ).casefold()
        return not needle or needle in haystack

    def serialize(item: object) -> dict:
        result = {
            "api_name": item.api_name,
            "ui_name": item.ui_name,
            "category": item.category,
            "description": item.description,
            "custom_definition": bool(item.custom_definition),
        }
        if include_deprecated_aliases and item.deprecated_api_names:
            result["deprecated_api_names"] = list(item.deprecated_api_names)
        return result

    dimensions = []
    if kind in ("dimensions", "both"):
        dimensions = [
            serialize(item)
            for item in response.dimensions
            if matches(item)
        ][:limit]

    metrics = []
    if kind in ("metrics", "both"):
        metrics = [
            serialize(item)
            for item in response.metrics
            if matches(item)
        ][:limit]

    return {
        "property": property_name,
        "search": search,
        "dimensions": dimensions,
        "metrics": metrics,
        "counts": {"dimensions": len(dimensions), "metrics": len(metrics)},
        "truncated_at": limit,
    }


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
def list_audiences(
    property: str | None = None,
    page_size: int = 50,
    page_token: str = "",
) -> dict:
    """List one page of GA4 Audiences configured on a Property.

    This uses the Google Analytics Admin API and does not change GA4. Property
    accepts a configured site alias or numeric ID. Use the returned
    ads_personalization_enabled field when assessing whether an Audience is
    eligible for ads personalization.
    """
    if not 1 <= page_size <= 200:
        raise ValueError("page_size 必须在 1 到 200 之间。")

    property_name = _property_name(property)
    pager = _admin_client().list_audiences(
        request=admin_v1alpha.ListAudiencesRequest(
            parent=property_name,
            page_size=page_size,
            page_token=page_token,
        )
    )
    page = next(iter(pager.pages))
    audiences = [_admin_message_to_dict(item) for item in page.audiences]
    return {
        "property": property_name,
        "audiences": audiences,
        "count": len(audiences),
        "next_page_token": page.next_page_token,
    }


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
def get_audience(audience: str, property: str | None = None) -> dict:
    """Get one GA4 Audience by numeric ID or full resource name."""
    name = _audience_name(audience, property)
    result = _admin_client().get_audience(
        request=admin_v1alpha.GetAudienceRequest(name=name)
    )
    return _admin_message_to_dict(result)


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
def list_google_ads_links(
    property: str | None = None,
    page_size: int = 50,
    page_token: str = "",
) -> dict:
    """List Google Ads links for a GA4 Property without changing them.

    Use this before claiming that a newly created Audience will export to Ads.
    The link must exist and personalized advertising must be enabled.
    """
    if not 1 <= page_size <= 200:
        raise ValueError("page_size 必须在 1 到 200 之间。")

    property_name = _property_name(property)
    pager = _admin_client().list_google_ads_links(
        request=admin_v1alpha.ListGoogleAdsLinksRequest(
            parent=property_name,
            page_size=page_size,
            page_token=page_token,
        )
    )
    page = next(iter(pager.pages))
    links = [_admin_message_to_dict(item) for item in page.google_ads_links]
    return {
        "property": property_name,
        "google_ads_links": links,
        "count": len(links),
        "next_page_token": page.next_page_token,
    }


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    }
)
def create_audience(
    display_name: str,
    description: str,
    filter_clauses: list[AudienceClauseInput],
    property: str | None = None,
    membership_duration_days: int = 30,
    exclusion_duration_mode: Literal[
        "EXCLUDE_TEMPORARILY", "EXCLUDE_PERMANENTLY"
    ] = "EXCLUDE_PERMANENTLY",
    event_trigger_name: str | None = None,
    event_trigger_log_condition: Literal[
        "AUDIENCE_JOINED", "AUDIENCE_MEMBERSHIP_RENEWED"
    ] = "AUDIENCE_JOINED",
    confirm: bool = False,
) -> dict:
    """Preview or create a GA4 Audience with simple INCLUDE/EXCLUDE clauses.

    This changes GA4 only when confirm=true. Always call once with confirm=false,
    show the returned preview to the user, and obtain explicit confirmation before
    repeating the exact request with confirm=true. Audience definitions and
    membership duration are immutable after creation; an unwanted Audience must be
    archived. Conditions within each inner group are ORed; groups and clauses are
    ANDed. Sequence filters are not supported by this tool.
    """
    if not display_name.strip():
        raise ValueError("display_name 不能为空。")
    if not description.strip():
        raise ValueError("description 不能为空。")
    if not 1 <= membership_duration_days <= 540:
        raise ValueError("membership_duration_days 必须在 1 到 540 之间。")
    if not filter_clauses:
        raise ValueError("filter_clauses 至少需要一个 INCLUDE 条件。")
    if not any(clause.clause_type == "INCLUDE" for clause in filter_clauses):
        raise ValueError("filter_clauses 至少需要一个 INCLUDE 条件。")
    if event_trigger_name is not None and not event_trigger_name.strip():
        raise ValueError("event_trigger_name 不能是空白字符串。")

    property_name = _property_name(property)
    audience = _build_audience(
        display_name=display_name,
        description=description,
        membership_duration_days=membership_duration_days,
        filter_clauses=filter_clauses,
        exclusion_duration_mode=exclusion_duration_mode,
        event_trigger_name=event_trigger_name,
        event_trigger_log_condition=event_trigger_log_condition,
    )
    audience_definition = _admin_message_to_dict(audience)
    for output_only_field in ("name", "ads_personalization_enabled", "create_time"):
        audience_definition.pop(output_only_field, None)
    if (
        audience_definition.get("exclusion_duration_mode")
        == "AUDIENCE_EXCLUSION_DURATION_MODE_UNSPECIFIED"
    ):
        audience_definition.pop("exclusion_duration_mode")
    preview = {
        "property": property_name,
        "audience": audience_definition,
        "warning": (
            "Audience 条件和成员资格期限创建后不可修改；请确认 Property、名称、"
            "条件、排除模式与期限。"
        ),
    }
    if not confirm:
        return {
            "created": False,
            "requires_confirmation": True,
            "preview": preview,
        }

    result = _admin_client().create_audience(
        request=admin_v1alpha.CreateAudienceRequest(
            parent=property_name,
            audience=audience,
        )
    )
    return {
        "created": True,
        "property": property_name,
        "audience": _admin_message_to_dict(result),
    }


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
def update_audience(
    audience: str,
    property: str | None = None,
    display_name: str | None = None,
    description: str | None = None,
    confirm: bool = False,
) -> dict:
    """Preview or update the mutable name/description of one GA4 Audience.

    This changes GA4 only when confirm=true. Filters and membership duration are
    immutable and therefore intentionally not accepted here.
    """
    changes = {}
    if display_name is not None:
        if not display_name.strip():
            raise ValueError("display_name 不能是空白字符串。")
        changes["display_name"] = display_name.strip()
    if description is not None:
        if not description.strip():
            raise ValueError("description 不能是空白字符串。")
        changes["description"] = description.strip()
    if not changes:
        raise ValueError("至少提供 display_name 或 description 中的一项。")

    name = _audience_name(audience, property)
    current = _admin_client().get_audience(
        request=admin_v1alpha.GetAudienceRequest(name=name)
    )
    if not confirm:
        return {
            "updated": False,
            "requires_confirmation": True,
            "preview": {
                "property": "/".join(name.split("/")[:2]),
                "current": _admin_message_to_dict(current),
                "proposed_changes": changes,
            },
        }

    result = _admin_client().update_audience(
        request=admin_v1alpha.UpdateAudienceRequest(
            audience=admin_v1alpha.Audience(name=name, **changes),
            update_mask=FieldMask(paths=list(changes)),
        )
    )
    return {
        "updated": True,
        "property": "/".join(name.split("/")[:2]),
        "audience": _admin_message_to_dict(result),
    }


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    }
)
def archive_audience(
    audience: str,
    property: str | None = None,
    confirm: bool = False,
) -> dict:
    """Preview or archive one GA4 Audience.

    Archiving is a destructive external action and occurs only when confirm=true.
    Always preview first and obtain explicit user confirmation for the exact resource.
    """
    name = _audience_name(audience, property)
    current = _admin_client().get_audience(
        request=admin_v1alpha.GetAudienceRequest(name=name)
    )
    preview = {
        "property": "/".join(name.split("/")[:2]),
        "audience": _admin_message_to_dict(current),
        "warning": "归档后该 Audience 将不再继续积累成员；请确认准确资源。",
    }
    if not confirm:
        return {
            "archived": False,
            "requires_confirmation": True,
            "preview": preview,
        }

    _admin_client().archive_audience(
        request=admin_v1alpha.ArchiveAudienceRequest(name=name)
    )
    return {
        "archived": True,
        "property": preview["property"],
        "audience": preview["audience"],
    }


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
