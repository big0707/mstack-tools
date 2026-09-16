from __future__ import annotations

from typing import Any

from ..auth import service_account_credentials, service_account_email
from ..models import Action, ActionResult
from .base import Provider


GMP_ORG_READ_SCOPE = "https://www.googleapis.com/auth/marketingplatformadmin.analytics.read"


class GmpOrgProvider(Provider):
    """Read-only helper for the public GMP Admin API v1alpha surface.

    The public API manages organizations' Analytics account links and service
    levels.  It intentionally is not an employee ACL provider: Google's public
    discovery document exposes no users, memberships, roles, or permissions
    resource.
    """

    name = "gmp_org"

    def _service(self):
        from googleapiclient.discovery import build

        path = self.settings.gmp_org_credentials
        if not path or not path.is_file():
            raise RuntimeError("找不到 GMP organization service-account credential")
        credentials = service_account_credentials(path, (GMP_ORG_READ_SCOPE,))
        return build(
            "marketingplatformadmin",
            "v1alpha",
            credentials=credentials,
            cache_discovery=False,
        )

    def _evidence(self) -> dict[str, Any]:
        catalog = self.settings.catalog
        return {
            "organization": catalog.gmp_org_resource_name,
            "display_name": catalog.gmp_org_display_name,
            "credential_email": service_account_email(self.settings.gmp_org_credentials),
            "declared_roles": catalog.gmp_org_declared_roles,
            "source": catalog.gmp_org_evidence,
            "verified_by_public_api": False,
        }

    def doctor(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "product": "gmp_org",
            "api_version": "v1alpha",
            "read": False,
            "write": False,
            "personnel_user_api": False,
            "organization_role_api": False,
            "analytics_account_link_api": True,
            "declared_role_evidence": self._evidence(),
            "note": (
                "GMP Org Admin/User Admin/Billing Admin 是真实的组织层角色，但公开 GMP Admin API "
                "没有 users/memberships/roles/permissions endpoint，不能用于员工 ACL 自动化。"
            ),
        }
        try:
            discovery = self.discover()
            result["read"] = True
            result["api_enabled"] = True
            result["service_usage_ready"] = True
            result["organizations"] = discovery["organizations"]
        except Exception as exc:
            message = str(exc)
            result["error"] = message
            if "SERVICE_DISABLED" in message or "has not been used" in message or "is disabled" in message:
                result["api_enabled"] = False
                result["service_usage_ready"] = False
                result["next_step"] = (
                    "如需读取组织与 GA account links，先在凭据项目启用 "
                    "marketingplatformadmin.googleapis.com；这仍不会开放组织用户 ACL API"
                )
            elif "USER_PROJECT_DENIED" in message or "serviceusage.services.use" in message:
                result["api_enabled"] = True
                result["service_usage_ready"] = False
                result["next_step"] = (
                    "给调用身份 quota project 的 Service Usage Consumer 后再读组织；"
                    "这仍不会开放组织用户 ACL API"
                )
            else:
                result["api_enabled"] = "unknown"
                result["service_usage_ready"] = "unknown"
                result["next_step"] = "检查 GMP Admin API 启用状态与只读 scope"
        return result

    def discover(self) -> dict[str, Any]:
        service = self._service()
        organizations = service.organizations().list().execute().get("organizations", [])
        rows: list[dict[str, Any]] = []
        configured = self.settings.catalog.gmp_org_resource_name
        for organization in organizations:
            name = str(organization.get("name") or "")
            links = (
                service.organizations()
                .analyticsAccountLinks()
                .list(parent=name)
                .execute()
                .get("analyticsAccountLinks", [])
            )
            rows.append(
                {
                    "name": name,
                    "display_name": organization.get("displayName"),
                    "configured": bool(configured and name == configured),
                    "analytics_account_links": [
                        {
                            "name": item.get("name"),
                            "analytics_account": item.get("analyticsAccount"),
                        }
                        for item in links
                    ],
                }
            )
        return {
            "organizations": rows,
            "personnel_user_api": False,
            "declared_role_evidence": self._evidence(),
        }

    def who(self, email: str) -> list[dict[str, Any]]:
        return [
            {
                "email": email,
                "error": "公开 GMP Admin API 不能列出组织中的其他用户或角色",
                "declared_role_evidence": self._evidence(),
            }
        ]

    def apply(self, action: Action, *, execute: bool) -> ActionResult:
        return self.blocked(
            action,
            "公开 GMP Admin API 没有人员 ACL endpoint。",
            "员工权限继续使用 GA/GTM/Ads 各产品 API；GSC 为 manual_required",
            execute=execute,
        )
