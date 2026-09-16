from __future__ import annotations

from typing import Any

from ..auth import credentials_for
from ..models import Action, ActionResult
from ..roles import ga_role, role_is_at_least
from .base import Provider


DATA_RESTRICTION_ROLES = {
    "predefinedRoles/noCostMetrics",
    "predefinedRoles/noRevenueMetrics",
}


class Ga4Provider(Provider):
    name = "ga"

    def _client(self, *, write: bool = False):
        from google.analytics.admin_v1alpha import AnalyticsAdminServiceClient

        return AnalyticsAdminServiceClient(credentials=credentials_for(self.settings, "ga", write=write))

    def list_account_ids(self) -> list[str]:
        """Return every GA account visible to the dedicated read credential."""
        rows: list[str] = []
        for summary in self._client(write=False).list_account_summaries():
            account = str(getattr(summary, "account", "") or "").strip()
            if not account:
                raise RuntimeError("Analytics Admin API returned an account summary without an account resource name")
            rows.append(account)
        return rows

    def doctor(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "product": "ga",
            "read": False,
            "write": False,
            "accounts": 0,
            "properties": 0,
        }
        try:
            client = self._client(write=False)
            summaries = list(client.list_account_summaries())
            result["read"] = True
            result["accounts"] = len(summaries)
            result["properties"] = sum(len(item.property_summaries) for item in summaries)
        except Exception as exc:
            result["error"] = str(exc)
            result["next_step"] = "确认 GMP_GA_CREDENTIALS 指向的服务账号已加入 GA4，并启用 Analytics Admin API"
            return result
        primary = next(
            (
                brand.ga_account or brand.ga_primary
                for brand in self.settings.catalog.brands.values()
                if brand.ga_account or brand.ga_primary
            ),
            "",
        )
        if not primary:
            result["next_step"] = "catalog.yaml 里没有 GA account/property"
            return result
        try:
            write_client = self._client(write=True)
            list(write_client.list_access_bindings(parent=primary))
            result["acl_read"] = True
            result["write_candidate"] = True
            result["write_unverified"] = True
            result["write_check"] = f"组织身份可读取 {primary} 的 AccessBindings；本次未做远端 mutation"
            result["write_identity"] = "GMP_ORG_CREDENTIALS or administrator OAuth"
            result["organization_role_evidence"] = self.settings.catalog.gmp_org_declared_roles
            result["next_step"] = (
                "人员管理服务账号的 GMP User Admin 证据与 AccessBindings 读取均已识别；"
                "实际 create/update/delete 只会在确认后的单次 plan 中尝试并写后校验"
            )
        except Exception as exc:
            result["write_error"] = str(exc)
            result["next_step"] = (
                "当前凭证不能管理 GA 用户。把服务账号升级为 Administrator，"
                "或运行 gmp auth login 用管理员 Google 账号授权"
            )
        return result

    def list_bindings(self, parent: str) -> list[dict[str, Any]]:
        client = self._client(write=True)
        rows = []
        for binding in client.list_access_bindings(parent=parent):
            rows.append(
                {
                    "name": binding.name,
                    "user": getattr(binding, "user", ""),
                    "roles": list(binding.roles),
                    "parent": parent,
                }
            )
        return rows

    def who(self, email: str) -> list[dict[str, Any]]:
        needle = email.casefold()
        found: list[dict[str, Any]] = []
        seen: set[str] = set()
        for brand in self.settings.catalog.brands.values():
            parents = [brand.ga_account] if brand.ga_account else []
            parents.extend(item.id for item in brand.ga_properties)
            for parent in parents:
                if parent in seen:
                    continue
                seen.add(parent)
                try:
                    for row in self.list_bindings(parent):
                        if str(row.get("user", "")).casefold() == needle:
                            found.append({"brand": brand.key, **row})
                except Exception as exc:
                    found.append({"brand": brand.key, "parent": parent, "error": str(exc)})
        return found

    def apply(self, action: Action, *, execute: bool) -> ActionResult:
        role = ga_role(action.role or "analyst")
        parent = action.resource_id
        if not execute:
            return self.planned(
                action,
                f"将 {action.email} 在 {parent} 设为 {role}"
                if action.op != "revoke"
                else f"将 {action.email} 从 {parent} 移除",
                "确认整个不可变 plan 后再用 gmp apply 执行",
            )
        mutation_started = False
        try:
            client = self._client(write=True)
            existing = next(
                (
                    item
                    for item in client.list_access_bindings(parent=parent)
                    if str(getattr(item, "user", "")).casefold() == action.email.casefold()
                ),
                None,
            )
            if action.op == "revoke":
                if not existing:
                    return ActionResult(action, "skipped", False, f"{action.email} 不在 {parent}")
                mutation_started = True
                client.delete_access_binding(name=existing.name)
                if self._find_binding(client, parent, action.email):
                    return ActionResult(
                        action,
                        "unknown",
                        False,
                        f"GA API 返回删除成功，但写后校验仍找到 {action.email}",
                        next_step="稍后运行 gmp who 复核；不要重复授予",
                    )
                return ActionResult(
                    action,
                    "ok",
                    False,
                    f"已从 {parent} 移除 {action.email}",
                    data={"binding": existing.name, "verified": True},
                )
            from google.analytics.admin_v1alpha.types import AccessBinding
            from google.protobuf.field_mask_pb2 import FieldMask

            if existing:
                current_roles = list(existing.roles)
                if action.op == "grant" and any(
                    self._role_at_least(current, role) for current in current_roles
                ):
                    return ActionResult(
                        action,
                        "skipped",
                        False,
                        f"{action.email} 在 {parent} 已有同级或更高权限；grant 不会降权",
                        data={"roles": current_roles},
                    )
                if action.op == "set_role":
                    restrictions = [
                        current
                        for current in current_roles
                        if current in DATA_RESTRICTION_ROLES
                    ]
                    desired_roles = [role, *restrictions]
                else:
                    desired_roles = [*current_roles, role]
                desired_roles = list(dict.fromkeys(desired_roles))
                if set(current_roles) == set(desired_roles):
                    return ActionResult(action, "skipped", False, f"{parent} 已是目标角色")
                existing.roles[:] = desired_roles
                mutation_started = True
                client.update_access_binding(access_binding=existing, update_mask=FieldMask(paths=["roles"]))
                verified = self._find_binding(client, parent, action.email)
                verified_roles = list(verified.roles) if verified else []
                if not verified or set(verified_roles) != set(desired_roles):
                    return ActionResult(
                        action,
                        "unknown",
                        False,
                        f"GA 角色更新后的校验不一致：{parent}",
                        next_step="运行 gmp who 复核该用户",
                    )
                return ActionResult(
                    action,
                    "ok",
                    False,
                    f"已把 {parent} 角色更新为 {', '.join(desired_roles)}",
                    data={"binding": existing.name, "roles": verified_roles, "verified": True},
                )
            mutation_started = True
            created = client.create_access_binding(
                parent=parent,
                access_binding=AccessBinding(user=action.email, roles=[role]),
            )
            verified = self._find_binding(client, parent, action.email)
            if not verified or role not in list(verified.roles):
                return ActionResult(
                    action,
                    "unknown",
                    False,
                    f"GA API 已创建 binding，但写后校验失败：{parent}",
                    next_step="运行 gmp who 复核该用户",
                )
            return ActionResult(
                action,
                "ok",
                False,
                f"已把 {action.email} 加入 {parent}",
                data={"binding": created.name, "roles": list(verified.roles), "verified": True},
            )
        except Exception as exc:
            if mutation_started:
                return ActionResult(
                    action,
                    "unknown",
                    False,
                    f"GA 远端写入已经开始，但最终状态无法验证：{exc}",
                    next_step="先运行 gmp who 及 GA Access Management 只读复核；不要重放旧计划",
                )
            return self.blocked(
                action,
                str(exc),
                "把服务账号或 OAuth 用户升级为该 Property/Account 的 Administrator，再重试",
                execute=execute,
            )

    @staticmethod
    def _role_at_least(current: str, requested: str) -> bool:
        try:
            return role_is_at_least("ga", current, requested)
        except Exception:
            return False

    @staticmethod
    def _find_binding(client: Any, parent: str, email: str) -> Any | None:
        needle = email.casefold()
        return next(
            (
                item
                for item in client.list_access_bindings(parent=parent)
                if str(getattr(item, "user", "")).casefold() == needle
            ),
            None,
        )
