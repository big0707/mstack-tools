from __future__ import annotations

import unittest

from gmp_access.catalog import load_catalog
from gmp_access.config import ROOT
from gmp_access.task_parser import parse_task


class TaskParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = load_catalog(ROOT / "catalog.yaml")

    def test_user_one_liner(self) -> None:
        parsed = parse_task(
            "把 xxx@abc.com 加入 ga, search console, SC, adwords",
            self.catalog,
        )
        self.assertEqual(parsed.action, "grant")
        self.assertEqual(parsed.emails, ["xxx@abc.com"])
        self.assertIn("ga", parsed.products)
        self.assertIn("gsc", parsed.products)
        self.assertIn("ads", parsed.products)
        self.assertEqual(parsed.missing, ["brands"])

    def test_onboard_brand(self) -> None:
        parsed = parse_task(
            "入职把 alice@example.com 加入 demo 的 ga gtm gsc ads",
            self.catalog,
        )
        self.assertEqual(parsed.brands, ["demo"])
        self.assertEqual(set(parsed.products), {"ga", "gtm", "gsc", "ads"})
        self.assertEqual(parsed.preset, "onboard")
        self.assertEqual(parsed.missing, [])

    def test_offboard(self) -> None:
        parsed = parse_task("离职删除 bob@company.com", self.catalog)
        self.assertEqual(parsed.action, "offboard")
        self.assertTrue(parsed.all_resources)
        self.assertEqual(parsed.missing, [])

    def test_ambiguous_delete_requires_brand(self) -> None:
        parsed = parse_task("删除 bob@company.com", self.catalog)
        self.assertEqual(parsed.action, "revoke")
        self.assertIn("brands", parsed.missing)

    def test_set_role_requires_product_and_role(self) -> None:
        parsed = parse_task("把 alice@example.com 在 demo 改权限", self.catalog)
        self.assertEqual(parsed.action, "set_role")
        self.assertIn("products", parsed.missing)
        self.assertIn("role", parsed.missing)

    def test_common_set_role_phrases_are_exact_changes(self) -> None:
        examples = {
            "把 alice@example.com 在 demo 的 ga 权限改为 editor": "editor",
            "把 alice@example.com 在 demo 的 ga 权限更改为 editor": "editor",
            "把 alice@example.com 在 demo 的 ga 设为 viewer": "viewer",
            "把 alice@example.com 在 demo 的 ga 设置为只读": "viewer",
        }
        for text, expected_role in examples.items():
            with self.subTest(text=text):
                parsed = parse_task(text, self.catalog)
                self.assertEqual(parsed.action, "set_role")
                self.assertEqual(parsed.products, ["ga"])
                self.assertEqual(parsed.role, expected_role)
                self.assertEqual(parsed.missing, [])

    def test_explicit_role_change_beats_generic_promotion_template(self) -> None:
        parsed = parse_task(
            "alice@example.com 升职，把 demo 的 ga 权限改为 editor",
            self.catalog,
        )
        self.assertEqual(parsed.action, "set_role")
        self.assertEqual(parsed.role, "editor")

    def test_short_sc_alias_does_not_match_email_or_unrelated_words(self) -> None:
        parsed = parse_task("把 alice@scenic.example 加入 demo 的 ga", self.catalog)
        self.assertEqual(parsed.products, ["ga"])

    def test_action_words_inside_email_never_change_intent(self) -> None:
        for email in ("offboard@example.com", "remove@example.com", "admin@example.com"):
            with self.subTest(email=email):
                parsed = parse_task(f"add {email} to demo ga", self.catalog)
                self.assertEqual(parsed.action, "grant")
                self.assertEqual(parsed.preset, "onboard")
                self.assertEqual(parsed.emails, [email])


if __name__ == "__main__":
    unittest.main()
