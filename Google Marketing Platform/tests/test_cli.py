from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from gmp_access.cli import main
from gmp_access.config import load_settings
from gmp_access.models import Action, ActionResult
from gmp_access.planning import create_plan


class CliTests(unittest.TestCase):
    def test_help(self) -> None:
        with self.assertRaises(SystemExit) as raised:
            main(["--help"])
        self.assertEqual(raised.exception.code, 0)

    def test_task_dry_run(self) -> None:
        buffer = StringIO()
        with patch("sys.stdout", buffer):
            code = main(["task", "把 xxx@abc.com 加入 demo 的 ga, search console, ads"])
        payload = json.loads(buffer.getvalue())
        self.assertEqual(code, 0)
        self.assertTrue(payload.get("dry_run", True))
        self.assertIn("results", payload)
        self.assertRegex(payload["plan_id"], r"^[0-9a-f]{16}$")
        self.assertGreaterEqual(payload["summary"].get("planned", 0), 1)

    def test_grant_dry_run_json(self) -> None:
        buffer = StringIO()
        with patch("sys.stdout", buffer):
            code = main(
                [
                    "grant",
                    "--email",
                    "xxx@abc.com",
                    "--brands",
                    "demo",
                    "--products",
                    "ga,gsc,ads",
                    "--preset",
                    "onboard",
                ]
            )
        payload = json.loads(buffer.getvalue())
        self.assertEqual(code, 0)
        self.assertTrue(payload["dry_run"])
        self.assertTrue(all(item["dry_run"] for item in payload["results"]))
        self.assertNotIn("ok", {item["status"] for item in payload["results"]})

    def test_grant_accepts_exact_extra_gsc_sites(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = replace(load_settings(), root=Path(directory))
            buffer = StringIO()
            with patch("gmp_access.cli._settings", return_value=settings), patch(
                "sys.stdout", buffer
            ):
                code = main(
                    [
                        "grant",
                        "--email",
                        "colleague@example.com",
                        "--brands",
                        "demo,demothree,demofour",
                        "--products",
                        "ga,gsc",
                        "--preset",
                        "marketer",
                        "--extra-gsc-sites",
                        "sc-domain:alternate.example.net",
                    ]
                )

        payload = json.loads(buffer.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(payload["extra_gsc_sites"], ["sc-domain:alternate.example.net"])
        gsc = [
            item["action"]
            for item in payload["results"]
            if item["action"]["product"] == "gsc"
        ]
        self.assertEqual(
            {item["resource_id"] for item in gsc},
            {
                "sc-domain:example.com",
                "sc-domain:example.net",
                "sc-domain:alternate.example.net",
                "sc-domain:demofour.example.com",
            },
        )
        self.assertEqual({item["role"] for item in gsc}, {"full"})

    def test_offboard_never_builds_grant_actions(self) -> None:
        buffer = StringIO()
        with patch("sys.stdout", buffer), patch(
            "gmp_access.cli.AccessService.assert_offboard_catalog_complete",
            return_value={"ok": True},
        ) as gate:
            code = main(["offboard", "--email", "former.employee@example.com"])
        payload = json.loads(buffer.getvalue())
        self.assertEqual(code, 0)
        gate.assert_called_once_with()
        self.assertTrue(payload["dry_run"])
        self.assertEqual(payload["offboard_preflight"], {"ok": True})
        self.assertTrue(payload["results"])
        self.assertEqual(
            {item["action"]["op"] for item in payload["results"]},
            {"revoke"},
        )

    def test_natural_language_offboard_uses_completeness_gate(self) -> None:
        buffer = StringIO()
        with patch("sys.stdout", buffer), patch(
            "gmp_access.cli.AccessService.assert_offboard_catalog_complete",
            return_value={"ok": True},
        ) as gate:
            code = main(["task", "离职删除 bob@example.com"])
        payload = json.loads(buffer.getvalue())
        self.assertEqual(code, 0)
        gate.assert_called_once_with()
        self.assertEqual(payload["parsed"]["action"], "offboard")
        self.assertIn("plan_id", payload)

    def test_non_offboard_does_not_use_completeness_gate(self) -> None:
        buffer = StringIO()
        with patch("sys.stdout", buffer), patch(
            "gmp_access.cli.AccessService.assert_offboard_catalog_complete",
            side_effect=AssertionError("gate must only run for offboard"),
        ) as gate:
            code = main(
                ["task", "把 alice@example.com 加入 demo 的 ga"]
            )
        payload = json.loads(buffer.getvalue())
        self.assertEqual(code, 0)
        gate.assert_not_called()
        self.assertIn("plan_id", payload)

    def test_failed_offboard_gate_does_not_create_plan(self) -> None:
        from gmp_access.errors import GmpError

        buffer = StringIO()
        with patch("sys.stdout", buffer), patch(
            "gmp_access.cli.AccessService.assert_offboard_catalog_complete",
            side_effect=GmpError("catalog mismatch", "update catalog"),
        ), patch("gmp_access.cli.create_plan") as create:
            code = main(["offboard", "--email", "former.employee@example.com"])
        payload = json.loads(buffer.getvalue())
        self.assertEqual(code, 1)
        self.assertFalse(payload["ok"])
        self.assertIn("catalog mismatch", payload["error"])
        self.assertNotIn("plan_id", payload)
        create.assert_not_called()

    def test_invalid_offboard_email_is_rejected_before_live_gate(self) -> None:
        buffer = StringIO()
        with patch("sys.stdout", buffer), patch(
            "gmp_access.cli.AccessService.assert_offboard_catalog_complete"
        ) as gate:
            code = main(["offboard", "--email", "not-an-email"])
        payload = json.loads(buffer.getvalue())
        self.assertEqual(code, 1)
        self.assertIn("邮箱不合法", payload["error"])
        gate.assert_not_called()

    def test_apply_offboard_rechecks_gate_without_consuming_plan_on_failure(self) -> None:
        from gmp_access.errors import GmpError
        from gmp_access.planning import plan_state_path

        with tempfile.TemporaryDirectory() as directory:
            settings = replace(load_settings(), root=Path(directory))
            action = Action(
                product="ga",
                op="revoke",
                email="former.employee@example.com",
                brand="demo",
                resource_id="accounts/111111111",
                resource_name="Demo(GA4)",
                role="predefinedRoles/analyst",
                details={"scope": "account", "full_user_revoke": True},
            )
            plan = create_plan(settings, [action], intent="offboard")
            successful = [ActionResult(action, "ok", False, "done")]
            with patch("gmp_access.cli._settings", return_value=settings), patch(
                "gmp_access.cli.AccessService.assert_offboard_catalog_complete",
                side_effect=[
                    GmpError("live catalog drift", "refresh catalog"),
                    {"ok": True, "products": {}},
                ],
            ) as gate, patch(
                "gmp_access.cli.AccessService.execute",
                return_value=successful,
            ) as execute:
                failed_output = StringIO()
                with patch("sys.stdout", failed_output):
                    failed = main(
                        ["apply", plan["plan_id"], "--confirm", plan["plan_id"]]
                    )

                self.assertEqual(failed, 1)
                self.assertIn("live catalog drift", json.loads(failed_output.getvalue())["error"])
                self.assertFalse(plan_state_path(settings, plan["plan_id"]).exists())
                self.assertFalse(Path(directory, ".data", "audit.jsonl").exists())
                execute.assert_not_called()

                retry_output = StringIO()
                with patch("sys.stdout", retry_output):
                    retried = main(
                        ["apply", plan["plan_id"], "--confirm", plan["plan_id"]]
                    )

            retry_payload = json.loads(retry_output.getvalue())
            self.assertEqual(retried, 0)
            self.assertTrue(retry_payload["complete"])
            self.assertEqual(
                retry_payload["offboard_preflight"],
                {"ok": True, "products": {}},
            )
            self.assertEqual(gate.call_count, 2)
            execute.assert_called_once()

    def test_set_role_keeps_set_role_semantics(self) -> None:
        buffer = StringIO()
        with patch("sys.stdout", buffer):
            code = main(
                [
                    "task",
                    "把 alice@example.com 在 demo 的 ga 改成 editor",
                ]
            )
        payload = json.loads(buffer.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(
            {item["action"]["op"] for item in payload["results"]},
            {"set_role"},
        )

    def test_direct_execute_is_rejected_before_remote_writes(self) -> None:
        buffer = StringIO()
        with patch("sys.stdout", buffer):
            code = main(
                [
                    "grant",
                    "--email",
                    "alice@example.com",
                    "--brands",
                    "demo",
                    "--products",
                    "ga",
                    "--execute",
                ]
            )
        payload = json.loads(buffer.getvalue())
        self.assertEqual(code, 1)
        self.assertFalse(payload["ok"])
        self.assertIn("plan_id", payload["next_step"])

    def test_apply_requires_exact_confirmation_and_writes_audit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = replace(load_settings(), root=Path(directory))
            action = Action(
                product="ga",
                op="grant",
                email="alice@example.com",
                brand="demo",
                resource_id="properties/1",
                resource_name="Property",
                role="predefinedRoles/analyst",
            )
            plan = create_plan(settings, [action], intent="onboard")
            successful = [ActionResult(action, "ok", False, "done")]
            with patch("gmp_access.cli._settings", return_value=settings), patch(
                "gmp_access.cli.AccessService.execute",
                return_value=successful,
            ) as execute:
                rejected_output = StringIO()
                with patch("sys.stdout", rejected_output):
                    rejected = main(
                        ["apply", plan["plan_id"], "--confirm", "0000000000000000"]
                    )
                self.assertEqual(rejected, 1)
                execute.assert_not_called()

                accepted_output = StringIO()
                with patch("sys.stdout", accepted_output):
                    accepted = main(
                        ["apply", plan["plan_id"], "--confirm", plan["plan_id"]]
                    )
                payload = json.loads(accepted_output.getvalue())
                self.assertEqual(accepted, 0)
                self.assertTrue(payload["complete"])
                self.assertTrue(Path(payload["audit_file"]).is_file())
                execute.assert_called_once()

                replay_output = StringIO()
                with patch("sys.stdout", replay_output):
                    replayed = main(
                        ["apply", plan["plan_id"], "--confirm", plan["plan_id"]]
                    )
                replay_payload = json.loads(replay_output.getvalue())
                self.assertEqual(replayed, 1)
                self.assertIn("已经执行或曾开始执行", replay_payload["error"])
                execute.assert_called_once()

                audit_rows = [
                    json.loads(line)
                    for line in Path(payload["audit_file"]).read_text(encoding="utf-8").splitlines()
                ]
                self.assertEqual([row["event"] for row in audit_rows], ["started", "finished"])

    def test_apply_returns_follow_up_exit_code_for_manual_work(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = replace(load_settings(), root=Path(directory))
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
            plan = create_plan(settings, [action], intent="onboard")
            manual = [
                ActionResult(
                    action,
                    "manual_required",
                    False,
                    "GSC public API cannot manage users",
                )
            ]
            with patch("gmp_access.cli._settings", return_value=settings), patch(
                "gmp_access.cli.AccessService.execute",
                return_value=manual,
            ):
                output = StringIO()
                with patch("sys.stdout", output):
                    code = main(
                        ["apply", plan["plan_id"], "--confirm", plan["plan_id"]]
                    )

            payload = json.loads(output.getvalue())
            self.assertEqual(code, 2)
            self.assertTrue(payload["ok"])
            self.assertFalse(payload["complete"])
            self.assertTrue(payload["requires_follow_up"])


if __name__ == "__main__":
    unittest.main()
