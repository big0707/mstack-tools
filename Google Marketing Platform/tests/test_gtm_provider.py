from __future__ import annotations

import copy
import unittest
from typing import Any, Callable
from unittest.mock import patch

from gmp_access.models import Action
from gmp_access.providers.gtm import GtmProvider


ACCOUNT_ID = "123456"
EMAIL = "colleague@example.com"


class FakeRequest:
    def __init__(self, callback: Callable[[], Any]) -> None:
        self.callback = callback

    def execute(self) -> Any:
        return self.callback()


class FakeUserPermissions:
    def __init__(
        self,
        permission: dict[str, Any] | None,
        *,
        apply_updates: bool = True,
        apply_deletes: bool = True,
        update_transform: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> None:
        self.permission = copy.deepcopy(permission)
        self.apply_updates = apply_updates
        self.apply_deletes = apply_deletes
        self.update_transform = update_transform
        self.update_calls: list[dict[str, Any]] = []
        self.delete_calls: list[str] = []
        self.create_calls: list[dict[str, Any]] = []

    def list(self, *, parent: str, pageToken: str | None = None) -> FakeRequest:
        del parent, pageToken

        def response() -> dict[str, Any]:
            rows = [copy.deepcopy(self.permission)] if self.permission else []
            return {"userPermission": rows}

        return FakeRequest(response)

    def update(self, *, path: str, body: dict[str, Any]) -> FakeRequest:
        captured = {"path": path, "body": copy.deepcopy(body)}
        self.update_calls.append(captured)

        def response() -> dict[str, Any]:
            if self.apply_updates:
                updated = self.update_transform(body) if self.update_transform else body
                self.permission = copy.deepcopy(updated)
            return copy.deepcopy(body)

        return FakeRequest(response)

    def delete(self, *, path: str) -> FakeRequest:
        self.delete_calls.append(path)

        def response() -> dict[str, Any]:
            if self.apply_deletes:
                self.permission = None
            return {}

        return FakeRequest(response)

    def create(self, *, parent: str, body: dict[str, Any]) -> FakeRequest:
        captured = {"parent": parent, "body": copy.deepcopy(body)}
        self.create_calls.append(captured)

        def response() -> dict[str, Any]:
            created = copy.deepcopy(body)
            created.setdefault("path", f"{parent}/user_permissions/fake")
            created.setdefault("accountId", parent.rsplit("/", 1)[-1])
            self.permission = created
            return copy.deepcopy(created)

        return FakeRequest(response)


class FakeAccounts:
    def __init__(self, user_permissions: FakeUserPermissions) -> None:
        self._user_permissions = user_permissions

    def user_permissions(self) -> FakeUserPermissions:
        return self._user_permissions


class FakeService:
    def __init__(self, user_permissions: FakeUserPermissions) -> None:
        self._accounts = FakeAccounts(user_permissions)

    def accounts(self) -> FakeAccounts:
        return self._accounts


def permission(
    container_access: dict[str, str],
    *,
    account_permission: str = "user",
) -> dict[str, Any]:
    return {
        "path": f"accounts/{ACCOUNT_ID}/user_permissions/42",
        "accountId": ACCOUNT_ID,
        "emailAddress": EMAIL,
        "accountAccess": {"permission": account_permission},
        "containerAccess": [
            {"containerId": container_id, "permission": role}
            for container_id, role in container_access.items()
        ],
    }


def action(
    op: str,
    *,
    container_id: str = "1001",
    role: str | None = None,
    account_wide_revoke: bool = False,
) -> Action:
    details: dict[str, Any] = {
        "account_id": ACCOUNT_ID,
        "public_id": f"GTM-{container_id}",
    }
    if account_wide_revoke:
        details["account_wide_revoke"] = True
        resource_id = f"accounts/{ACCOUNT_ID}"
        resource_name = "Test GTM account"
    else:
        details["container_id"] = container_id
        resource_id = f"GTM-{container_id}"
        resource_name = f"Test container {container_id}"
    return Action(
        product="gtm",
        op=op,  # type: ignore[arg-type]
        email=EMAIL,
        brand="test",
        resource_id=resource_id,
        resource_name=resource_name,
        role=role,
        details=details,
    )


def access_map(user_permissions: FakeUserPermissions) -> dict[str, str]:
    current = user_permissions.permission or {}
    return {
        str(item["containerId"]): str(item["permission"])
        for item in current.get("containerAccess") or []
    }


class GtmProviderRegressionTests(unittest.TestCase):
    def run_action(
        self,
        target: Action,
        initial: dict[str, Any] | None,
        *,
        apply_updates: bool = True,
        apply_deletes: bool = True,
        update_transform: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> tuple[Any, FakeUserPermissions]:
        user_permissions = FakeUserPermissions(
            initial,
            apply_updates=apply_updates,
            apply_deletes=apply_deletes,
            update_transform=update_transform,
        )
        service = FakeService(user_permissions)
        provider = GtmProvider(settings=object())  # type: ignore[arg-type]
        with patch.object(provider, "_service", return_value=service):
            result = provider.apply(target, execute=True)
        return result, user_permissions

    def test_grant_lower_role_does_not_downgrade_publish(self) -> None:
        result, api = self.run_action(
            action("grant", role="read"),
            permission({"1001": "publish"}),
        )

        self.assertEqual(result.status, "skipped")
        self.assertIn("不会降权", result.message)
        self.assertEqual(access_map(api), {"1001": "publish"})
        self.assertEqual(api.update_calls, [])

    def test_account_admin_grant_does_not_create_redundant_container_access(self) -> None:
        result, api = self.run_action(
            action("grant", role="publish"),
            permission({"2002": "read"}, account_permission="admin"),
        )

        self.assertEqual(result.status, "skipped")
        self.assertIn("Account Admin", result.message)
        self.assertEqual(access_map(api), {"2002": "read"})
        self.assertEqual(api.update_calls, [])

    def test_target_container_update_preserves_other_container_access(self) -> None:
        result, api = self.run_action(
            action("set_role", role="publish"),
            permission({"1001": "read", "2002": "approve"}),
        )

        self.assertEqual(result.status, "ok")
        self.assertEqual(
            access_map(api),
            {"1001": "publish", "2002": "approve"},
        )
        self.assertEqual(len(api.update_calls), 1)
        self.assertTrue(result.data and result.data["verified"])

    def test_container_revoke_only_removes_target_and_preserves_other(self) -> None:
        result, api = self.run_action(
            action("revoke"),
            permission({"1001": "publish", "2002": "edit"}),
        )

        self.assertEqual(result.status, "ok")
        self.assertEqual(access_map(api), {"2002": "edit"})
        self.assertEqual(len(api.update_calls), 1)
        self.assertEqual(api.delete_calls, [])
        self.assertEqual(result.data, {"verified": True, "preserved_container_count": 1})

    def test_account_admin_container_revoke_is_blocked(self) -> None:
        result, api = self.run_action(
            action("revoke"),
            permission({"1001": "publish", "2002": "read"}, account_permission="admin"),
        )

        self.assertEqual(result.status, "blocked")
        self.assertIn("Account Admin", result.message)
        self.assertEqual(api.update_calls, [])
        self.assertEqual(api.delete_calls, [])
        self.assertEqual(access_map(api), {"1001": "publish", "2002": "read"})

    def test_account_wide_revoke_deletes_entire_user_permission(self) -> None:
        result, api = self.run_action(
            action("revoke", account_wide_revoke=True),
            permission({"1001": "publish", "2002": "edit"}, account_permission="admin"),
        )

        self.assertEqual(result.status, "ok")
        self.assertIsNone(api.permission)
        self.assertEqual(api.delete_calls, [f"accounts/{ACCOUNT_ID}/user_permissions/42"])
        self.assertEqual(result.data, {"verified": True, "scope": "account"})

    def test_update_reports_error_when_write_after_verification_mismatches(self) -> None:
        result, api = self.run_action(
            action("set_role", role="publish"),
            permission({"1001": "read", "2002": "edit"}),
            apply_updates=False,
        )

        self.assertEqual(len(api.update_calls), 1)
        self.assertEqual(result.status, "unknown")
        self.assertIn("校验不一致", result.message)
        self.assertEqual(access_map(api), {"1001": "read", "2002": "edit"})

    def test_update_reports_unknown_if_unrelated_container_is_dropped(self) -> None:
        def drop_other(body: dict[str, Any]) -> dict[str, Any]:
            changed = copy.deepcopy(body)
            changed["containerAccess"] = [
                item for item in changed["containerAccess"] if item["containerId"] != "2002"
            ]
            return changed

        result, _ = self.run_action(
            action("set_role", role="publish"),
            permission({"1001": "read", "2002": "approve"}),
            update_transform=drop_other,
        )

        self.assertEqual(result.status, "unknown")
        self.assertIn("完整校验", result.message)

    def test_revoke_reports_unknown_if_preserved_container_changes(self) -> None:
        def alter_other(body: dict[str, Any]) -> dict[str, Any]:
            changed = copy.deepcopy(body)
            changed["containerAccess"][0]["permission"] = "read"
            return changed

        result, _ = self.run_action(
            action("revoke"),
            permission({"1001": "publish", "2002": "approve"}),
            update_transform=alter_other,
        )

        self.assertEqual(result.status, "unknown")
        self.assertIn("完整校验", result.message)


if __name__ == "__main__":
    unittest.main()
