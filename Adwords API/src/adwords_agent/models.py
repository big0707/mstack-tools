from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TaskType(str, Enum):
    CREATE_RESPONSIVE_SEARCH_AD = "create_responsive_search_ad"
    UPDATE_RESPONSIVE_SEARCH_AD = "update_responsive_search_ad"
    PAUSE_AD = "pause_ad"
    REPORT = "report"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class TextAssetSpec:
    text: str
    pinned_field: str | None = None


@dataclass(frozen=True)
class CreateResponsiveSearchAdRequest:
    customer_id: str
    ad_group_id: str
    final_urls: list[str]
    headlines: list[TextAssetSpec]
    descriptions: list[TextAssetSpec]
    status: str = "PAUSED"
    path1: str | None = None
    path2: str | None = None


@dataclass(frozen=True)
class UpdateResponsiveSearchAdRequest:
    customer_id: str
    ad_id: str
    final_urls: list[str] = field(default_factory=list)
    final_mobile_urls: list[str] = field(default_factory=list)
    headlines: list[TextAssetSpec] = field(default_factory=list)
    descriptions: list[TextAssetSpec] = field(default_factory=list)


@dataclass(frozen=True)
class PauseAdRequest:
    customer_id: str
    ad_group_id: str
    ad_id: str


@dataclass(frozen=True)
class ReportDefinition:
    customer_id: str
    name: str = "daily_campaign"
    date_range: str = "YESTERDAY"
    limit: int = 100
    output: str | None = None
    send_feishu: bool = False


@dataclass(frozen=True)
class ExecutionResult:
    ok: bool
    action: str
    resource_names: list[str] = field(default_factory=list)
    message: str = ""
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ParsedTask:
    task_type: TaskType
    confidence: float
    missing_fields: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
