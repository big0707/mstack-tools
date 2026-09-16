from __future__ import annotations

import json
import os
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable
from unittest.mock import patch

from gmp_access.cli import main
from gmp_access.config import load_settings
from gmp_access.models import Action
from gmp_access.providers.gmp_org import GmpOrgProvider


ORG_NAME = "organizations/YOUR_GMP_ORG_ID"


class FakeRequest:
    def __init__(self, callback: Callable[[], Any]) -> None:
        self.callback = callback

    def execute(self) -> Any:
        return self.callback()


class FakeAnalyticsAccountLinks:
    def __init__(self, links_by_parent: dict[str, list[dict[str, Any]]]) -> None:
        self.links_by_parent = links_by_parent
        self.list_calls: list[str] = []

    def list(self, *, parent: str) -> FakeRequest:
        self.list_calls.append(parent)
        return FakeRequest(
            lambda: {
                "analyticsAccountLinks": self.links_by_parent.get(parent, []),
            }
        )


class FakeOrganizations:
    def __init__(
        self,
        organizations: list[dict[str, Any]],
        links_by_parent: dict[str, list[dict[str, Any]]],
    ) -> None:
        self._organizations = organizations
        self._links = FakeAnalyticsAccountLinks(links_by_parent)
        self.list_calls = 0

    def list(self) -> FakeRequest:
        self.list_calls += 1
        return FakeRequest(lambda: {"organizations": self._organizations})

    def analyticsAccountLinks(self) -> FakeAnalyticsAccountLinks:
        return self._links


class FakeService:
    def __init__(self, organizations: FakeOrganizations) -> None:
        self._organizations = organizations

    def organizations(self) -> FakeOrganizations:
        return self._organizations


def fake_settings(*, credential: Path | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        gmp_org_credentials=credential,
        catalog=SimpleNamespace(
            gmp_org_resource_name=ORG_NAME,
            gmp_org_display_name="Your Organization",
            gmp_org_declared_roles=["Org Admin", "User Admin", "Billing Admin"],
            gmp_org_evidence="example user-provided screenshot",
        ),
    )


def personnel_action(op: str) -> Action:
    # gmp_org is deliberately auxiliary rather than a plannable Product, so a
    # valid product action is enough to prove it cannot become an ACL backend.
    return Action(
        product="ga",
        op=op,  # type: ignore[arg-type]
        email="colleague@example.com",
        brand="wonder-idea",
        resource_id=ORG_NAME,
        resource_name="Your Organization",
        role="Org Admin" if op != "revoke" else None,
    )


class GmpOrgConfigTests(unittest.TestCase):
    def test_org_credentials_default_to_gtm_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            gtm_key = Path(directory) / "gtm.json"
            gtm_key.write_text("{}", encoding="utf-8")
            with patch.dict(
                os.environ,
                {
                    "GMP_GTM_CREDENTIALS": str(gtm_key),
                    "GMP_ORG_CREDENTIALS": "",
                },
                clear=False,
            ):
                settings = load_settings()

        self.assertEqual(settings.gtm_credentials, gtm_key)
        self.assertEqual(settings.gmp_org_credentials, gtm_key)

    def test_explicit_org_credentials_override_gtm_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            gtm_key = Path(directory) / "gtm.json"
            org_key = Path(directory) / "org.json"
            gtm_key.write_text("{}", encoding="utf-8")
            org_key.write_text("{}", encoding="utf-8")
            with patch.dict(
                os.environ,
                {
                    "GMP_GTM_CREDENTIALS": str(gtm_key),
                    "GMP_ORG_CREDENTIALS": str(org_key),
                },
                clear=False,
            ):
                settings = load_settings()

        self.assertEqual(settings.gtm_credentials, gtm_key)
        self.assertEqual(settings.gmp_org_credentials, org_key)


class GmpOrgProviderTests(unittest.TestCase):
    def test_discover_lists_organizations_and_analytics_links_only(self) -> None:
        second_org = "organizations/sales-partner-org"
        organizations = FakeOrganizations(
            [
                {"name": ORG_NAME, "displayName": "Your Organization"},
                {"name": second_org, "displayName": "Sales Partner"},
            ],
            {
                ORG_NAME: [
                    {
                        "name": f"{ORG_NAME}/analyticsAccountLinks/123456",
                        "analyticsAccount": "analyticsAccounts/123456",
                        "ignoredField": "not part of the stable output contract",
                    }
                ],
                second_org: [],
            },
        )
        provider = GmpOrgProvider(fake_settings())  # type: ignore[arg-type]
        with patch.object(provider, "_service", return_value=FakeService(organizations)):
            result = provider.discover()

        self.assertEqual(organizations.list_calls, 1)
        self.assertEqual(organizations._links.list_calls, [ORG_NAME, second_org])
        self.assertFalse(result["personnel_user_api"])
        self.assertFalse(result["declared_role_evidence"]["verified_by_public_api"])
        self.assertEqual(result["declared_role_evidence"]["organization"], ORG_NAME)
        self.assertEqual(
            result["organizations"],
            [
                {
                    "name": ORG_NAME,
                    "display_name": "Your Organization",
                    "configured": True,
                    "analytics_account_links": [
                        {
                            "name": f"{ORG_NAME}/analyticsAccountLinks/123456",
                            "analytics_account": "analyticsAccounts/123456",
                        }
                    ],
                },
                {
                    "name": second_org,
                    "display_name": "Sales Partner",
                    "configured": False,
                    "analytics_account_links": [],
                },
            ],
        )

    def test_doctor_reports_read_capability_without_claiming_acl_write(self) -> None:
        provider = GmpOrgProvider(fake_settings())  # type: ignore[arg-type]
        discovered = [{"name": ORG_NAME, "analytics_account_links": []}]
        with patch.object(
            provider,
            "discover",
            return_value={"organizations": discovered},
        ):
            result = provider.doctor()

        self.assertTrue(result["read"])
        self.assertTrue(result["api_enabled"])
        self.assertTrue(result["service_usage_ready"])
        self.assertFalse(result["write"])
        self.assertFalse(result["personnel_user_api"])
        self.assertFalse(result["organization_role_api"])
        self.assertTrue(result["analytics_account_link_api"])
        self.assertEqual(result["organizations"], discovered)
        evidence = result["declared_role_evidence"]
        self.assertEqual(
            evidence["declared_roles"],
            ["Org Admin", "User Admin", "Billing Admin"],
        )
        self.assertEqual(evidence["source"], "example user-provided screenshot")
        self.assertFalse(evidence["verified_by_public_api"])

    def test_doctor_preserves_acl_limit_when_public_api_is_disabled(self) -> None:
        provider = GmpOrgProvider(fake_settings())  # type: ignore[arg-type]
        with patch.object(
            provider,
            "discover",
            side_effect=RuntimeError("SERVICE_DISABLED: API is disabled"),
        ):
            result = provider.doctor()

        self.assertFalse(result["read"])
        self.assertFalse(result["api_enabled"])
        self.assertFalse(result["service_usage_ready"])
        self.assertFalse(result["personnel_user_api"])
        self.assertFalse(result["organization_role_api"])
        self.assertFalse(result["declared_role_evidence"]["verified_by_public_api"])
        self.assertIn("不会开放组织用户 ACL API", result["next_step"])

    def test_who_is_truthful_about_missing_public_personnel_api(self) -> None:
        provider = GmpOrgProvider(fake_settings())  # type: ignore[arg-type]

        rows = provider.who("colleague@example.com")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["email"], "colleague@example.com")
        self.assertIn("不能列出组织中的其他用户或角色", rows[0]["error"])
        self.assertFalse(rows[0]["declared_role_evidence"]["verified_by_public_api"])

    def test_every_personnel_mutation_is_blocked_without_calling_api(self) -> None:
        provider = GmpOrgProvider(fake_settings())  # type: ignore[arg-type]
        with patch.object(
            provider,
            "_service",
            side_effect=AssertionError("personnel actions must never call GMP API"),
        ) as service:
            for op in ("grant", "revoke", "set_role"):
                for execute in (False, True):
                    with self.subTest(op=op, execute=execute):
                        result = provider.apply(personnel_action(op), execute=execute)
                        self.assertEqual(result.status, "blocked")
                        self.assertEqual(result.dry_run, not execute)
                        self.assertIn("没有人员 ACL endpoint", result.message)
                        self.assertIn("各产品 API", result.next_step or "")
        service.assert_not_called()


class GmpOrgCliTests(unittest.TestCase):
    def test_discover_gmp_org_routes_to_auxiliary_provider(self) -> None:
        discovery = {
            "organizations": [{"name": ORG_NAME}],
            "personnel_user_api": False,
        }
        output = StringIO()
        with patch(
            "gmp_access.workflows.GmpOrgProvider.discover",
            return_value=discovery,
        ) as discover, patch("sys.stdout", output):
            code = main(["discover", "--product", "gmp-org"])

        payload = json.loads(output.getvalue())
        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["product"], "gmp-org")
        self.assertEqual(payload["data"], discovery)
        discover.assert_called_once_with()

    def test_discover_gmp_org_reports_api_failure_without_fallback(self) -> None:
        output = StringIO()
        with patch(
            "gmp_access.workflows.GmpOrgProvider.discover",
            side_effect=RuntimeError("SERVICE_DISABLED"),
        ), patch("sys.stdout", output):
            code = main(["discover", "--product", "gmp-org"])

        payload = json.loads(output.getvalue())
        self.assertEqual(code, 1)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["product"], "gmp-org")
        self.assertEqual(payload["error"], "SERVICE_DISABLED")
        self.assertIn("gmp doctor", payload["next_step"])


if __name__ == "__main__":
    unittest.main()
