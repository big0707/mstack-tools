from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from gmp_access.config import load_settings
from gmp_access.models import Action
from gmp_access.planning import (
    actions_from_plan,
    apply_lock,
    begin_plan_attempt,
    create_plan,
    load_plan,
    plan_directory,
    plan_lock,
)


class PlanningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.settings = replace(load_settings(), root=Path(self.temporary.name))
        self.action = Action(
            product="ga",
            op="grant",
            email="alice@example.com",
            brand="demo",
            resource_id="properties/123456789",
            resource_name="Demo",
            role="predefinedRoles/analyst",
        )

    def test_round_trip_immutable_plan(self) -> None:
        created = create_plan(
            self.settings,
            [self.action],
            intent="onboard",
            reason="ticket HR-123",
        )
        loaded = load_plan(self.settings, created["plan_id"])
        actions = actions_from_plan(loaded)
        self.assertEqual(actions[0].email, "alice@example.com")
        self.assertEqual(actions[0].op, "grant")
        self.assertEqual(loaded["reason"], "ticket HR-123")

    def test_tampered_plan_is_rejected(self) -> None:
        created = create_plan(self.settings, [self.action], intent="onboard")
        path = plan_directory(self.settings) / f"{created['plan_id']}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["actions"][0]["role"] = "predefinedRoles/admin"
        path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(Exception, "校验失败"):
            load_plan(self.settings, created["plan_id"])

    def test_plan_lock_rejects_parallel_apply(self) -> None:
        created = create_plan(self.settings, [self.action], intent="onboard")
        with plan_lock(self.settings, created["plan_id"]):
            with self.assertRaisesRegex(Exception, "正在被另一个进程执行"):
                with plan_lock(self.settings, created["plan_id"]):
                    pass

    def test_global_apply_lock_rejects_parallel_apply(self) -> None:
        with apply_lock(self.settings):
            with self.assertRaisesRegex(Exception, "另一个权限计划"):
                with apply_lock(self.settings):
                    pass

    def test_plan_is_single_use_once_attempt_starts(self) -> None:
        created = create_plan(self.settings, [self.action], intent="onboard")
        begin_plan_attempt(self.settings, created)
        with self.assertRaisesRegex(Exception, "已经执行或曾开始执行"):
            begin_plan_attempt(self.settings, created)

    def test_older_plan_cannot_override_newer_attempt_for_same_user_product(self) -> None:
        same_windows_tick = datetime(2026, 9, 3, 7, 0, 0, tzinfo=timezone.utc)
        with patch("gmp_access.planning._utcnow", return_value=same_windows_tick):
            older = create_plan(self.settings, [self.action], intent="grant", reason="older")
            newer = create_plan(self.settings, [self.action], intent="set_role", reason="newer")
        self.assertGreater(newer["created_at"], older["created_at"])
        begin_plan_attempt(self.settings, newer)
        with self.assertRaisesRegex(Exception, "更新的计划"):
            begin_plan_attempt(self.settings, older)

    def test_apply_mode_rejects_plan_after_catalog_changes(self) -> None:
        catalog_copy = Path(self.temporary.name) / "catalog.yaml"
        catalog_copy.write_bytes(self.settings.catalog.path.read_bytes())
        self.settings.catalog.path = catalog_copy
        created = create_plan(self.settings, [self.action], intent="offboard")
        catalog_copy.write_text(
            catalog_copy.read_text(encoding="utf-8") + "\n# newly mapped resource\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(Exception, "catalog.yaml"):
            load_plan(
                self.settings,
                created["plan_id"],
                require_current_catalog=True,
            )

        inspected = load_plan(self.settings, created["plan_id"])
        self.assertEqual(inspected["plan_id"], created["plan_id"])


if __name__ == "__main__":
    unittest.main()
