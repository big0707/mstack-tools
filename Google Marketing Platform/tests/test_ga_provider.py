from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from gmp_access.models import Action
from gmp_access.providers.ga4 import Ga4Provider


class FakeGaClient:
    def __init__(self, binding=None, *, extra_role_after_update: str | None = None) -> None:
        self.binding = binding
        self.extra_role_after_update = extra_role_after_update
        self.updated = 0
        self.deleted = 0

    def list_access_bindings(self, parent: str):
        return [self.binding] if self.binding else []

    def update_access_binding(self, **kwargs):
        self.binding = kwargs["access_binding"]
        if self.extra_role_after_update:
            self.binding.roles.append(self.extra_role_after_update)
        self.updated += 1
        return self.binding

    def delete_access_binding(self, name: str):
        self.binding = None
        self.deleted += 1

    def create_access_binding(self, *, parent: str, access_binding):
        access_binding.name = f"{parent}/accessBindings/1"
        self.binding = access_binding
        return access_binding


def action(op: str, role: str) -> Action:
    return Action(
        product="ga",
        op=op,
        email="alice@example.com",
        brand="demo",
        resource_id="properties/1",
        resource_name="Property",
        role=role,
    )


class GaProviderTests(unittest.TestCase):
    def test_grant_never_downgrades_existing_admin(self) -> None:
        binding = SimpleNamespace(
            name="properties/1/accessBindings/1",
            user="alice@example.com",
            roles=["predefinedRoles/admin"],
        )
        client = FakeGaClient(binding)
        provider = Ga4Provider(None)  # type: ignore[arg-type]
        with patch.object(provider, "_client", return_value=client):
            result = provider.apply(action("grant", "predefinedRoles/analyst"), execute=True)
        self.assertEqual(result.status, "skipped")
        self.assertEqual(client.updated, 0)
        self.assertEqual(binding.roles, ["predefinedRoles/admin"])

    def test_set_role_is_exact(self) -> None:
        binding = SimpleNamespace(
            name="properties/1/accessBindings/1",
            user="alice@example.com",
            roles=["predefinedRoles/admin", "predefinedRoles/analyst"],
        )
        client = FakeGaClient(binding)
        provider = Ga4Provider(None)  # type: ignore[arg-type]
        with patch.object(provider, "_client", return_value=client):
            result = provider.apply(action("set_role", "predefinedRoles/viewer"), execute=True)
        self.assertEqual(result.status, "ok")
        self.assertEqual(client.updated, 1)
        self.assertEqual(binding.roles, ["predefinedRoles/viewer"])

    def test_set_role_preserves_metric_data_restrictions(self) -> None:
        binding = SimpleNamespace(
            name="properties/1/accessBindings/1",
            user="alice@example.com",
            roles=["predefinedRoles/admin", "predefinedRoles/noRevenueMetrics"],
        )
        client = FakeGaClient(binding)
        provider = Ga4Provider(None)  # type: ignore[arg-type]
        with patch.object(provider, "_client", return_value=client):
            result = provider.apply(action("set_role", "predefinedRoles/viewer"), execute=True)
        self.assertEqual(result.status, "ok")
        self.assertEqual(
            binding.roles,
            ["predefinedRoles/viewer", "predefinedRoles/noRevenueMetrics"],
        )

    def test_set_role_verification_rejects_unexpected_extra_role(self) -> None:
        binding = SimpleNamespace(
            name="properties/1/accessBindings/1",
            user="alice@example.com",
            roles=["predefinedRoles/admin"],
        )
        client = FakeGaClient(
            binding,
            extra_role_after_update="predefinedRoles/noRevenueMetrics",
        )
        provider = Ga4Provider(None)  # type: ignore[arg-type]
        with patch.object(provider, "_client", return_value=client):
            result = provider.apply(action("set_role", "predefinedRoles/viewer"), execute=True)
        self.assertEqual(result.status, "unknown")
        self.assertIn("校验不一致", result.message)

    def test_revoke_verifies_absence(self) -> None:
        binding = SimpleNamespace(
            name="properties/1/accessBindings/1",
            user="alice@example.com",
            roles=["predefinedRoles/viewer"],
        )
        client = FakeGaClient(binding)
        provider = Ga4Provider(None)  # type: ignore[arg-type]
        with patch.object(provider, "_client", return_value=client):
            result = provider.apply(action("revoke", "predefinedRoles/viewer"), execute=True)
        self.assertEqual(result.status, "ok")
        self.assertEqual(client.deleted, 1)


if __name__ == "__main__":
    unittest.main()
