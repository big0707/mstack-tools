from __future__ import annotations

import unittest

from gmp_access.models import Action
from gmp_access.providers.gsc import GscProvider


class GscProviderTests(unittest.TestCase):
    def test_execute_is_truthful_manual_required(self) -> None:
        action = Action(
            product="gsc",
            op="grant",
            email="alice@example.com",
            brand="demo",
            resource_id="sc-domain:example.com",
            resource_name="sc-domain:example.com",
            role="full",
            method="manual",
        )
        result = GscProvider(None).apply(action, execute=True)  # type: ignore[arg-type]
        self.assertEqual(result.status, "manual_required")
        self.assertFalse(result.dry_run)
        self.assertFalse(result.data["public_user_api"])
        self.assertIn("users_url", result.data)
        self.assertIn("不得降级", result.message)

    def test_grant_preview_pres_not_downgrade_existing_higher_access(self) -> None:
        action = Action(
            product="gsc",
            op="grant",
            email="alice@example.com",
            brand="demo",
            resource_id="sc-domain:example.com",
            resource_name="sc-domain:example.com",
            role="full",
            method="manual",
        )

        result = GscProvider(None).apply(action, execute=False)  # type: ignore[arg-type]

        self.assertEqual(result.status, "planned")
        self.assertIn("至少授予", result.message)
        self.assertIn("保持不变", result.message)


if __name__ == "__main__":
    unittest.main()
