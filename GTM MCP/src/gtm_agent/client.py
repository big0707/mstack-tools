from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from functools import lru_cache
from typing import Any, Callable

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .config import (
    Settings,
    get_settings,
    is_numeric_id,
    is_public_container_id,
    read_service_account_identity,
)


READONLY_SCOPES = ("https://www.googleapis.com/auth/tagmanager.readonly",)
WRITE_SCOPES = (
    "https://www.googleapis.com/auth/tagmanager.readonly",
    "https://www.googleapis.com/auth/tagmanager.edit.containers",
    "https://www.googleapis.com/auth/tagmanager.edit.containerversions",
    "https://www.googleapis.com/auth/tagmanager.publish",
)

COLLECTION_KEYS = {
    "account": "account",
    "container": "container",
    "workspace": "workspace",
    "tag": "tag",
    "trigger": "trigger",
    "variable": "variable",
    "folder": "folder",
    "builtInVariable": "builtInVariable",
    "containerVersionHeader": "containerVersionHeader",
    "environment": "environment",
}


class GtmApiError(RuntimeError):
    def __init__(self, message: str, status: int | None = None, reason: str | None = None):
        super().__init__(message)
        self.status = status
        self.reason = reason

    @classmethod
    def from_http(cls, exc: HttpError) -> "GtmApiError":
        status = int(getattr(exc.resp, "status", 0) or 0)
        reason = ""
        try:
            payload = json.loads(exc.content.decode("utf-8")) if exc.content else {}
            error = payload.get("error", {})
            reason = error.get("message") or error.get("status") or str(exc)
        except (ValueError, UnicodeDecodeError):
            reason = str(exc)
        next_step = _next_step_for_status(status, reason)
        message = f"GTM API 失败 ({status or 'unknown'}): {reason}"
        if next_step:
            message = f"{message} {next_step}"
        return cls(message, status=status, reason=reason)


def _next_step_for_status(status: int, reason: str) -> str:
    lowered = reason.casefold()
    if status in {401, 403} and "tagmanager" in lowered and "has not been used" in lowered:
        return "下一步：在 Google Cloud 项目中启用 Tag Manager API。"
    if status in {401, 403}:
        return (
            "下一步：确认服务账号 JSON 有效，已在 GTM Admin → User Management "
            "加入该 client_email，并授予 Read / Edit / Publish。"
        )
    if status == 404:
        return "下一步：用 list_accounts / list_containers / resolve_target 核对 account、container、workspace 路径。"
    if status == 429:
        return "下一步：稍后重试，并减少一次列出的对象数量。"
    return ""


@dataclass(frozen=True)
class Target:
    account_id: str
    container_id: str
    workspace_id: str
    account_path: str
    container_path: str
    workspace_path: str
    public_id: str
    container_name: str
    workspace_name: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


class GtmClient:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings(require_credentials=True)
        if not self.settings.credentials_path:
            raise RuntimeError("缺少 GOOGLE_APPLICATION_CREDENTIALS。")
        scopes = READONLY_SCOPES if self.settings.read_only else WRITE_SCOPES
        credentials = service_account.Credentials.from_service_account_file(
            self.settings.credentials_path,
            scopes=scopes,
        )
        self.service = build(
            "tagmanager",
            "v2",
            credentials=credentials,
            cache_discovery=False,
        )
        self.identity = read_service_account_identity(self.settings.credentials_path)

    def _execute(self, request: Any) -> dict[str, Any]:
        try:
            return request.execute()
        except HttpError as exc:
            raise GtmApiError.from_http(exc) from exc

    def _paginate(
        self,
        method: Callable[..., Any],
        item_key: str,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            request_kwargs = dict(kwargs)
            if page_token:
                request_kwargs["pageToken"] = page_token
            response = self._execute(method(**request_kwargs))
            items.extend(response.get(item_key, []))
            page_token = response.get("nextPageToken")
            if not page_token:
                return items

    def list_accounts(self) -> list[dict[str, Any]]:
        return self._paginate(self.service.accounts().list, "account")

    def list_containers(self, account: str) -> list[dict[str, Any]]:
        return self._paginate(
            self.service.accounts().containers().list,
            "container",
            parent=_account_path(account),
        )

    def get_container(self, path: str) -> dict[str, Any]:
        return self._execute(self.service.accounts().containers().get(path=path))

    def get_container_snippet(self, path: str) -> dict[str, Any]:
        return self._execute(self.service.accounts().containers().snippet(path=path))

    def list_workspaces(self, container_path: str) -> list[dict[str, Any]]:
        return self._paginate(
            self.service.accounts().containers().workspaces().list,
            "workspace",
            parent=container_path,
        )

    def get_workspace(self, path: str) -> dict[str, Any]:
        return self._execute(self.service.accounts().containers().workspaces().get(path=path))

    def get_workspace_status(self, path: str) -> dict[str, Any]:
        return self._execute(
            self.service.accounts().containers().workspaces().getStatus(path=path)
        )

    def create_workspace(self, container_path: str, body: dict[str, Any]) -> dict[str, Any]:
        return self._execute(
            self.service.accounts().containers().workspaces().create(
                parent=container_path,
                body=body,
            )
        )

    def list_tags(self, workspace_path: str) -> list[dict[str, Any]]:
        return self._paginate(
            self.service.accounts().containers().workspaces().tags().list,
            "tag",
            parent=workspace_path,
        )

    def get_tag(self, path: str) -> dict[str, Any]:
        return self._execute(
            self.service.accounts().containers().workspaces().tags().get(path=path)
        )

    def create_tag(self, workspace_path: str, body: dict[str, Any]) -> dict[str, Any]:
        return self._execute(
            self.service.accounts().containers().workspaces().tags().create(
                parent=workspace_path,
                body=body,
            )
        )

    def update_tag(self, path: str, body: dict[str, Any], fingerprint: str | None = None) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"path": path, "body": body}
        if fingerprint:
            kwargs["fingerprint"] = fingerprint
        return self._execute(
            self.service.accounts().containers().workspaces().tags().update(**kwargs)
        )

    def delete_tag(self, path: str) -> dict[str, Any]:
        self._execute(self.service.accounts().containers().workspaces().tags().delete(path=path))
        return {"deleted": True, "path": path}

    def list_triggers(self, workspace_path: str) -> list[dict[str, Any]]:
        return self._paginate(
            self.service.accounts().containers().workspaces().triggers().list,
            "trigger",
            parent=workspace_path,
        )

    def get_trigger(self, path: str) -> dict[str, Any]:
        return self._execute(
            self.service.accounts().containers().workspaces().triggers().get(path=path)
        )

    def create_trigger(self, workspace_path: str, body: dict[str, Any]) -> dict[str, Any]:
        return self._execute(
            self.service.accounts().containers().workspaces().triggers().create(
                parent=workspace_path,
                body=body,
            )
        )

    def update_trigger(
        self, path: str, body: dict[str, Any], fingerprint: str | None = None
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"path": path, "body": body}
        if fingerprint:
            kwargs["fingerprint"] = fingerprint
        return self._execute(
            self.service.accounts().containers().workspaces().triggers().update(**kwargs)
        )

    def delete_trigger(self, path: str) -> dict[str, Any]:
        self._execute(
            self.service.accounts().containers().workspaces().triggers().delete(path=path)
        )
        return {"deleted": True, "path": path}

    def list_variables(self, workspace_path: str) -> list[dict[str, Any]]:
        return self._paginate(
            self.service.accounts().containers().workspaces().variables().list,
            "variable",
            parent=workspace_path,
        )

    def get_variable(self, path: str) -> dict[str, Any]:
        return self._execute(
            self.service.accounts().containers().workspaces().variables().get(path=path)
        )

    def create_variable(self, workspace_path: str, body: dict[str, Any]) -> dict[str, Any]:
        return self._execute(
            self.service.accounts().containers().workspaces().variables().create(
                parent=workspace_path,
                body=body,
            )
        )

    def update_variable(
        self, path: str, body: dict[str, Any], fingerprint: str | None = None
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"path": path, "body": body}
        if fingerprint:
            kwargs["fingerprint"] = fingerprint
        return self._execute(
            self.service.accounts().containers().workspaces().variables().update(**kwargs)
        )

    def delete_variable(self, path: str) -> dict[str, Any]:
        self._execute(
            self.service.accounts().containers().workspaces().variables().delete(path=path)
        )
        return {"deleted": True, "path": path}

    def list_built_in_variables(self, workspace_path: str) -> list[dict[str, Any]]:
        return self._paginate(
            self.service.accounts().containers().workspaces().built_in_variables().list,
            "builtInVariable",
            parent=workspace_path,
        )

    def enable_built_in_variables(
        self, workspace_path: str, types: list[str]
    ) -> dict[str, Any]:
        return self._execute(
            self.service.accounts().containers().workspaces().built_in_variables().create(
                parent=workspace_path,
                type=types,
            )
        )

    def list_folders(self, workspace_path: str) -> list[dict[str, Any]]:
        return self._paginate(
            self.service.accounts().containers().workspaces().folders().list,
            "folder",
            parent=workspace_path,
        )

    def list_version_headers(self, container_path: str) -> list[dict[str, Any]]:
        return self._paginate(
            self.service.accounts().containers().version_headers().list,
            "containerVersionHeader",
            parent=container_path,
        )

    def get_version(self, path: str) -> dict[str, Any]:
        return self._execute(self.service.accounts().containers().versions().get(path=path))

    def get_live_version(self, container_path: str) -> dict[str, Any]:
        return self._execute(
            self.service.accounts().containers().versions().live(parent=container_path)
        )

    def create_version(self, workspace_path: str, name: str, notes: str = "") -> dict[str, Any]:
        return self._execute(
            self.service.accounts().containers().workspaces().create_version(
                path=workspace_path,
                body={"name": name, "notes": notes},
            )
        )

    def publish_version(self, version_path: str) -> dict[str, Any]:
        return self._execute(
            self.service.accounts().containers().versions().publish(path=version_path)
        )

    def resolve(
        self,
        container: str | None = None,
        account: str | None = None,
        workspace: str | None = None,
    ) -> Target:
        query = self.settings.resolve_container_query(container)
        account_hint = (account or self.settings.account_id or "").strip()
        workspace_hint = (workspace or self.settings.workspace_id or "").strip()

        if query.startswith("accounts/") and "/workspaces/" in query:
            parsed = _parse_workspace_path(query)
            container_obj = self.get_container(parsed["container_path"])
            workspace_obj = self._pick_workspace(parsed["container_path"], parsed["workspace_id"])
            return _target_from_objects(container_obj, workspace_obj)

        if query.startswith("accounts/") and "/containers/" in query:
            container_obj = self.get_container(query)
            workspace_obj = self._pick_workspace(container_obj["path"], workspace_hint)
            return _target_from_objects(container_obj, workspace_obj)

        container_obj = self._find_container(query, account_hint)
        workspace_obj = self._pick_workspace(container_obj["path"], workspace_hint)
        return _target_from_objects(container_obj, workspace_obj)

    def _find_container(self, query: str, account_hint: str) -> dict[str, Any]:
        accounts = (
            [{"path": _account_path(account_hint), "accountId": _bare_id(account_hint)}]
            if account_hint
            else self.list_accounts()
        )
        matches: list[dict[str, Any]] = []
        for item in accounts:
            for container in self.list_containers(item["path"]):
                if _container_matches(container, query):
                    matches.append(container)
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise GtmApiError(
                f"找不到容器 {query}。下一步：先调用 list_accounts 和 list_containers，"
                "确认服务账号已被加入该 GTM 账户，且容器 ID 正确。"
            )
        names = ", ".join(
            f"{item.get('publicId')} ({item.get('path')})" for item in matches
        )
        raise GtmApiError(
            f"容器 {query} 匹配到多个结果：{names}。请同时传入 account。"
        )

    def _pick_workspace(self, container_path: str, workspace_hint: str) -> dict[str, Any]:
        workspaces = self.list_workspaces(container_path)
        if not workspaces:
            raise GtmApiError(f"容器 {container_path} 没有任何 workspace。")
        if workspace_hint:
            for item in workspaces:
                if (
                    item.get("workspaceId") == workspace_hint
                    or item.get("path") == workspace_hint
                    or item.get("name", "").casefold() == workspace_hint.casefold()
                ):
                    return item
            raise GtmApiError(
                f"找不到 workspace {workspace_hint}。可用："
                + ", ".join(f"{item.get('name')} ({item.get('workspaceId')})" for item in workspaces)
            )
        for item in workspaces:
            if item.get("name") == "Default Workspace":
                return item
        return workspaces[0]


def _account_path(value: str) -> str:
    stripped = value.strip()
    if stripped.startswith("accounts/"):
        return "/".join(stripped.split("/")[:2])
    if not is_numeric_id(stripped):
        raise ValueError("account 必须是数字 accountId 或 accounts/{id}。")
    return f"accounts/{stripped}"


def _bare_id(value: str) -> str:
    return value.strip().rstrip("/").split("/")[-1]


def _parse_workspace_path(path: str) -> dict[str, str]:
    parts = path.strip("/").split("/")
    if len(parts) < 6 or parts[0] != "accounts" or parts[2] != "containers":
        raise ValueError(f"无法解析 workspace 路径：{path}")
    container_path = "/".join(parts[:4])
    workspace_id = parts[5] if len(parts) >= 6 and parts[4] == "workspaces" else ""
    return {"container_path": container_path, "workspace_id": workspace_id}


def _container_matches(container: dict[str, Any], query: str) -> bool:
    if container.get("path") == query:
        return True
    if container.get("containerId") == query:
        return True
    if str(container.get("publicId", "")).casefold() == query.casefold():
        return True
    if is_public_container_id(query) or is_numeric_id(query):
        return False
    return str(container.get("name", "")).casefold() == query.casefold()


def _target_from_objects(container: dict[str, Any], workspace: dict[str, Any]) -> Target:
    account_id = container["path"].split("/")[1]
    return Target(
        account_id=account_id,
        container_id=str(container.get("containerId", "")),
        workspace_id=str(workspace.get("workspaceId", "")),
        account_path=f"accounts/{account_id}",
        container_path=container["path"],
        workspace_path=workspace["path"],
        public_id=str(container.get("publicId", "")),
        container_name=str(container.get("name", "")),
        workspace_name=str(workspace.get("name", "")),
    )


@lru_cache(maxsize=1)
def get_client() -> GtmClient:
    return GtmClient()


def reset_client_cache() -> None:
    get_client.cache_clear()
