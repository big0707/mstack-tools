from __future__ import annotations

import unittest

from gmp_access.roles import ga_role, is_privileged, normalize_preset, role_for


class RoleTests(unittest.TestCase):
    def test_onboard_defaults(self) -> None:
        self.assertEqual(role_for("onboard", "ga"), "analyst")
        self.assertEqual(role_for("onboard", "gsc"), "restricted")
        self.assertEqual(role_for("入职", "ads"), "READ_ONLY")
        self.assertEqual(role_for("service_account", "ga"), "viewer")
        self.assertEqual(role_for("服务账号", "gtm"), "publish")
        self.assertEqual(role_for("service_account", "ads"), "READ_ONLY")

    def test_ga_admin_alias(self) -> None:
        self.assertEqual(ga_role("administrator"), "predefinedRoles/admin")
        self.assertTrue(is_privileged("ga", "admin"))
        self.assertFalse(is_privileged("ga", "analyst"))

    def test_unknown_preset(self) -> None:
        with self.assertRaises(Exception):
            normalize_preset("superuser")


if __name__ == "__main__":
    unittest.main()
