from __future__ import annotations

from collections import defaultdict
from typing import Any

from ..auth import credentials_for, load_oauth_credentials, oauth_identity_email, service_account_email
from ..errors import MutationStateUnknownError
from ..models import Action, ActionResult
from ..roles import gtm_account_role, gtm_container_role, role_is_at_least
from .base import Provider


class GtmProvider(Provider):
    name = "gtm"

    def _service(self, *, write: bool = False):
        from googleapiclient.discovery import build

        scopes = (
            (
                "https://www.googleapis.com/auth/tagmanager.manage.users",
                "https://www.googleapis.com/auth/tagmanager.readonly",
            )
            if write
            else ("https://www.googleapis.com/auth/tagmanager.readonly",)
        )
        creds = credentials_for(self.settings, "gtm", write=write)
        if hasattr(creds, "with_scopes"):
            try:
                creds = creds.with_scopes(list(scopes))
            except Exception:
                pass
        return build("tagmanager", "v2", credentials=creds, cache_discovery=False)

    @staticmethod
    def _paginate(method: Any, item_key: str, **kwargs: Any) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            request_kwargs = dict(kwargs)
            if page_token:
                request_kwargs["pageToken"] = page_token
            response = method(**request_kwargs).execute()
            rows.extend(response.get(item_key, []))
            page_token = response.get("nextPageToken")
            if not page_token:
                return rows

    def _accounts(self, service: Any) -> list[dict[str, Any]]:
        return self._paginate(service.accounts().list, "account")

    def _permissions(self, service: Any, account_id: str) -> list[dict[str, Any]]:
        return self._paginate(
            service.accounts().user_permissions().list,
            "userPermission",
            parent=f"accounts/{account_id}",
        )

    def doctor(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "product": "gtm",
            "read": False,
            "write": False,
            "accounts": 0,
            "credential_source": "../GTM MCP (preferred) or GMP_GTM_CREDENTIALS",
        }
        try:
            accounts = self._accounts(self._service(write=False))
            result["read"] = True
            result["accounts"] = len(accounts)
            result["account_names"] = [item.get("name") for item in accounts]
        except Exception as exc:
            result["error"] = str(exc)
            result["next_step"] = (
                "先运行 ../GTM MCP/.venv/Scripts/gtm-mcp.exe doctor；"
                "确认服务账号已加入 GTM 且 Tag Manager API 已启用"
            )
            return result
        if not accounts:
            result["next_step"] = "凭据能调用 API，但看不到任何 GTM account"
            return result
        account_id = str(accounts[0].get("accountId") or str(accounts[0].get("path", "")).split("/")[-1])
        try:
            permissions = self._permissions(self._service(write=True), account_id)
            oauth = load_oauth_credentials(
                self.settings,
                refresh=False,
                persist_refresh=False,
            )
            if oauth:
                try:
                    identity = oauth_identity_email(self.settings)
                except Exception as exc:
                    identity = None
                    result["identity_error"] = str(exc)
                result["credential_mode"] = "oauth"
            else:
                identity = service_account_email(self.settings.gtm_credentials)
                result["credential_mode"] = "service_account"
            result["credential_email"] = identity
            identity_row = next(
                (
                    item
                    for item in permissions
                    if identity
                    and str(item.get("emailAddress", "")).casefold() == identity.casefold()
                ),
                None,
            )
            account_permission = str(
                ((identity_row or {}).get("accountAccess") or {}).get("permission") or "unknown"
            )
            result["credential_account_permission"] = account_permission
            result["write"] = account_permission == "admin"
            result["acl_read"] = True
            result["organization_role_evidence"] = self.settings.catalog.gmp_org_declared_roles
            if not result["write"] and "User Admin" in result["organization_role_evidence"]:
                result["write_candidate"] = True
                result["write_unverified"] = True
            result["write_check"] = f"可读取 accounts/{account_id} 的 UserPermissions"
            if not result["write"]:
                result["next_step"] = (
                    "当前直接 GTM 角色是 Account User，但已有人工证据显示同一身份是 GMP User Admin。"
                    "公开 API 无法验证组织角色；实际 mutate 只在确认后的单次 plan 中尝试并校验"
                )
        except Exception as exc:
            result["write_error"] = str(exc)
            result["next_step"] = (
                "当前凭据不能管理 GTM 用户。运行 gmp auth login 使用 GTM Account Admin，"
                "或给专用服务账号 Account Admin"
            )
        return result

    def discover(self) -> list[dict[str, Any]]:
        service = self._service(write=False)
        rows: list[dict[str, Any]] = []
        for account in self._accounts(service):
            account_id = str(account.get("accountId") or str(account.get("path", "")).split("/")[-1])
            containers = self._paginate(
                service.accounts().containers().list,
                "container",
                parent=f"accounts/{account_id}",
            )
            rows.append(
                {
                    "account_id": account_id,
                    "name": account.get("name"),
                    "containers": [
                        {
                            "container_id": item.get("containerId"),
                            "public_id": item.get("publicId"),
                            "name": item.get("name"),
                        }
                        for item in containers
                    ],
                }
            )
        return rows

    def who(self, email: str) -> list[dict[str, Any]]:
        needle = email.casefold()
        found: list[dict[str, Any]] = []
        try:
            service = self._service(write=True)
            for account in self._accounts(service):
                account_id = str(account.get("accountId") or str(account.get("path", "")).split("/")[-1])
                for item in self._permissions(service, account_id):
                    if str(item.get("emailAddress", "")).casefold() == needle:
                        found.append({"account": account.get("name"), **item})
        except Exception as exc:
            return [{"error": str(exc), "next_step": "需要 GTM Account Admin 才能列出 UserPermissions"}]
        return found

    def _find_permission(self, service: Any, account_id: str, email: str) -> dict[str, Any] | None:
        needle = email.casefold()
        return next(
            (
                item
                for item in self._permissions(service, account_id)
                if str(item.get("emailAddress", "")).casefold() == needle
            ),
            None,
        )

    def apply(self, action: Action, *, execute: bool) -> ActionResult:
        return self.apply_many([action], execute=execute)[0]

    def apply_many(self, actions: list[Action], *, execute: bool) -> list[ActionResult]:
        if not execute:
            return [self._preview(action) for action in actions]
        resolved, failures = self._resolve_targets(actions)
        if not resolved:
            return failures
        groups: dict[tuple[str, str], list[Action]] = defaultdict(list)
        for action in resolved:
            groups[(action.email.casefold(), str(action.details["account_id"]))].append(action)
        results = list(failures)
        try:
            service = self._service(write=True)
        except Exception as exc:
            results.extend(
                self.blocked(
                    action,
                    str(exc),
                    "运行 gmp auth login，授权账号必须是 GTM Account Admin",
                    execute=True,
                )
                for action in resolved
            )
            return results
        for (_, account_id), group in groups.items():
            try:
                results.extend(self._apply_group(service, account_id, group))
            except MutationStateUnknownError as exc:
                results.extend(
                    ActionResult(
                        action,
                        "unknown",
                        False,
                        str(exc),
                        next_step="先运行 gmp who 及 GTM User Management 只读复核；不要重放旧计划",
                    )
                    for action in group
                )
            except Exception as exc:
                results.extend(
                    self.blocked(
                        action,
                        str(exc),
                        "确认管理员凭据有 tagmanager.manage.users；修复后重新生成并确认新 plan",
                        execute=True,
                    )
                    for action in group
                )
        return results

    def _preview(self, action: Action) -> ActionResult:
        if action.details.get("account_wide_revoke"):
            message = f"从 GTM account {action.details.get('account_id')} 全量移除 {action.email}"
        else:
            verb = "撤销" if action.op == "revoke" else "精确设为" if action.op == "set_role" else "至少授予"
            message = (
                f"{verb} {action.email} @ {action.details.get('public_id') or action.resource_id}"
                + (f" ({action.role})" if action.op != "revoke" else "")
            )
        return self.planned(action, message, "确认整个不可变 plan 后再执行")

    def _resolve_targets(self, actions: list[Action]) -> tuple[list[Action], list[ActionResult]]:
        needs_discovery = any(
            not action.details.get("account_id")
            or (
                not action.details.get("account_wide_revoke")
                and not action.details.get("container_id")
            )
            for action in actions
        )
        lookup: dict[str, tuple[str, str]] = {}
        discovery_error: Exception | None = None
        if needs_discovery:
            try:
                for account in self.discover():
                    for container in account.get("containers") or []:
                        pair = (str(account.get("account_id") or ""), str(container.get("container_id") or ""))
                        for key in (container.get("public_id"), container.get("container_id")):
                            if key:
                                lookup[str(key).casefold()] = pair
            except Exception as exc:
                discovery_error = exc
        resolved: list[Action] = []
        failures: list[ActionResult] = []
        for action in actions:
            account_id = str(action.details.get("account_id") or "")
            container_id = str(action.details.get("container_id") or "")
            if action.details.get("account_wide_revoke") and not account_id:
                account_id = action.resource_id.strip().split("/")[-1] if action.resource_id else ""
            if not account_id or (not action.details.get("account_wide_revoke") and not container_id):
                key = str(action.details.get("public_id") or action.resource_id).casefold()
                discovered = lookup.get(key)
                if discovered:
                    account_id, container_id = discovered
            if not account_id or (not action.details.get("account_wide_revoke") and not container_id):
                failures.append(
                    self.blocked(
                        action,
                        f"无法解析 GTM account/container：{discovery_error or action.resource_id}",
                        "运行 gmp discover --product gtm，并把数字 ID 写入 catalog.yaml",
                        execute=True,
                    )
                )
                continue
            action.details["account_id"] = account_id
            if container_id:
                action.details["container_id"] = container_id
            resolved.append(action)
        return resolved, failures

    def _apply_group(self, service: Any, account_id: str, actions: list[Action]) -> list[ActionResult]:
        existing = self._find_permission(service, account_id, actions[0].email)
        if any(action.details.get("account_wide_revoke") for action in actions):
            return self._remove_account_permission(service, account_id, actions, existing)
        if all(action.op == "revoke" for action in actions):
            return self._revoke_containers(service, account_id, actions, existing)
        if any(action.op == "revoke" for action in actions):
            return [
                self.blocked(
                    action,
                    "同一 GTM account 的计划混合了 grant/set-role/revoke。",
                    "拆成两个计划执行",
                    execute=True,
                )
                for action in actions
            ]
        return self._grant_or_set(service, account_id, actions, existing)

    def _remove_account_permission(
        self,
        service: Any,
        account_id: str,
        actions: list[Action],
        existing: dict[str, Any] | None,
    ) -> list[ActionResult]:
        if not existing:
            return [ActionResult(action, "skipped", False, f"{action.email} 不在 GTM account {account_id}") for action in actions]
        try:
            service.accounts().user_permissions().delete(path=existing["path"]).execute()
            verified = self._find_permission(service, account_id, actions[0].email)
        except Exception as exc:
            raise MutationStateUnknownError(
                f"GTM account 撤权已经开始，但最终状态无法验证：{exc}"
            ) from exc
        if verified:
            return [
                ActionResult(
                    action,
                    "unknown",
                    False,
                    f"GTM 删除后仍能查到 {action.email}",
                    next_step="稍后用 gmp who 复核",
                )
                for action in actions
            ]
        return [
            ActionResult(
                action,
                "ok",
                False,
                f"已从 GTM account {account_id} 全量移除 {action.email}",
                data={"verified": True, "scope": "account"},
            )
            for action in actions
        ]

    def _revoke_containers(
        self,
        service: Any,
        account_id: str,
        actions: list[Action],
        existing: dict[str, Any] | None,
    ) -> list[ActionResult]:
        if not existing:
            return [ActionResult(action, "skipped", False, f"{action.email} 不在 GTM account {account_id}") for action in actions]
        account_permission = str((existing.get("accountAccess") or {}).get("permission") or "user")
        if account_permission == "admin":
            return [
                self.blocked(
                    action,
                    "该用户是 GTM Account Admin，容器级撤权不会降低其有效权限。",
                    "若是离职请用 offboard；否则先单独确认是否降为 account user",
                    execute=True,
                )
                for action in actions
            ]
        target_ids = {str(action.details.get("container_id") or "") for action in actions}
        current = {
            str(item.get("containerId")): str(item.get("permission") or "noAccess")
            for item in existing.get("containerAccess") or []
            if item.get("containerId")
        }
        changed = {container_id for container_id in target_ids if container_id in current}
        if not changed:
            return [ActionResult(action, "skipped", False, "目标 GTM 容器没有直接权限") for action in actions]
        remaining = {key: value for key, value in current.items() if key not in target_ids}
        try:
            if remaining:
                body = self._permission_body(existing, account_id, remaining, account_permission)
                service.accounts().user_permissions().update(path=existing["path"], body=body).execute()
            else:
                service.accounts().user_permissions().delete(path=existing["path"]).execute()
            verified = self._find_permission(service, account_id, actions[0].email)
        except Exception as exc:
            raise MutationStateUnknownError(
                f"GTM 容器撤权已经开始，但最终状态无法验证：{exc}"
            ) from exc
        verified_access = {
            str(item.get("containerId")): str(item.get("permission") or "noAccess")
            for item in (verified or {}).get("containerAccess") or []
            if item.get("containerId")
        }
        verified_account_permission = str(
            ((verified or {}).get("accountAccess") or {}).get("permission") or ""
        )
        preservation_failed = (
            (bool(remaining) and not verified)
            or (not remaining and bool(verified))
            or verified_access != remaining
            or (bool(remaining) and verified_account_permission != account_permission)
        )
        if preservation_failed:
            return [
                ActionResult(
                    action,
                    "unknown",
                    False,
                    "GTM 容器撤权写后完整校验失败；目标或其他容器/账号权限可能不一致",
                    next_step="运行 gmp who 复核",
                )
                for action in actions
            ]
        results: list[ActionResult] = []
        for action in actions:
            container_id = str(action.details.get("container_id") or "")
            if container_id in changed:
                results.append(
                    ActionResult(
                        action,
                        "ok",
                        False,
                        f"已撤销 GTM container {container_id} 的直接权限，并保留其他容器",
                        data={"verified": True, "preserved_container_count": len(remaining)},
                    )
                )
            else:
                results.append(ActionResult(action, "skipped", False, "目标 GTM 容器没有直接权限"))
        return results

    def _grant_or_set(
        self,
        service: Any,
        account_id: str,
        actions: list[Action],
        existing: dict[str, Any] | None,
    ) -> list[ActionResult]:
        account_permission = str((existing or {}).get("accountAccess", {}).get("permission") or "user")
        if account_permission == "admin" and all(action.op == "grant" for action in actions):
            return [
                ActionResult(
                    action,
                    "skipped",
                    False,
                    "已有 GTM Account Admin；grant 不会创建冗余容器权限或降权",
                    data={"role": "admin", "access_source": "account"},
                )
                for action in actions
            ]
        if account_permission == "admin" and any(
            action.op == "set_role" and str(action.role).casefold() != "admin" for action in actions
        ):
            return [
                self.blocked(
                    action,
                    "该用户是 GTM Account Admin；不能用容器级 set-role 隐式降级账号权限。",
                    "明确创建单独的 account-role 变更计划",
                    execute=True,
                )
                for action in actions
            ]
        current = {
            str(item.get("containerId")): str(item.get("permission") or "noAccess")
            for item in (existing or {}).get("containerAccess") or []
            if item.get("containerId")
        }
        desired = dict(current)
        per_action: list[tuple[Action, bool, str]] = []
        make_admin = any(str(action.role).casefold() == "admin" for action in actions)
        if make_admin and account_permission != "admin":
            account_permission = "admin"
        for action in actions:
            requested_raw = str(action.role or "read")
            if requested_raw.casefold() == "admin":
                changed = not existing or str((existing.get("accountAccess") or {}).get("permission")) != "admin"
                per_action.append((action, changed, "account admin"))
                continue
            container_id = str(action.details.get("container_id") or "")
            requested = gtm_container_role(requested_raw)
            current_role = current.get(container_id)
            if action.op == "grant" and current_role and self._at_least(current_role, requested):
                per_action.append((action, False, current_role))
                continue
            if action.op == "set_role" and current_role == requested:
                per_action.append((action, False, current_role))
                continue
            desired[container_id] = requested
            per_action.append((action, True, requested))
        if not any(changed for _, changed, _ in per_action):
            return [
                ActionResult(
                    action,
                    "skipped",
                    False,
                    f"已有同级或更高 GTM 权限（{effective}）；grant 不会降权",
                )
                for action, _, effective in per_action
            ]
        try:
            if existing:
                body = self._permission_body(existing, account_id, desired, account_permission)
                service.accounts().user_permissions().update(path=existing["path"], body=body).execute()
            else:
                body = {
                    "emailAddress": actions[0].email,
                    "accountAccess": {"permission": gtm_account_role("admin" if make_admin else "user")},
                    "containerAccess": [
                        {"containerId": key, "permission": value}
                        for key, value in sorted(desired.items())
                    ],
                }
                service.accounts().user_permissions().create(parent=f"accounts/{account_id}", body=body).execute()
            verified = self._find_permission(service, account_id, actions[0].email)
        except Exception as exc:
            raise MutationStateUnknownError(
                f"GTM 授权写入已经开始，但最终状态无法验证：{exc}"
            ) from exc
        if not verified:
            return [
                ActionResult(action, "unknown", False, "GTM 写入后找不到用户", next_step="运行 gmp who 复核")
                for action in actions
            ]
        verified_access = {
            str(item.get("containerId")): str(item.get("permission") or "noAccess")
            for item in verified.get("containerAccess") or []
            if item.get("containerId")
        }
        verified_account_permission = str(
            (verified.get("accountAccess") or {}).get("permission") or ""
        )
        if verified_access != desired or verified_account_permission != account_permission:
            return [
                ActionResult(
                    action,
                    "unknown",
                    False,
                    "GTM 写入后完整校验不一致；目标或其他容器/账号权限可能被改变",
                    next_step="运行 gmp who 复核",
                )
                for action in actions
            ]
        verified_admin = verified_account_permission == "admin"
        results: list[ActionResult] = []
        for action, changed, effective in per_action:
            if not changed:
                results.append(
                    ActionResult(
                        action,
                        "skipped",
                        False,
                        f"已有同级或更高 GTM 权限（{effective}）；grant 不会降权",
                    )
                )
                continue
            container_id = str(action.details.get("container_id") or "")
            expected_admin = str(action.role).casefold() == "admin"
            expected_role = None if expected_admin else gtm_container_role(str(action.role or "read"))
            if (expected_admin and not verified_admin) or (
                expected_role and verified_access.get(container_id) != expected_role
            ):
                results.append(
                    ActionResult(action, "unknown", False, "GTM 写入后角色校验不一致", next_step="运行 gmp who 复核")
                )
            else:
                results.append(
                    ActionResult(
                        action,
                        "ok",
                        False,
                        f"已更新 GTM 权限：{effective}",
                        data={"verified": True, "preserved_container_count": len(current)},
                    )
                )
        return results

    @staticmethod
    def _permission_body(
        existing: dict[str, Any],
        account_id: str,
        container_access: dict[str, str],
        account_permission: str,
    ) -> dict[str, Any]:
        return {
            "path": existing["path"],
            "accountId": existing.get("accountId", account_id),
            "emailAddress": existing.get("emailAddress"),
            "accountAccess": {"permission": account_permission},
            "containerAccess": [
                {"containerId": key, "permission": value}
                for key, value in sorted(container_access.items())
            ],
        }

    @staticmethod
    def _at_least(current: str, requested: str) -> bool:
        try:
            return role_is_at_least("gtm", current, requested)
        except Exception:
            return False
