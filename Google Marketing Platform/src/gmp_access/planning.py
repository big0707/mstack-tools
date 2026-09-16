from __future__ import annotations

import hashlib
import json
import os
import re
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from .config import Settings
from .errors import GmpError
from .models import Action
from .roles import is_privileged


SCHEMA_VERSION = 1
PLAN_TTL_HOURS = 24
PLAN_ID_RE = re.compile(r"^[0-9a-f]{16}$")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    # Fixed-width fractional seconds preserve chronological ordering when these
    # UTC strings are compared in the resource-state safety gate.
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _canonical(payload: dict[str, Any]) -> bytes:
    immutable = {key: value for key, value in payload.items() if key != "plan_id"}
    return json.dumps(
        immutable,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(payload)).hexdigest()[:16]


def _catalog_fingerprint(settings: Settings) -> str:
    try:
        return hashlib.sha256(settings.catalog.path.read_bytes()).hexdigest()
    except OSError:
        return ""


def _latest_plan_created_at(directory: Path) -> datetime | None:
    latest: datetime | None = None
    for path in directory.glob("*.json"):
        if not PLAN_ID_RE.fullmatch(path.stem):
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            created = datetime.fromisoformat(
                str(payload["created_at"]).replace("Z", "+00:00")
            )
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise GmpError(
                f"已有计划的创建时间无法读取：{path.name}",
                "停止生成新计划并人工检查 .data/plans；不要删除未审计的执行证据",
            ) from exc
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        else:
            created = created.astimezone(timezone.utc)
        if latest is None or created > latest:
            latest = created
    return latest


def plan_directory(settings: Settings) -> Path:
    return settings.root / ".data" / "plans"


def _atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{os.getpid()}.tmp"
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def create_plan(
    settings: Settings,
    actions: list[Action],
    *,
    intent: str,
    reason: str | None = None,
) -> dict[str, Any]:
    if not actions:
        raise GmpError("计划为空。", "检查品牌、产品和资源目录")
    directory = plan_directory(settings)
    directory.mkdir(parents=True, exist_ok=True)
    with _file_lock(
        directory / ".create.lock",
        "另一个进程正在生成权限计划；本次未生成 plan。",
    ):
        now = _utcnow()
        latest = _latest_plan_created_at(directory)
        if latest is not None and now <= latest:
            now = latest + timedelta(microseconds=1)
        expires = now + timedelta(hours=PLAN_TTL_HOURS)
        payload: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "created_at": _iso(now),
            "expires_at": _iso(expires),
            "intent": intent,
            "reason": (reason or "").strip(),
            "catalog_sha256": _catalog_fingerprint(settings),
            "privileged": any(
                bool(action.role and is_privileged(action.product, action.role))
                for action in actions
            ),
            "actions": [action.to_dict() for action in actions],
        }
        payload["plan_id"] = _digest(payload)
        path = directory / f"{payload['plan_id']}.json"
        _atomic_json_write(path, payload)
        return payload


def load_plan(
    settings: Settings,
    plan_id: str,
    *,
    allow_expired: bool = False,
    require_current_catalog: bool = False,
) -> dict[str, Any]:
    normalized = plan_id.strip().casefold()
    if not PLAN_ID_RE.fullmatch(normalized):
        raise GmpError("plan_id 格式不合法。", "先运行 dry-run 命令生成新的 plan_id")
    path = plan_directory(settings) / f"{normalized}.json"
    if not path.is_file():
        raise GmpError(f"找不到计划：{normalized}", "重新运行 dry-run 命令生成计划")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GmpError(f"计划文件无法读取：{exc}", "重新生成计划；不要手工修改 .data/plans") from exc
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise GmpError("计划版本不受支持。", "重新运行 dry-run 命令生成计划")
    if payload.get("plan_id") != normalized or _digest(payload) != normalized:
        raise GmpError("计划校验失败，内容可能被改过。", "重新生成计划；不要手工修改 plan JSON")
    if require_current_catalog:
        planned_catalog = str(payload.get("catalog_sha256") or "")
        current_catalog = _catalog_fingerprint(settings)
        if not planned_catalog or planned_catalog != current_catalog:
            raise GmpError(
                "catalog.yaml 在计划生成后发生了变化，旧计划已失效。",
                "重新生成并核对新计划，避免遗漏新增资源或使用已纠正的资源映射",
            )
    try:
        expires = datetime.fromisoformat(str(payload["expires_at"]).replace("Z", "+00:00"))
    except (KeyError, ValueError) as exc:
        raise GmpError("计划缺少有效过期时间。", "重新生成计划") from exc
    if not allow_expired and expires <= _utcnow():
        raise GmpError("计划已过期。", "资源或权限可能已变化，请重新生成 dry-run 计划")
    return payload


def actions_from_plan(payload: dict[str, Any]) -> list[Action]:
    try:
        return [Action.from_dict(item) for item in payload["actions"]]
    except (KeyError, TypeError, ValueError) as exc:
        raise GmpError("计划里的 action 无法解析。", "重新生成计划") from exc


def plan_state_path(settings: Settings, plan_id: str) -> Path:
    return plan_directory(settings) / f"{plan_id}.state.json"


def _resource_state_path(settings: Settings) -> Path:
    return settings.root / ".data" / "resource-state.json"


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GmpError(
            f"本地执行状态无法读取：{path.name}",
            "停止执行并人工检查 .data；不要在状态不明时重复写入",
        ) from exc
    if not isinstance(payload, dict):
        raise GmpError(
            f"本地执行状态格式错误：{path.name}",
            "停止执行并人工检查 .data",
        )
    return payload


def _resource_keys(plan: dict[str, Any]) -> list[str]:
    return sorted(
        {
            f"{str(action.get('product') or '').casefold()}|{str(action.get('email') or '').casefold()}"
            for action in plan.get("actions") or []
        }
    )


def begin_plan_attempt(settings: Settings, plan: dict[str, Any]) -> dict[str, Any]:
    """Claim a plan once and reject older plans for the same user/product."""
    plan_id = str(plan["plan_id"])
    state_path = plan_state_path(settings, plan_id)
    if state_path.exists():
        state = _read_json_object(state_path)
        raise GmpError(
            f"计划 {plan_id} 已经执行或曾开始执行（状态：{state.get('status', 'unknown')}）。",
            "不要重放旧计划；运行 gmp history 复核，并根据当前状态生成一个新计划",
        )
    resource_path = _resource_state_path(settings)
    resource_state = _read_json_object(resource_path)
    planned_at = str(plan.get("created_at") or "")
    resource_keys = _resource_keys(plan)
    previous_resources = {key: resource_state.get(key) for key in resource_keys}
    for key in resource_keys:
        previous = resource_state.get(key) or {}
        if (
            previous.get("plan_id") != plan_id
            and str(previous.get("plan_created_at") or "") > planned_at
        ):
            raise GmpError(
                f"该人员/产品已有更新的计划执行记录：{key}",
                "旧计划可能覆盖后续入职、升职或撤权；请按当前状态重新生成计划",
            )
    started_at = _iso(_utcnow())
    attempt = {
        "plan_id": plan_id,
        "status": "running",
        "started_at": started_at,
        "plan_created_at": planned_at,
        "pid": os.getpid(),
        "previous_resources": previous_resources,
    }
    _atomic_json_write(state_path, attempt)
    for key in resource_keys:
        resource_state[key] = {
            "plan_id": plan_id,
            "plan_created_at": planned_at,
            "started_at": started_at,
        }
    try:
        _atomic_json_write(resource_path, resource_state)
    except Exception:
        try:
            state_path.unlink()
        except FileNotFoundError:
            pass
        raise
    return attempt


def cancel_plan_attempt(settings: Settings, plan: dict[str, Any]) -> None:
    """Roll back only the local claim when the mandatory start audit failed."""
    plan_id = str(plan["plan_id"])
    state_path = plan_state_path(settings, plan_id)
    state = _read_json_object(state_path)
    try:
        state_path.unlink()
    except FileNotFoundError:
        pass
    resource_path = _resource_state_path(settings)
    resource_state = _read_json_object(resource_path)
    changed = False
    for key in _resource_keys(plan):
        if (resource_state.get(key) or {}).get("plan_id") == plan_id:
            previous = (state.get("previous_resources") or {}).get(key)
            if previous is None:
                del resource_state[key]
            else:
                resource_state[key] = previous
            changed = True
    if changed:
        _atomic_json_write(resource_path, resource_state)


def finish_plan_attempt(
    settings: Settings,
    plan: dict[str, Any],
    *,
    results: list[dict[str, Any]],
    summary: dict[str, int],
    complete: bool,
) -> dict[str, Any]:
    state = _read_json_object(plan_state_path(settings, str(plan["plan_id"])))
    state.update(
        {
            "status": "finished",
            "finished_at": _iso(_utcnow()),
            "complete": complete,
            "summary": summary,
            "results": results,
        }
    )
    _atomic_json_write(plan_state_path(settings, str(plan["plan_id"])), state)
    return state


@contextmanager
def _file_lock(path: Path, message: str) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    stream = path.open("a+b")
    stream.seek(0, os.SEEK_END)
    if stream.tell() == 0:
        stream.write(b"0")
        stream.flush()
    stream.seek(0)
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        stream.close()
        raise GmpError(message, "等待当前执行结束，再查 gmp history") from exc
    try:
        yield
    finally:
        stream.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        stream.close()


def apply_lock(settings: Settings) -> Iterator[None]:
    return _file_lock(
        settings.root / ".data" / "apply.lock",
        "另一个权限计划正在执行；为防止跨计划竞态，本次未开始。",
    )


@contextmanager
def plan_lock(settings: Settings, plan_id: str) -> Iterator[None]:
    with _file_lock(
        plan_directory(settings) / f"{plan_id}.lock",
        f"计划 {plan_id} 正在被另一个进程执行。",
    ):
        yield
