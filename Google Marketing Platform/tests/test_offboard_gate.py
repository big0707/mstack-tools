from __future__ import annotations

import unittest
from contextlib import ExitStack
from unittest.mock import patch

from gmp_access.config import load_settings
from gmp_access.errors import GmpError
from gmp_access.workflows import AccessService


class OffboardCatalogGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = load_settings()
        self.service = AccessService(self.settings)

        self.ga_accounts = sorted(
            {
                brand.ga_account
                for brand in self.settings.catalog.brands.values()
                if brand.ga_account
            }
        )
        self.gtm_accounts = sorted(
            {
                container.account_id
                for brand in self.settings.catalog.brands.values()
                for container in brand.gtm_containers
                if container.account_id
            }
        )
        self.gsc_sites = sorted(
            {
                site
                for brand in self.settings.catalog.brands.values()
                for site in brand.gsc_targets(True)
            }
        )
        self.ads_customers = sorted(
            {
                customer.id
                for brand in self.settings.catalog.brands.values()
                for customer in brand.ads_customers
            }
        )

    def patched_live(
        self,
        stack: ExitStack,
        *,
        ga_accounts: list[str] | None = None,
        gtm_accounts: list[str] | None = None,
        gsc_sites: list[str] | None = None,
        ads_customers: list[str] | None = None,
    ) -> None:
        stack.enter_context(
            patch.object(
                self.service.providers["ga"],
                "list_account_ids",
                return_value=self.ga_accounts if ga_accounts is None else ga_accounts,
            )
        )
        stack.enter_context(
            patch.object(
                self.service.providers["gtm"],
                "discover",
                return_value=[
                    {
                        "account_id": account_id,
                        # Deliberately unrelated to catalog: account-wide GTM
                        # offboarding covers every container in this account.
                        "containers": [{"container_id": "live-only-container"}],
                    }
                    for account_id in (
                        self.gtm_accounts if gtm_accounts is None else gtm_accounts
                    )
                ],
            )
        )
        stack.enter_context(
            patch.object(
                self.service.providers["gsc"],
                "list_sites",
                return_value=[
                    {"siteUrl": site}
                    for site in (self.gsc_sites if gsc_sites is None else gsc_sites)
                ],
            )
        )
        stack.enter_context(
            patch.object(
                self.service.providers["ads"],
                "list_customer_tree",
                return_value=[
                    {"customer_id": customer_id}
                    for customer_id in (
                        self.ads_customers if ads_customers is None else ads_customers
                    )
                ],
            )
        )

    def test_exact_live_boundary_passes_and_ignores_gtm_container_drift(self) -> None:
        with ExitStack() as stack:
            self.patched_live(stack)
            report = self.service.assert_offboard_catalog_complete()

        self.assertTrue(report["ok"])
        products = report["products"]
        self.assertTrue(all(item["ok"] for item in products.values()))
        self.assertEqual(products["gtm"]["catalog_count"], len(self.gtm_accounts))

    def test_untracked_live_resource_fails_closed(self) -> None:
        with ExitStack() as stack:
            self.patched_live(
                stack,
                gsc_sites=[*self.gsc_sites, "sc-domain:untracked.example"],
            )
            with self.assertRaises(GmpError) as raised:
                self.service.assert_offboard_catalog_complete()

        self.assertIn("gsc 不一致", str(raised.exception))
        self.assertIn("sc-domain:untracked.example", str(raised.exception))

    def test_catalog_resource_not_visible_live_fails_closed(self) -> None:
        with ExitStack() as stack:
            self.patched_live(stack, ga_accounts=self.ga_accounts[1:])
            with self.assertRaises(GmpError) as raised:
                self.service.assert_offboard_catalog_complete()

        self.assertIn("ga 不一致", str(raised.exception))
        self.assertIn("catalog_only", str(raised.exception))

    def test_read_error_fails_closed(self) -> None:
        with ExitStack() as stack:
            self.patched_live(stack)
            stack.enter_context(
                patch.object(
                    self.service.providers["ga"],
                    "list_account_ids",
                    side_effect=RuntimeError("simulated API outage"),
                )
            )
            with self.assertRaises(GmpError) as raised:
                self.service.assert_offboard_catalog_complete()

        self.assertIn("ga 实时资源无法只读获取", str(raised.exception))
        self.assertIn("simulated API outage", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
