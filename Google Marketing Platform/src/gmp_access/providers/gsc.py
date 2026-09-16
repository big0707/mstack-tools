from __future__ import annotations

from urllib.parse import quote
from typing import Any

from ..auth import credentials_for
from ..models import Action, ActionResult
from ..roles import gsc_role
from .base import Provider


class GscProvider(Provider):
    name = "gsc"

    def _service(self):
        from googleapiclient.discovery import build

        creds = credentials_for(self.settings, "gsc", write=False)
        return build("webmasters", "v3", credentials=creds, cache_discovery=False)

    def users_url(self, site: str) -> str:
        return f"https://search.google.com/search-console/users?resource_id={quote(site, safe='')}"

    def doctor(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "product": "gsc",
            "read": False,
            "write": False,
            "sites": 0,
            "user_api": False,
            "note": "Search Console 没有公开的 Full/Restricted 用户 ACL API；CLI-only 模式只能生成手动项",
        }
        try:
            sites = self._service().sites().list().execute().get("siteEntry", [])
            result["read"] = True
            result["sites"] = len(sites)
            result["site_urls"] = [item.get("siteUrl") for item in sites]
        except Exception as exc:
            result["error"] = str(exc)
            result["next_step"] = "确认 GMP_GSC_CREDENTIALS 指向 SEO-Agent 的 gsc-key.json，且该账号已被加为站点用户"
            return result
        result["next_step"] = (
            "GSC 权限变更会随统一 plan 返回 manual_required；由现有 Owner 按 users_url 手动完成"
        )
        return result

    def list_sites(self) -> list[dict[str, Any]]:
        return self._service().sites().list().execute().get("siteEntry", [])

    def who(self, email: str) -> list[dict[str, Any]]:
        return [
            {
                "email": email,
                "error": "Search Console 没有列出其他用户的官方 API",
                "next_step": "由现有 Owner 在 Search Console 的 Users and permissions 中核对",
            }
        ]

    def apply(self, action: Action, *, execute: bool) -> ActionResult:
        site = action.resource_id
        url = self.users_url(site)
        action.details["users_url"] = url
        role = gsc_role(action.role or "restricted")
        if role == "owner":
            return self.blocked(
                action,
                "拒绝自动授予 Search Console Owner",
                "Owner 只能在 Search Console 界面由现有 Owner 手动添加",
                execute=execute,
            )
        if not execute:
            if action.op == "grant":
                message = (
                    f"至少授予 {action.email} on {site} as {role}；"
                    "若已有更高权限则保持不变"
                )
            elif action.op == "set_role":
                message = f"精确设定 {action.email} on {site} as {role}"
            else:
                message = f"撤销 {action.email} on {site} 的访问"
            return ActionResult(
                action,
                "planned",
                True,
                message,
                next_step="确认整个 plan 后，GSC 仍会标为 manual_required；公开 API 不支持该 ACL 变更",
                data={"users_url": url, "method": "manual", "public_user_api": False},
            )
        if action.op == "revoke":
            verb = "移除"
        elif action.op == "set_role":
            verb = f"精确设为 {role}"
        else:
            verb = f"至少授予 {role}（已有更高权限时不得降级）"
        return ActionResult(
            action,
            "manual_required",
            False,
            f"未自动修改 GSC：需要由现有 Owner 在 {site} {verb} {action.email}",
            next_step=f"手动打开 {url} 完成后，再由第二人复核",
            data={"users_url": url, "method": "manual", "public_user_api": False},
        )
