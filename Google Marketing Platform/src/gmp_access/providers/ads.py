from __future__ import annotations

from typing import Any

from ..auth import (
    ADS_PERSONNEL_SERVICE_ACCOUNT,
    ads_service_account_email,
    load_ads_client,
)
from ..errors import MutationStateUnknownError
from ..models import Action, ActionResult
from ..roles import ads_role, role_is_at_least
from .base import Provider


class AdsProvider(Provider):
    name = "ads"

    def _client(self):
        return load_ads_client(self.settings)

    def _service(self, client: Any, name: str):
        version = self.settings.ads_api_version
        return client.get_service(name, version=version) if version and version != "latest" else client.get_service(name)

    def _type(self, client: Any, name: str):
        version = self.settings.ads_api_version
        return client.get_type(name, version=version) if version and version != "latest" else client.get_type(name)

    def doctor(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "product": "ads",
            "read": False,
            "write": False,
            "api_version": self.settings.ads_api_version,
            "customers": [],
            "credential_mode": "service_account",
            "credential_email": ads_service_account_email(self.settings),
            "expected_credential_email": ADS_PERSONNEL_SERVICE_ACCOUNT,
            "write_check_scope": "mcc_only",
            "child_write_verified": False,
        }
        try:
            client = self._client()
            service = self._service(client, "CustomerService")
            names = list(service.list_accessible_customers().resource_names)
            result["read"] = True
            result["accessible"] = names
            result["customers"] = self.list_customer_tree(self.settings.ads_login_customer_id)
        except Exception as exc:
            result["error"] = str(exc)
            result["next_step"] = (
                "确认 GMP_ADS_CREDENTIALS 是专用人员管理服务账号密钥，"
                "GMP_ADS_YAML 仅提供 developer token，且 API 版本可用"
            )
            return result
        mcc = self.settings.ads_login_customer_id.replace("-", "")
        try:
            users = self.list_users(mcc)
            result["mcc_users"] = len(users)
            identity = result["credential_email"]
            identity_row = next(
                (item for item in users if identity and item["email"].casefold() == identity.casefold()),
                None,
            )
            result["credential_role"] = identity_row["role"] if identity_row else "unknown_or_inherited"
            result["write"] = bool(identity_row and identity_row["role"] == "ADMIN")
            result["write_note"] = "仅检查当前服务账号在 MCC 的 ADMIN 角色；未执行 mutation，子账号写权限尚未验证"
            if not result["write"]:
                result["next_step"] = (
                    "当前专用服务账号未被确认是 MCC ADMIN。请给人员管理服务账号授予 MCC ADMIN；"
                    "本项目不会回退到投放账号或用户 OAuth"
                )
        except Exception as exc:
            result["write_error"] = str(exc)
            result["next_step"] = "能列账号但不能列用户时，检查凭据的 Ads Access and security 权限"
        return result

    def list_customer_tree(self, customer_id: str) -> list[dict[str, Any]]:
        client = self._client()
        service = self._service(client, "GoogleAdsService")
        rows: list[dict[str, Any]] = []
        query = (
            "SELECT customer_client.client_customer, customer_client.descriptive_name, "
            "customer_client.manager, customer_client.level, customer_client.status "
            "FROM customer_client WHERE customer_client.level <= 1"
        )
        for row in service.search(customer_id=customer_id.replace("-", ""), query=query):
            item = row.customer_client
            rows.append(
                {
                    "customer_id": str(item.client_customer).split("/")[-1],
                    "name": item.descriptive_name,
                    "manager": bool(item.manager),
                    "level": int(item.level),
                    "status": item.status.name,
                }
            )
        return rows

    def list_users(self, customer_id: str) -> list[dict[str, Any]]:
        client = self._client()
        service = self._service(client, "GoogleAdsService")
        rows: list[dict[str, Any]] = []
        for row in service.search(
            customer_id=customer_id.replace("-", ""),
            query=(
                "SELECT customer_user_access.resource_name, customer_user_access.user_id, "
                "customer_user_access.email_address, customer_user_access.access_role "
                "FROM customer_user_access"
            ),
        ):
            item = row.customer_user_access
            rows.append(
                {
                    "resource_name": item.resource_name,
                    "user_id": item.user_id,
                    "email": item.email_address,
                    "role": item.access_role.name,
                    "customer_id": customer_id.replace("-", ""),
                    "access_source": "direct",
                }
            )
        return rows

    def list_invitations(self, customer_id: str) -> list[dict[str, Any]]:
        client = self._client()
        service = self._service(client, "GoogleAdsService")
        rows: list[dict[str, Any]] = []
        for row in service.search(
            customer_id=customer_id.replace("-", ""),
            query=(
                "SELECT customer_user_access_invitation.resource_name, "
                "customer_user_access_invitation.email_address, "
                "customer_user_access_invitation.access_role, "
                "customer_user_access_invitation.invitation_status "
                "FROM customer_user_access_invitation"
            ),
        ):
            item = row.customer_user_access_invitation
            rows.append(
                {
                    "resource_name": item.resource_name,
                    "email": item.email_address,
                    "role": item.access_role.name,
                    "status": item.invitation_status.name,
                    "customer_id": customer_id.replace("-", ""),
                }
            )
        return rows

    def who(self, email: str) -> list[dict[str, Any]]:
        needle = email.casefold()
        found: list[dict[str, Any]] = []
        customer_ids = [self.settings.ads_login_customer_id]
        for brand in self.settings.catalog.brands.values():
            customer_ids.extend(item.id for item in brand.ads_customers)
        seen: set[str] = set()
        for customer_id in customer_ids:
            normalized = customer_id.replace("-", "")
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            try:
                for row in self.list_users(normalized):
                    if str(row.get("email", "")).casefold() == needle:
                        found.append(row)
                for row in self.list_invitations(normalized):
                    if str(row.get("email", "")).casefold() == needle:
                        found.append({"invitation": True, **row})
            except Exception as exc:
                found.append({"customer_id": normalized, "error": str(exc)})
        return found

    def apply_many(self, actions: list[Action], *, execute: bool) -> list[ActionResult]:
        ordered = sorted(
            actions,
            key=lambda action: 0 if action.details.get("scope") == "mcc" else 1,
        )
        return [self.apply(action, execute=execute) for action in ordered]

    def apply(self, action: Action, *, execute: bool) -> ActionResult:
        customer_id = action.resource_id.replace("-", "")
        role = ads_role(action.role or "READ_ONLY")
        if not execute:
            if action.op == "revoke":
                message = f"撤销 {action.email} @ Ads {customer_id}（含待接受邀请）"
            elif action.op == "set_role":
                message = f"精确设置 {action.email} @ Ads {customer_id} 为 {role}"
            else:
                message = f"至少授予 {action.email} @ Ads {customer_id} {role}；不会降权"
            return self.planned(action, message, "确认整个不可变 plan 后再执行；新用户仍需接受邮件邀请")
        try:
            existing = self._find_user(customer_id, action.email)
            invitations = self._find_invitations(customer_id, action.email)
            inherited = self._mcc_access_for(customer_id, action.email)
            client = self._client()
            if inherited:
                inherited_role = inherited["role"]
                if action.op == "revoke":
                    return self.blocked(
                        action,
                        f"该用户仍通过 MCC 继承 {inherited_role}；删除子账号直接权限不会撤销有效访问。",
                        "先撤销或调整 MCC 权限；离职请使用完整 offboard 计划",
                        execute=True,
                    )
                if action.op == "grant" and self._at_least(inherited_role, role):
                    return ActionResult(
                        action,
                        "skipped",
                        False,
                        f"{action.email} 已通过 MCC 继承 {inherited_role}；grant 不会创建更低的直接权限",
                        data={"access_source": "inherited_mcc", "role": inherited_role},
                    )
                if (
                    action.op == "set_role"
                    and inherited_role != role
                    and self._at_least(inherited_role, role)
                ):
                    return self.blocked(
                        action,
                        f"MCC 继承的 {inherited_role} 高于目标角色，子账号 set-role 无法降级有效权限。",
                        "先单独调整 MCC 权限，再设置子账号直接权限",
                        execute=True,
                    )
                if action.op == "set_role" and inherited_role == role and not existing:
                    return self._keep_inherited_exact_role(
                        client,
                        action,
                        customer_id,
                        invitations,
                        inherited_role,
                    )
            if action.op == "revoke":
                return self._revoke(client, action, customer_id, existing, invitations, inherited)
            if existing:
                result = self._update_existing(client, action, customer_id, existing, role)
                if action.op == "set_role" and result.status in {"ok", "skipped"}:
                    return self._finish_existing_set_role(
                        client,
                        action,
                        customer_id,
                        invitations,
                        result,
                    )
                return result
            return self._ensure_invitation(client, action, customer_id, invitations, role)
        except MutationStateUnknownError as exc:
            return ActionResult(
                action,
                "unknown",
                False,
                str(exc),
                next_step="先运行 gmp who 及 Google Ads Access and security 只读复核；不要重放旧计划",
            )
        except Exception as exc:
            return self.blocked(
                action,
                str(exc),
                "授权账号必须是目标 Ads customer 的 ADMIN；修复后重新生成并确认新 plan",
                execute=True,
            )

    def _find_user(self, customer_id: str, email: str) -> dict[str, Any] | None:
        needle = email.casefold()
        return next((item for item in self.list_users(customer_id) if item["email"].casefold() == needle), None)

    def _find_invitations(self, customer_id: str, email: str) -> list[dict[str, Any]]:
        needle = email.casefold()
        return [item for item in self.list_invitations(customer_id) if item["email"].casefold() == needle]

    def _mcc_access_for(self, customer_id: str, email: str) -> dict[str, Any] | None:
        mcc = self.settings.ads_login_customer_id.replace("-", "")
        if not mcc or customer_id == mcc:
            return None
        return self._find_user(mcc, email)

    def _revoke(
        self,
        client: Any,
        action: Action,
        customer_id: str,
        existing: dict[str, Any] | None,
        invitations: list[dict[str, Any]],
        inherited: dict[str, Any] | None,
    ) -> ActionResult:
        if existing and existing["role"] == "ADMIN":
            admins = [item for item in self.list_users(customer_id) if item["role"] == "ADMIN"]
            if len(admins) <= 1:
                return self.blocked(
                    action,
                    "拒绝删除该 Ads customer 的最后一位直接 ADMIN。",
                    "先新增并验证另一位 Admin，再重新生成 offboard plan",
                    execute=True,
                )
        removed: list[str] = []
        mutation_started = False
        try:
            if existing:
                service = self._service(client, "CustomerUserAccessService")
                operation = self._type(client, "CustomerUserAccessOperation")
                operation.remove = existing["resource_name"]
                mutation_started = True
                service.mutate_customer_user_access(customer_id=customer_id, operation=operation)
                removed.append("active_access")
            invitation_service = self._service(client, "CustomerUserAccessInvitationService")
            for invitation in invitations:
                if invitation.get("status") != "PENDING":
                    continue
                operation = self._type(client, "CustomerUserAccessInvitationOperation")
                operation.remove = invitation["resource_name"]
                mutation_started = True
                invitation_service.mutate_customer_user_access_invitation(
                    customer_id=customer_id,
                    operation=operation,
                )
                removed.append("pending_invitation")
        except Exception as exc:
            if mutation_started:
                raise MutationStateUnknownError(
                    f"Ads 撤权已经开始，但最终状态无法验证：{exc}"
                ) from exc
            raise
        if not removed:
            if inherited:
                return self.blocked(
                    action,
                    f"没有子账号直接权限，但仍通过 MCC 继承 {inherited['role']}。",
                    "撤销或调整 MCC 权限；仅改子账号不能消除有效访问",
                    execute=True,
                )
            return ActionResult(action, "skipped", False, f"{action.email} 在 Ads {customer_id} 无直接权限或待处理邀请")
        try:
            still_active = self._find_user(customer_id, action.email)
            still_pending = any(
                item.get("status") == "PENDING"
                for item in self._find_invitations(customer_id, action.email)
            )
        except Exception as exc:
            raise MutationStateUnknownError(
                f"Ads 撤权已提交，但写后读取失败：{exc}"
            ) from exc
        if still_active or still_pending:
            return ActionResult(
                action,
                "unknown",
                False,
                "Ads 撤权后的写后校验失败",
                next_step="运行 gmp who 复核该邮箱",
            )
        return ActionResult(
            action,
            "ok",
            False,
            f"已从 Ads {customer_id} 移除 {action.email} 的直接权限和待接受邀请",
            data={"removed": removed, "verified": True},
        )

    def _update_existing(
        self,
        client: Any,
        action: Action,
        customer_id: str,
        existing: dict[str, Any],
        role: str,
    ) -> ActionResult:
        if action.op == "grant" and self._at_least(existing["role"], role):
            return ActionResult(
                action,
                "skipped",
                False,
                f"已有同级或更高 Ads 权限（{existing['role']}）；grant 不会降权",
                data={"role": existing["role"], "access_source": "direct"},
            )
        if existing["role"] == role:
            return ActionResult(action, "skipped", False, f"Ads {customer_id} 已是 {role}")
        if action.op == "set_role" and existing["role"] == "ADMIN" and role != "ADMIN":
            admins = [item for item in self.list_users(customer_id) if item["role"] == "ADMIN"]
            if len(admins) <= 1:
                return self.blocked(
                    action,
                    "拒绝降级该 Ads customer 的最后一位直接 ADMIN。",
                    "先新增并验证另一位 Admin，再重新生成 set-role plan",
                    execute=True,
                )
        service = self._service(client, "CustomerUserAccessService")
        operation = self._type(client, "CustomerUserAccessOperation")
        operation.update.resource_name = existing["resource_name"]
        operation.update.access_role = getattr(client.enums.AccessRoleEnum, role)
        operation.update_mask.paths.append("access_role")
        try:
            service.mutate_customer_user_access(customer_id=customer_id, operation=operation)
            verified = self._find_user(customer_id, action.email)
        except Exception as exc:
            raise MutationStateUnknownError(
                f"Ads 角色写入已经开始，但最终状态无法验证：{exc}"
            ) from exc
        if not verified or verified["role"] != role:
            return ActionResult(
                action,
                "unknown",
                False,
                "Ads 角色更新后的写后校验失败",
                next_step="运行 gmp who 复核该邮箱",
            )
        return ActionResult(
            action,
            "ok",
            False,
            f"已把 Ads {customer_id} 角色设为 {role}",
            data={"role": role, "verified": True},
        )

    def _finish_existing_set_role(
        self,
        client: Any,
        action: Action,
        customer_id: str,
        invitations: list[dict[str, Any]],
        role_result: ActionResult,
    ) -> ActionResult:
        removed = self._remove_pending_invitations(client, customer_id, invitations)
        try:
            remaining = [
                item
                for item in self._find_invitations(customer_id, action.email)
                if item.get("status") == "PENDING"
            ]
        except Exception as exc:
            if removed or role_result.status == "ok":
                raise MutationStateUnknownError(
                    f"Ads 精确改权已提交，但邀请状态无法验证：{exc}"
                ) from exc
            raise
        if remaining:
            return ActionResult(
                action,
                "unknown",
                False,
                "Ads 精确改权后仍存在待接受邀请",
                next_step="运行 gmp who 复核并清理待处理邀请",
            )
        if not removed:
            return role_result
        data = dict(role_result.data or {})
        data.update({"removed_pending_invitations": removed, "verified": True})
        return ActionResult(
            action,
            "ok",
            False,
            f"{role_result.message}；并清除了 {len(removed)} 个待接受邀请",
            data=data,
        )

    def _keep_inherited_exact_role(
        self,
        client: Any,
        action: Action,
        customer_id: str,
        invitations: list[dict[str, Any]],
        inherited_role: str,
    ) -> ActionResult:
        removed = self._remove_pending_invitations(client, customer_id, invitations)
        try:
            remaining = [
                item
                for item in self._find_invitations(customer_id, action.email)
                if item.get("status") == "PENDING"
            ]
        except Exception as exc:
            if removed:
                raise MutationStateUnknownError(
                    f"Ads 邀请清理已提交，但最终状态无法验证：{exc}"
                ) from exc
            raise
        if remaining:
            return ActionResult(
                action,
                "unknown",
                False,
                "MCC 角色已符合目标，但子账号待接受邀请清理校验失败",
                next_step="运行 gmp who 复核待处理邀请",
            )
        status = "ok" if removed else "skipped"
        message = f"MCC 继承权限已使有效角色精确为 {inherited_role}"
        if removed:
            message += f"；已清除 {len(removed)} 个冗余或冲突邀请"
        return ActionResult(
            action,
            status,
            False,
            message,
            data={
                "access_source": "inherited_mcc",
                "role": inherited_role,
                "removed_pending_invitations": removed,
                "verified": True,
            },
        )

    def _remove_pending_invitations(
        self,
        client: Any,
        customer_id: str,
        invitations: list[dict[str, Any]],
    ) -> list[str]:
        removed: list[str] = []
        service = self._service(client, "CustomerUserAccessInvitationService")
        for invitation in invitations:
            if invitation.get("status") != "PENDING":
                continue
            operation = self._type(client, "CustomerUserAccessInvitationOperation")
            operation.remove = invitation["resource_name"]
            try:
                service.mutate_customer_user_access_invitation(
                    customer_id=customer_id,
                    operation=operation,
                )
            except Exception as exc:
                raise MutationStateUnknownError(
                    f"Ads 邀请清理已经开始，但最终状态无法验证：{exc}"
                ) from exc
            removed.append(invitation["resource_name"])
        return removed

    def _ensure_invitation(
        self,
        client: Any,
        action: Action,
        customer_id: str,
        invitations: list[dict[str, Any]],
        role: str,
    ) -> ActionResult:
        pending = [item for item in invitations if item.get("status") == "PENDING"]
        same_or_higher = next(
            (
                item
                for item in pending
                if item["role"] == role
                or (action.op == "grant" and self._at_least(item["role"], role))
            ),
            None,
        )
        if same_or_higher:
            return ActionResult(
                action,
                "pending_acceptance",
                False,
                f"Ads {customer_id} 已有待接受邀请（{same_or_higher['role']}），未重复发送",
                next_step=f"请 {action.email} 接受 Google Ads 邀请邮件",
                data={"resource_name": same_or_higher["resource_name"], "verified": True},
            )
        service = self._service(client, "CustomerUserAccessInvitationService")
        mutation_started = False
        try:
            for invitation in pending:
                operation = self._type(client, "CustomerUserAccessInvitationOperation")
                operation.remove = invitation["resource_name"]
                mutation_started = True
                service.mutate_customer_user_access_invitation(customer_id=customer_id, operation=operation)
            operation = self._type(client, "CustomerUserAccessInvitationOperation")
            operation.create.email_address = action.email
            operation.create.access_role = getattr(client.enums.AccessRoleEnum, role)
            mutation_started = True
            response = service.mutate_customer_user_access_invitation(customer_id=customer_id, operation=operation)
            verified = next(
                (
                    item
                    for item in self._find_invitations(customer_id, action.email)
                    if item.get("status") == "PENDING" and item.get("role") == role
                ),
                None,
            )
        except Exception as exc:
            if mutation_started:
                raise MutationStateUnknownError(
                    f"Ads 邀请变更已经开始，但最终状态无法验证：{exc}"
                ) from exc
            raise
        if not verified:
            return ActionResult(
                action,
                "unknown",
                False,
                "Ads 邀请发送后未能写后校验",
                next_step="检查 Google Ads Access and security，再运行 gmp who",
            )
        return ActionResult(
            action,
            "pending_acceptance",
            False,
            f"已向 {action.email} 发送 Ads {customer_id} 的 {role} 邀请",
            next_step="收件人必须接受邮件邀请后权限才生效",
            data={"resource_name": response.result.resource_name, "verified": True},
        )

    @staticmethod
    def _at_least(current: str, requested: str) -> bool:
        try:
            return role_is_at_least("ads", current, requested)
        except Exception:
            return False
