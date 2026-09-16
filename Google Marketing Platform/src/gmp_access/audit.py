from __future__ import annotations

import json
import getpass
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import Settings
from .models import ActionResult


def audit_path(settings: Settings) -> Path:
    return settings.root / ".data" / "audit.jsonl"


def _append_event(settings: Settings, event: dict[str, Any]) -> dict[str, Any]:
    path = audit_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
        stream.flush()
    return event


def append_audit_start(
    settings: Settings,
    *,
    plan: dict[str, Any],
    identity: dict[str, Any],
) -> dict[str, Any]:
    event = {
        "event": "started",
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "plan_id": plan["plan_id"],
        "intent": plan.get("intent"),
        "reason": plan.get("reason") or "",
        "catalog_sha256": plan.get("catalog_sha256") or "",
        "action_count": len(plan.get("actions") or []),
        "local_actor": getpass.getuser(),
        "host": socket.gethostname(),
        "credential_identity": identity,
    }
    return _append_event(settings, event)


def append_audit(
    settings: Settings,
    *,
    plan: dict[str, Any],
    results: list[ActionResult],
    summary: dict[str, int],
    complete: bool,
) -> dict[str, Any]:
    event = {
        "event": "finished",
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "plan_id": plan["plan_id"],
        "intent": plan.get("intent"),
        "reason": plan.get("reason") or "",
        "complete": complete,
        "summary": summary,
        "results": [item.to_dict() for item in results],
    }
    return _append_event(settings, event)


def read_history(
    settings: Settings,
    *,
    limit: int = 20,
    plan_id: str | None = None,
) -> list[dict[str, Any]]:
    path = audit_path(settings)
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            row = {"error": "audit line is not valid JSON"}
        if plan_id and row.get("plan_id") != plan_id:
            continue
        rows.append(row)
    return rows[-max(1, min(limit, 200)) :]
