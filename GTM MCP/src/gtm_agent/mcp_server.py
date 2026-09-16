from __future__ import annotations

from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from .builders import (
    TagPreset,
    TriggerPreset,
    VariablePreset,
    build_tag_body,
    build_trigger_body,
    build_variable_body,
)
from .client import GtmClient, Target, get_client
from .config import get_settings, read_service_account_identity


SERVER_INSTRUCTIONS = """Google Tag Manager (GTM) configuration server using Tag Manager API v2.

Use resolve_target or list_accounts / list_containers before changing anything.
Read tools never invent account data. If credentials are missing, stop and tell
the user to follow README.md. Write, delete, version, and publish tools are
two-step: first call with confirm=false, show the exact preview, and only repeat
with confirm=true after explicit user confirmation. create_version deletes the
current workspace after snapshotting it. Never publish to live unless the user
explicitly asked. Never print .env or service-account JSON contents."""

mcp = FastMCP("Google Tag Manager", instructions=SERVER_INSTRUCTIONS)


def _client() -> GtmClient:
    return get_client()


def _target(
    container: str | None = None,
    account: str | None = None,
    workspace: str | None = None,
) -> Target:
    return _client().resolve(container=container, account=account, workspace=workspace)


def _compact_tag(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "tagId": item.get("tagId"),
        "name": item.get("name"),
        "type": item.get("type"),
        "paused": bool(item.get("paused")),
        "firingTriggerId": item.get("firingTriggerId", []),
        "path": item.get("path"),
        "notes": item.get("notes", ""),
    }


def _compact_trigger(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "triggerId": item.get("triggerId"),
        "name": item.get("name"),
        "type": item.get("type"),
        "path": item.get("path"),
        "notes": item.get("notes", ""),
    }


def _compact_variable(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "variableId": item.get("variableId"),
        "name": item.get("name"),
        "type": item.get("type"),
        "path": item.get("path"),
        "notes": item.get("notes", ""),
    }


def _maybe_compact(items: list[dict[str, Any]], compact: bool, kind: str) -> list[dict[str, Any]]:
    if not compact:
        return items
    if kind == "tag":
        return [_compact_tag(item) for item in items]
    if kind == "trigger":
        return [_compact_trigger(item) for item in items]
    if kind == "variable":
        return [_compact_variable(item) for item in items]
    return items


def _ensure_writable() -> None:
    settings = get_settings(require_credentials=True)
    if settings.read_only:
        raise RuntimeError(
            "当前 GTM_READ_ONLY=true，拒绝写操作。把 .env 中的 GTM_READ_ONLY 设为 false 后再试。"
        )


def _preview_or_apply(confirm: bool, action: str, preview: dict[str, Any]) -> dict[str, Any] | None:
    _ensure_writable()
    if not confirm:
        return {
            "applied": False,
            "requires_confirmation": True,
            "action": action,
            "preview": preview,
        }
    return None


def _entity_path(target: Target, kind: str, entity_id: str) -> str:
    value = entity_id.strip()
    if value.startswith("accounts/"):
        return value
    plural = {
        "tag": "tags",
        "trigger": "triggers",
        "variable": "variables",
        "version": "versions",
    }[kind]
    parent = target.container_path if kind == "version" else target.workspace_path
    return f"{parent}/{plural}/{value}"


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
def whoami() -> dict[str, Any]:
    """Show the configured service-account identity without reading the private key."""
    settings = get_settings(require_credentials=False)
    identity = read_service_account_identity(settings.credentials_path)
    return {
        "client_email": identity.get("client_email"),
        "project_id": identity.get("project_id"),
        "credentials_type": identity.get("type"),
        "credentials_path_exists": identity.get("credentials_path_exists") == "true",
        "read_only_mode": settings.read_only,
        "default_account_id": settings.account_id or None,
        "default_container_id": settings.container_id or None,
        "container_aliases": settings.containers,
    }


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
def check_connection(container: str | None = None) -> dict[str, Any]:
    """Verify credentials and list accessible GTM accounts. Optionally resolve one container."""
    client = _client()
    accounts = client.list_accounts()
    result: dict[str, Any] = {
        "ok": True,
        "client_email": client.identity.get("client_email"),
        "project_id": client.identity.get("project_id"),
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
    if container or get_settings(require_credentials=False).container_id:
        result["target"] = client.resolve(container=container).to_dict()
    return result


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
def list_accounts() -> dict[str, Any]:
    """List GTM accounts visible to the service account."""
    accounts = _client().list_accounts()
    return {"accounts": accounts, "count": len(accounts)}


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
def list_containers(account: str | None = None) -> dict[str, Any]:
    """List containers in one account, or in every accessible account if omitted."""
    client = _client()
    settings = get_settings(require_credentials=True)
    account_id = account or settings.account_id
    if account_id:
        containers = client.list_containers(account_id)
        return {"account": account_id, "containers": containers, "count": len(containers)}

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
    return {"accounts": grouped, "count": total}


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
def get_container(
    container: str | None = None,
    account: str | None = None,
) -> dict[str, Any]:
    """Get one container by GTM-XXXX, numeric ID, alias, or path."""
    target = _target(container=container, account=account)
    return _client().get_container(target.container_path)


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
def get_container_snippet(
    container: str | None = None,
    account: str | None = None,
) -> dict[str, Any]:
    """Get the web install snippet for a container."""
    target = _target(container=container, account=account)
    snippet = _client().get_container_snippet(target.container_path)
    snippet["target"] = target.to_dict()
    return snippet


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
def resolve_target(
    container: str | None = None,
    account: str | None = None,
    workspace: str | None = None,
) -> dict[str, Any]:
    """Resolve a site alias, GTM-XXXX, or IDs into account/container/workspace paths."""
    return _target(container=container, account=account, workspace=workspace).to_dict()


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
def list_workspaces(
    container: str | None = None,
    account: str | None = None,
) -> dict[str, Any]:
    """List workspaces in a container."""
    target = _target(container=container, account=account)
    workspaces = _client().list_workspaces(target.container_path)
    return {
        "target": target.to_dict(),
        "workspaces": workspaces,
        "count": len(workspaces),
    }


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
def get_workspace_status(
    container: str | None = None,
    account: str | None = None,
    workspace: str | None = None,
) -> dict[str, Any]:
    """Show unpublished workspace changes and sync conflicts."""
    target = _target(container=container, account=account, workspace=workspace)
    status = _client().get_workspace_status(target.workspace_path)
    return {"target": target.to_dict(), "status": status}


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
def list_tags(
    container: str | None = None,
    account: str | None = None,
    workspace: str | None = None,
    compact: bool = True,
) -> dict[str, Any]:
    """List tags in a workspace. compact=true returns a short inventory."""
    target = _target(container=container, account=account, workspace=workspace)
    tags = _client().list_tags(target.workspace_path)
    return {
        "target": target.to_dict(),
        "tags": _maybe_compact(tags, compact, "tag"),
        "count": len(tags),
    }


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
def get_tag(
    tag_id: str,
    container: str | None = None,
    account: str | None = None,
    workspace: str | None = None,
) -> dict[str, Any]:
    """Get one tag by tagId or full path."""
    target = _target(container=container, account=account, workspace=workspace)
    return _client().get_tag(_entity_path(target, "tag", tag_id))


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
def list_triggers(
    container: str | None = None,
    account: str | None = None,
    workspace: str | None = None,
    compact: bool = True,
) -> dict[str, Any]:
    """List triggers in a workspace."""
    target = _target(container=container, account=account, workspace=workspace)
    triggers = _client().list_triggers(target.workspace_path)
    return {
        "target": target.to_dict(),
        "triggers": _maybe_compact(triggers, compact, "trigger"),
        "count": len(triggers),
    }


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
def get_trigger(
    trigger_id: str,
    container: str | None = None,
    account: str | None = None,
    workspace: str | None = None,
) -> dict[str, Any]:
    """Get one trigger by triggerId or full path."""
    target = _target(container=container, account=account, workspace=workspace)
    return _client().get_trigger(_entity_path(target, "trigger", trigger_id))


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
def list_variables(
    container: str | None = None,
    account: str | None = None,
    workspace: str | None = None,
    compact: bool = True,
) -> dict[str, Any]:
    """List user-defined variables in a workspace."""
    target = _target(container=container, account=account, workspace=workspace)
    variables = _client().list_variables(target.workspace_path)
    return {
        "target": target.to_dict(),
        "variables": _maybe_compact(variables, compact, "variable"),
        "count": len(variables),
    }


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
def get_variable(
    variable_id: str,
    container: str | None = None,
    account: str | None = None,
    workspace: str | None = None,
) -> dict[str, Any]:
    """Get one user-defined variable by variableId or full path."""
    target = _target(container=container, account=account, workspace=workspace)
    return _client().get_variable(_entity_path(target, "variable", variable_id))


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
def list_built_in_variables(
    container: str | None = None,
    account: str | None = None,
    workspace: str | None = None,
) -> dict[str, Any]:
    """List enabled built-in variables."""
    target = _target(container=container, account=account, workspace=workspace)
    items = _client().list_built_in_variables(target.workspace_path)
    return {"target": target.to_dict(), "builtInVariables": items, "count": len(items)}


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
def list_folders(
    container: str | None = None,
    account: str | None = None,
    workspace: str | None = None,
) -> dict[str, Any]:
    """List folders in a workspace."""
    target = _target(container=container, account=account, workspace=workspace)
    folders = _client().list_folders(target.workspace_path)
    return {"target": target.to_dict(), "folders": folders, "count": len(folders)}


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
def search_workspace(
    query: str,
    container: str | None = None,
    account: str | None = None,
    workspace: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Search tags, triggers, and variables by name, type, or notes."""
    if not query.strip():
        raise ValueError("query 不能为空。")
    if not 1 <= limit <= 200:
        raise ValueError("limit 必须在 1 到 200 之间。")
    target = _target(container=container, account=account, workspace=workspace)
    client = _client()
    needle = query.casefold()

    def matches(item: dict[str, Any]) -> bool:
        haystack = " ".join(
            str(item.get(field, ""))
            for field in ("name", "type", "notes", "tagId", "triggerId", "variableId")
        ).casefold()
        return needle in haystack

    tags = [_compact_tag(item) for item in client.list_tags(target.workspace_path) if matches(item)]
    triggers = [
        _compact_trigger(item)
        for item in client.list_triggers(target.workspace_path)
        if matches(item)
    ]
    variables = [
        _compact_variable(item)
        for item in client.list_variables(target.workspace_path)
        if matches(item)
    ]
    return {
        "target": target.to_dict(),
        "query": query,
        "tags": tags[:limit],
        "triggers": triggers[:limit],
        "variables": variables[:limit],
        "counts": {
            "tags": len(tags),
            "triggers": len(triggers),
            "variables": len(variables),
        },
        "truncated_at": limit,
    }


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
def audit_container(
    container: str | None = None,
    account: str | None = None,
    workspace: str | None = None,
) -> dict[str, Any]:
    """Summarize a container: counts, tag types, paused tags, unpublished changes, live version."""
    target = _target(container=container, account=account, workspace=workspace)
    client = _client()
    tags = client.list_tags(target.workspace_path)
    triggers = client.list_triggers(target.workspace_path)
    variables = client.list_variables(target.workspace_path)
    status = client.get_workspace_status(target.workspace_path)
    try:
        live = client.get_live_version(target.container_path)
    except Exception as exc:  # noqa: BLE001
        live = {"unavailable": str(exc)}

    type_counts: dict[str, int] = {}
    paused = []
    for tag in tags:
        tag_type = str(tag.get("type") or "unknown")
        type_counts[tag_type] = type_counts.get(tag_type, 0) + 1
        if tag.get("paused"):
            paused.append(_compact_tag(tag))

    workspace_entities = status.get("workspaceChange") or status.get("workspaceChanges") or []
    conflicts = status.get("syncStatus") or status.get("mergeConflict") or {}
    return {
        "target": target.to_dict(),
        "counts": {
            "tags": len(tags),
            "triggers": len(triggers),
            "variables": len(variables),
            "paused_tags": len(paused),
        },
        "tag_types": dict(sorted(type_counts.items())),
        "paused_tags": paused,
        "has_ga4_config": any(tag.get("type") in {"gaawc", "googtag"} for tag in tags),
        "has_ga4_event": any(tag.get("type") == "gaawe" for tag in tags),
        "has_custom_html": any(tag.get("type") == "html" for tag in tags),
        "workspace_status": status,
        "unpublished_change_count": len(workspace_entities) if isinstance(workspace_entities, list) else None,
        "sync_or_conflict": conflicts,
        "live_version": {
            "name": live.get("name") if isinstance(live, dict) else None,
            "containerVersionId": live.get("containerVersionId") if isinstance(live, dict) else None,
            "path": live.get("path") if isinstance(live, dict) else None,
            "raw": live if isinstance(live, dict) and live.get("unavailable") else None,
        },
    }


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
def list_versions(
    container: str | None = None,
    account: str | None = None,
) -> dict[str, Any]:
    """List container version headers."""
    target = _target(container=container, account=account)
    headers = _client().list_version_headers(target.container_path)
    return {
        "target": target.to_dict(),
        "versions": headers,
        "count": len(headers),
    }


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
def get_version(
    version_id: str,
    container: str | None = None,
    account: str | None = None,
) -> dict[str, Any]:
    """Get one container version by versionId or full path."""
    target = _target(container=container, account=account)
    return _client().get_version(_entity_path(target, "version", version_id))


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
def get_live_version(
    container: str | None = None,
    account: str | None = None,
) -> dict[str, Any]:
    """Get the currently published live container version."""
    target = _target(container=container, account=account)
    version = _client().get_live_version(target.container_path)
    return {"target": target.to_dict(), "version": version}


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    }
)
def create_tag(
    name: str,
    container: str | None = None,
    account: str | None = None,
    workspace: str | None = None,
    tag_type: str | None = None,
    preset: TagPreset = "none",
    measurement_id: str | None = None,
    event_name: str | None = None,
    html: str | None = None,
    image_url: str | None = None,
    send_page_view: bool = True,
    event_parameters: dict[str, str] | None = None,
    parameters: list[dict[str, Any]] | None = None,
    firing_trigger_ids: list[str] | None = None,
    blocking_trigger_ids: list[str] | None = None,
    notes: str | None = None,
    paused: bool = False,
    confirm: bool = False,
) -> dict[str, Any]:
    """Preview or create a tag. Use preset for GA4, Google tag, HTML, or image.

    Changes GTM only when confirm=true. Always preview first.
    """
    _ensure_writable()
    target = _target(container=container, account=account, workspace=workspace)
    body = build_tag_body(
        name=name,
        tag_type=tag_type,
        preset=preset,
        measurement_id=measurement_id,
        event_name=event_name,
        html=html,
        image_url=image_url,
        send_page_view=send_page_view,
        event_parameters=event_parameters,
        parameters=parameters,
        firing_trigger_ids=firing_trigger_ids,
        blocking_trigger_ids=blocking_trigger_ids,
        notes=notes,
        paused=paused,
    )
    blocked = _preview_or_apply(
        confirm,
        "create_tag",
        {"target": target.to_dict(), "tag": body},
    )
    if blocked:
        return blocked
    created = _client().create_tag(target.workspace_path, body)
    return {"applied": True, "action": "create_tag", "tag": created}


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
def update_tag(
    tag_id: str,
    container: str | None = None,
    account: str | None = None,
    workspace: str | None = None,
    name: str | None = None,
    paused: bool | None = None,
    notes: str | None = None,
    firing_trigger_ids: list[str] | None = None,
    blocking_trigger_ids: list[str] | None = None,
    parameters: list[dict[str, Any]] | None = None,
    confirm: bool = False,
) -> dict[str, Any]:
    """Preview or update an existing tag. Fetches the current tag, then applies field changes."""
    _ensure_writable()
    target = _target(container=container, account=account, workspace=workspace)
    path = _entity_path(target, "tag", tag_id)
    current = _client().get_tag(path)
    proposed = dict(current)
    changes: dict[str, Any] = {}
    if name is not None:
        changes["name"] = name.strip()
        proposed["name"] = name.strip()
    if paused is not None:
        changes["paused"] = paused
        proposed["paused"] = paused
    if notes is not None:
        changes["notes"] = notes
        proposed["notes"] = notes
    if firing_trigger_ids is not None:
        changes["firingTriggerId"] = firing_trigger_ids
        proposed["firingTriggerId"] = firing_trigger_ids
    if blocking_trigger_ids is not None:
        changes["blockingTriggerId"] = blocking_trigger_ids
        proposed["blockingTriggerId"] = blocking_trigger_ids
    if parameters is not None:
        changes["parameter"] = parameters
        proposed["parameter"] = parameters
    if not changes:
        raise ValueError("至少提供一个要修改的字段。")
    blocked = _preview_or_apply(
        confirm,
        "update_tag",
        {"target": target.to_dict(), "path": path, "changes": changes},
    )
    if blocked:
        return blocked
    updated = _client().update_tag(path, proposed, fingerprint=current.get("fingerprint"))
    return {"applied": True, "action": "update_tag", "tag": updated}


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    }
)
def delete_tag(
    tag_id: str,
    container: str | None = None,
    account: str | None = None,
    workspace: str | None = None,
    confirm: bool = False,
) -> dict[str, Any]:
    """Preview or delete a tag. Deletion only happens when confirm=true."""
    _ensure_writable()
    target = _target(container=container, account=account, workspace=workspace)
    path = _entity_path(target, "tag", tag_id)
    current = _client().get_tag(path)
    blocked = _preview_or_apply(
        confirm,
        "delete_tag",
        {"target": target.to_dict(), "tag": _compact_tag(current), "warning": "删除后无法从 API 撤销。"},
    )
    if blocked:
        return blocked
    return {"applied": True, "action": "delete_tag", **_client().delete_tag(path)}


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    }
)
def create_trigger(
    name: str,
    container: str | None = None,
    account: str | None = None,
    workspace: str | None = None,
    trigger_type: str | None = None,
    preset: TriggerPreset = "none",
    event_name: str | None = None,
    filter_variable: str | None = None,
    filter_value: str | None = None,
    filter_match: str = "contains",
    filters: list[dict[str, Any]] | None = None,
    custom_event_filters: list[dict[str, Any]] | None = None,
    notes: str | None = None,
    confirm: bool = False,
) -> dict[str, Any]:
    """Preview or create a trigger. Use preset for pageview, click, form, or custom event."""
    _ensure_writable()
    target = _target(container=container, account=account, workspace=workspace)
    body = build_trigger_body(
        name=name,
        trigger_type=trigger_type,
        preset=preset,
        event_name=event_name,
        filter_variable=filter_variable,
        filter_value=filter_value,
        filter_match=filter_match,
        filters=filters,
        custom_event_filters=custom_event_filters,
        notes=notes,
    )
    blocked = _preview_or_apply(
        confirm,
        "create_trigger",
        {"target": target.to_dict(), "trigger": body},
    )
    if blocked:
        return blocked
    created = _client().create_trigger(target.workspace_path, body)
    return {"applied": True, "action": "create_trigger", "trigger": created}


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
def update_trigger(
    trigger_id: str,
    container: str | None = None,
    account: str | None = None,
    workspace: str | None = None,
    name: str | None = None,
    notes: str | None = None,
    filters: list[dict[str, Any]] | None = None,
    custom_event_filters: list[dict[str, Any]] | None = None,
    confirm: bool = False,
) -> dict[str, Any]:
    """Preview or update an existing trigger."""
    _ensure_writable()
    target = _target(container=container, account=account, workspace=workspace)
    path = _entity_path(target, "trigger", trigger_id)
    current = _client().get_trigger(path)
    proposed = dict(current)
    changes: dict[str, Any] = {}
    if name is not None:
        changes["name"] = name.strip()
        proposed["name"] = name.strip()
    if notes is not None:
        changes["notes"] = notes
        proposed["notes"] = notes
    if filters is not None:
        changes["filter"] = filters
        proposed["filter"] = filters
    if custom_event_filters is not None:
        changes["customEventFilter"] = custom_event_filters
        proposed["customEventFilter"] = custom_event_filters
    if not changes:
        raise ValueError("至少提供一个要修改的字段。")
    blocked = _preview_or_apply(
        confirm,
        "update_trigger",
        {"target": target.to_dict(), "path": path, "changes": changes},
    )
    if blocked:
        return blocked
    updated = _client().update_trigger(path, proposed, fingerprint=current.get("fingerprint"))
    return {"applied": True, "action": "update_trigger", "trigger": updated}


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    }
)
def delete_trigger(
    trigger_id: str,
    container: str | None = None,
    account: str | None = None,
    workspace: str | None = None,
    confirm: bool = False,
) -> dict[str, Any]:
    """Preview or delete a trigger."""
    _ensure_writable()
    target = _target(container=container, account=account, workspace=workspace)
    path = _entity_path(target, "trigger", trigger_id)
    current = _client().get_trigger(path)
    blocked = _preview_or_apply(
        confirm,
        "delete_trigger",
        {"target": target.to_dict(), "trigger": _compact_trigger(current)},
    )
    if blocked:
        return blocked
    return {"applied": True, "action": "delete_trigger", **_client().delete_trigger(path)}


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    }
)
def create_variable(
    name: str,
    container: str | None = None,
    account: str | None = None,
    workspace: str | None = None,
    variable_type: str | None = None,
    preset: VariablePreset = "none",
    value: str | None = None,
    data_layer_key: str | None = None,
    javascript: str | None = None,
    parameters: list[dict[str, Any]] | None = None,
    notes: str | None = None,
    confirm: bool = False,
) -> dict[str, Any]:
    """Preview or create a variable. Use preset for constant, data layer, or custom JS."""
    _ensure_writable()
    target = _target(container=container, account=account, workspace=workspace)
    body = build_variable_body(
        name=name,
        variable_type=variable_type,
        preset=preset,
        value=value,
        data_layer_key=data_layer_key,
        javascript=javascript,
        parameters=parameters,
        notes=notes,
    )
    blocked = _preview_or_apply(
        confirm,
        "create_variable",
        {"target": target.to_dict(), "variable": body},
    )
    if blocked:
        return blocked
    created = _client().create_variable(target.workspace_path, body)
    return {"applied": True, "action": "create_variable", "variable": created}


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
def update_variable(
    variable_id: str,
    container: str | None = None,
    account: str | None = None,
    workspace: str | None = None,
    name: str | None = None,
    notes: str | None = None,
    parameters: list[dict[str, Any]] | None = None,
    confirm: bool = False,
) -> dict[str, Any]:
    """Preview or update an existing variable."""
    _ensure_writable()
    target = _target(container=container, account=account, workspace=workspace)
    path = _entity_path(target, "variable", variable_id)
    current = _client().get_variable(path)
    proposed = dict(current)
    changes: dict[str, Any] = {}
    if name is not None:
        changes["name"] = name.strip()
        proposed["name"] = name.strip()
    if notes is not None:
        changes["notes"] = notes
        proposed["notes"] = notes
    if parameters is not None:
        changes["parameter"] = parameters
        proposed["parameter"] = parameters
    if not changes:
        raise ValueError("至少提供一个要修改的字段。")
    blocked = _preview_or_apply(
        confirm,
        "update_variable",
        {"target": target.to_dict(), "path": path, "changes": changes},
    )
    if blocked:
        return blocked
    updated = _client().update_variable(path, proposed, fingerprint=current.get("fingerprint"))
    return {"applied": True, "action": "update_variable", "variable": updated}


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    }
)
def delete_variable(
    variable_id: str,
    container: str | None = None,
    account: str | None = None,
    workspace: str | None = None,
    confirm: bool = False,
) -> dict[str, Any]:
    """Preview or delete a user-defined variable."""
    _ensure_writable()
    target = _target(container=container, account=account, workspace=workspace)
    path = _entity_path(target, "variable", variable_id)
    current = _client().get_variable(path)
    blocked = _preview_or_apply(
        confirm,
        "delete_variable",
        {"target": target.to_dict(), "variable": _compact_variable(current)},
    )
    if blocked:
        return blocked
    return {"applied": True, "action": "delete_variable", **_client().delete_variable(path)}


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
def enable_built_in_variables(
    types: list[str],
    container: str | None = None,
    account: str | None = None,
    workspace: str | None = None,
    confirm: bool = False,
) -> dict[str, Any]:
    """Preview or enable built-in variables such as clickId, clickText, pageUrl."""
    _ensure_writable()
    if not types:
        raise ValueError("types 不能为空。")
    target = _target(container=container, account=account, workspace=workspace)
    blocked = _preview_or_apply(
        confirm,
        "enable_built_in_variables",
        {"target": target.to_dict(), "types": types},
    )
    if blocked:
        return blocked
    result = _client().enable_built_in_variables(target.workspace_path, types)
    return {"applied": True, "action": "enable_built_in_variables", "result": result}


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    }
)
def create_workspace(
    name: str,
    container: str | None = None,
    account: str | None = None,
    description: str = "",
    confirm: bool = False,
) -> dict[str, Any]:
    """Preview or create a workspace. Use a dedicated workspace for risky edits."""
    _ensure_writable()
    if not name.strip():
        raise ValueError("workspace name 不能为空。")
    target = _target(container=container, account=account)
    body = {"name": name.strip()}
    if description:
        body["description"] = description
    blocked = _preview_or_apply(
        confirm,
        "create_workspace",
        {"target": target.to_dict(), "workspace": body},
    )
    if blocked:
        return blocked
    created = _client().create_workspace(target.container_path, body)
    return {"applied": True, "action": "create_workspace", "workspace": created}


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    }
)
def create_version(
    name: str,
    container: str | None = None,
    account: str | None = None,
    workspace: str | None = None,
    notes: str = "",
    confirm: bool = False,
) -> dict[str, Any]:
    """Preview or create a container version from the workspace.

    This deletes the current workspace after snapshotting it and creates a
    replacement workspace. It does not publish to live.
    """
    _ensure_writable()
    if not name.strip():
        raise ValueError("version name 不能为空。")
    target = _target(container=container, account=account, workspace=workspace)
    blocked = _preview_or_apply(
        confirm,
        "create_version",
        {
            "target": target.to_dict(),
            "version": {"name": name.strip(), "notes": notes},
            "warning": (
                "create_version 会把当前 workspace 做成版本并删除该 workspace，"
                "然后生成新的 workspace。这不会发布到线上。"
            ),
        },
    )
    if blocked:
        return blocked
    result = _client().create_version(target.workspace_path, name.strip(), notes)
    return {"applied": True, "action": "create_version", "result": result}


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    }
)
def publish_version(
    version_id: str,
    container: str | None = None,
    account: str | None = None,
    confirm: bool = False,
) -> dict[str, Any]:
    """Preview or publish a container version to live. Live traffic changes only when confirm=true."""
    _ensure_writable()
    target = _target(container=container, account=account)
    path = _entity_path(target, "version", version_id)
    current = _client().get_version(path)
    blocked = _preview_or_apply(
        confirm,
        "publish_version",
        {
            "target": target.to_dict(),
            "version": {
                "path": current.get("path"),
                "name": current.get("name"),
                "containerVersionId": current.get("containerVersionId"),
                "description": current.get("description") or current.get("notes"),
            },
            "warning": "发布后网站会立即使用该版本。请确认这就是要上线的版本。",
        },
    )
    if blocked:
        return blocked
    result = _client().publish_version(path)
    return {"applied": True, "action": "publish_version", "result": result}


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
