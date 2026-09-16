from __future__ import annotations

import unittest
from pathlib import Path

from gmp_access.catalog import load_catalog
from gmp_access.config import ROOT


class CatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = load_catalog(ROOT / "catalog.yaml")

    def test_demo_aliases(self) -> None:
        brand = self.catalog.resolve_brand("Demo")
        self.assertEqual(brand.key, "demo")
        self.assertEqual(brand.ga_primary, "properties/123456789")
        self.assertEqual(brand.gsc_primary, "sc-domain:example.com")
        self.assertEqual(brand.ads_targets(False)[0].id, "2345678901")

    def test_all_brands(self) -> None:
        brands = self.catalog.resolve_brands(["all"])
        self.assertGreaterEqual(len(brands), 7)

    def test_gmp_organization_evidence_is_explicitly_non_api_verified(self) -> None:
        payload = self.catalog.to_dict()["gmp_organization"]
        self.assertEqual(
            payload["resource_name"],
            "organizations/YOUR_GMP_ORG_ID",
        )
        self.assertIn("User Admin", payload["declared_roles"])
        self.assertFalse(payload["roles_verified_by_public_api"])

    def test_unknown_brand(self) -> None:
        with self.assertRaises(Exception):
            self.catalog.resolve_brand("not-a-brand")


if __name__ == "__main__":
    unittest.main()
