from __future__ import annotations

import json
import re
from typing import Any

from .models import ParsedTask, TaskType


_CUSTOMER_ID = re.compile(r"(?:customer|客户|账户|账号)[^\d]*(\d{6,})", re.IGNORECASE)
_AD_GROUP_ID = re.compile(r"(?:ad.?group|广告组)[^\d]*(\d{3,})", re.IGNORECASE)
_AD_ID = re.compile(r"(?:ad.?id|广告\s*id|广告\s*ID)[^\d]*(\d{3,})", re.IGNORECASE)
_URL = re.compile(r"https?://[^\s，,]+", re.IGNORECASE)


def parse_json_task(text: str) -> ParsedTask | None:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    task_type = TaskType(data.get("task_type", TaskType.UNKNOWN))
    return ParsedTask(task_type=task_type, confidence=1.0, data=data)


def parse_natural_task(text: str) -> ParsedTask:
    json_task = parse_json_task(text)
    if json_task:
        return json_task

    lowered = text.lower()
    data: dict[str, Any] = {}
    notes: list[str] = []
    missing_fields: list[str] = []

    customer = _CUSTOMER_ID.search(text)
    ad_group = _AD_GROUP_ID.search(text)
    ad_id = _AD_ID.search(text)
    urls = _URL.findall(text)
    if customer:
        data["customer_id"] = customer.group(1)
    if ad_group:
        data["ad_group_id"] = ad_group.group(1)
    if ad_id:
        data["ad_id"] = ad_id.group(1)
    if urls:
        data["final_urls"] = urls

    if any(token in text for token in ["报告", "report", "日报"]):
        if "customer_id" not in data:
            missing_fields.append("customer_id")
        report_name = "daily_ad" if "广告" in text else "daily_campaign"
        data.update({"name": report_name, "date_range": "YESTERDAY"})
        return ParsedTask(TaskType.REPORT, 0.74, missing_fields, data, notes)

    if any(token in text for token in ["暂停", "pause"]):
        for field in ["customer_id", "ad_group_id", "ad_id"]:
            if field not in data:
                missing_fields.append(field)
        return ParsedTask(TaskType.PAUSE_AD, 0.78, missing_fields, data, notes)

    if any(token in text for token in ["改", "修改", "更新", "update", "文案"]):
        for field in ["customer_id", "ad_id"]:
            if field not in data:
                missing_fields.append(field)
        notes.append("For copy updates, provide headlines/descriptions as JSON for reliable execution.")
        return ParsedTask(TaskType.UPDATE_RESPONSIVE_SEARCH_AD, 0.62, missing_fields, data, notes)

    if any(token in text for token in ["创建", "新增", "create", "新建"]):
        for field in ["customer_id", "ad_group_id", "final_urls"]:
            if field not in data:
                missing_fields.append(field)
        notes.append("Responsive search ads require at least 3 headlines and 2 descriptions.")
        return ParsedTask(TaskType.CREATE_RESPONSIVE_SEARCH_AD, 0.68, missing_fields, data, notes)

    if "gaql" in lowered:
        return ParsedTask(TaskType.REPORT, 0.6, ["customer_id"], data, notes)

    return ParsedTask(
        TaskType.UNKNOWN,
        0.0,
        ["task_type"],
        data,
        ["Could not infer a supported task. Use JSON for deterministic execution."],
    )
