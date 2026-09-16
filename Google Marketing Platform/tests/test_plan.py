from __future__ import annotations

import unittest

from gmp_access.catalog import Brand, GaProperty
from gmp_access.config import load_settings
from gmp_access.errors import GmpError
from gmp_access.roles import normalize_preset
from gmp_access.workflows import build_plan, normalize_products


class PlanTests(unittest.TestCase):
    def test_primary_only_grant(self) -> None:
        settings = load_settings()
        brand = settings.catalog.resolve_brand("demo")
        actions = build_plan(
            settings,
            email="xxx@abc.com",
            brands=[brand],
            products=normalize_products(["ga", "gsc", "ads"]),
            op="grant",
            preset=normalize_preset("onboard"),
        )
        ga = [item for item in actions if item.product == "ga"]
        gsc = [item for item in actions if item.product == "gsc"]
        ads = [item for item in actions if item.product == "ads"]
        self.assertEqual(len(ga), 1)
        self.assertEqual(ga[0].resource_id, "properties/123456789")
        self.assertEqual(gsc[0].resource_id, "sc-domain:example.com")
        self.assertEqual(gsc[0].method, "manual")
        self.assertEqual(ads[0].resource_id, "2345678901")
        self.assertTrue(all(item.op == "grant" for item in actions))

    def test_rejects_admin_without_flag(self) -> None:
        settings = load_settings()
        brand = settings.catalog.resolve_brand("demo")
        with self.assertRaises(Exception):
            build_plan(
                settings,
                email="xxx@abc.com",
                brands=[brand],
                products=["ga"],
                op="grant",
                preset="admin",
            )

    def test_offboard_includes_account_level_cleanup_and_deduplicates(self) -> None:
        settings = load_settings()
        actions = build_plan(
            settings,
            email="former@example.com",
            brands=settings.catalog.resolve_brands(["all"]),
            products=normalize_products(["ga", "gtm", "ads"]),
            op="revoke",
            preset="onboard",
            all_resources=True,
            include_mcc=True,
            full_user_revoke=True,
        )
        self.assertEqual({item.op for item in actions}, {"revoke"})
        ga_accounts = [item for item in actions if item.product == "ga" and item.details.get("scope") == "account"]
        self.assertEqual(len({item.resource_id for item in ga_accounts}), len(ga_accounts))
        gtm_accounts = [item for item in actions if item.product == "gtm"]
        self.assertEqual(len(gtm_accounts), 1)
        self.assertTrue(gtm_accounts[0].details["account_wide_revoke"])
        self.assertTrue(any(item.details.get("scope") == "mcc" for item in actions if item.product == "ads"))

    def test_gtm_primary_and_all_resources(self) -> None:
        settings = load_settings()
        brand = settings.catalog.resolve_brand("demo")
        primary = build_plan(
            settings,
            email="alice@example.com",
            brands=[brand],
            products=["gtm"],
            op="grant",
            preset="onboard",
        )
        all_resources = build_plan(
            settings,
            email="alice@example.com",
            brands=[brand],
            products=["gtm"],
            op="grant",
            preset="onboard",
            all_resources=True,
        )
        self.assertEqual([item.resource_id for item in primary], ["GTM-XXXXXXX"])
        self.assertEqual(
            {item.resource_id for item in all_resources},
            {"GTM-XXXXXXX", "GTM-SECOND"},
        )

    def test_ga_account_scope_set_role_deduplicates_shared_accounts(self) -> None:
        settings = load_settings()
        shared = "accounts/111111111"
        brands = [
            Brand(
                key="alpha",
                display_name="Alpha",
                aliases=[],
                ga_account=shared,
                ga_account_name="Shared GA",
                ga_primary="properties/123456789",
                ga_properties=[GaProperty(id="properties/123456789", name="Alpha")],
                gsc_primary="",
                gsc_sites=[],
                gtm_containers=[],
                ads_customers=[],
            ),
            Brand(
                key="beta",
                display_name="Beta",
                aliases=[],
                ga_account=shared,
                ga_account_name="Shared GA",
                ga_primary="properties/123456780",
                ga_properties=[GaProperty(id="properties/123456780", name="Beta")],
                gsc_primary="",
                gsc_sites=[],
                gtm_containers=[],
                ads_customers=[],
            ),
        ]
        actions = build_plan(
            settings,
            email="ga-reader@example.com",
            brands=brands,
            products=["ga"],
            op="set_role",
            preset="viewer",
            role="viewer",
            ga_account_scope=True,
        )

        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].resource_id, shared)
        self.assertEqual(actions[0].details["scope"], "account")
        self.assertEqual(actions[0].details["brands"], ["alpha", "beta"])
        self.assertEqual(actions[0].role, "predefinedRoles/viewer")

    def test_extra_gsc_sites_add_only_exact_named_targets(self) -> None:
        settings = load_settings()
        actions = build_plan(
            settings,
            email="alice@example.com",
            brands=settings.catalog.resolve_brands(["demo", "demothree", "demofour"]),
            products=["ga", "gsc"],
            op="grant",
            preset="marketer",
            extra_gsc_sites=["sc-domain:alternate.example.net"],
        )

        gsc = [item for item in actions if item.product == "gsc"]
        self.assertEqual(
            {item.resource_id for item in gsc},
            {
                "sc-domain:example.com",
                "sc-domain:example.net",
                "sc-domain:alternate.example.net",
                "sc-domain:demofour.example.com",
            },
        )
        self.assertEqual({item.role for item in gsc}, {"full"})
        self.assertEqual(
            next(item for item in gsc if item.resource_id == "sc-domain:alternate.example.net").brand,
            "demothree",
        )

    def test_extra_gsc_site_must_exist_in_selected_brand_catalog(self) -> None:
        settings = load_settings()
        with self.assertRaisesRegex(GmpError, "不在已选品牌 catalog"):
            build_plan(
                settings,
                email="alice@example.com",
                brands=settings.catalog.resolve_brands(["demothree"]),
                products=["gsc"],
                op="grant",
                preset="marketer",
                extra_gsc_sites=["sc-domain:example.com"],
            )

    def test_extra_gsc_sites_require_gsc_product(self) -> None:
        settings = load_settings()
        with self.assertRaisesRegex(GmpError, "products 包含 gsc"):
            build_plan(
                settings,
                email="alice@example.com",
                brands=settings.catalog.resolve_brands(["demo"]),
                products=["ga"],
                op="grant",
                preset="marketer",
                extra_gsc_sites=["sc-domain:example.com"],
            )

    def test_extra_gsc_site_deduplicates_primary_action(self) -> None:
        settings = load_settings()
        actions = build_plan(
            settings,
            email="alice@example.com",
            brands=settings.catalog.resolve_brands(["demo"]),
            products=["gsc"],
            op="grant",
            preset="marketer",
            extra_gsc_sites=[
                "sc-domain:example.com",
                "sc-domain:example.com",
            ],
        )
        self.assertEqual(
            [item.resource_id for item in actions],
            ["sc-domain:example.com"],
        )


if __name__ == "__main__":
    unittest.main()
