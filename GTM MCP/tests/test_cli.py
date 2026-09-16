from __future__ import annotations

import json
import unittest
from io import StringIO
from unittest.mock import patch

from gtm_agent.cli import main


class CliTests(unittest.TestCase):
    def test_help_lists_agent_commands(self) -> None:
        buffer = StringIO()
        with patch("sys.stdout", buffer):
            with self.assertRaises(SystemExit) as exc:
                main(["--help"])
        self.assertEqual(exc.exception.code, 0)
        text = buffer.getvalue()
        for name in ("doctor", "tools", "call", "audit", "snapshot", "cleanup", "publish"):
            self.assertIn(name, text)

    def test_call_dry_run_does_not_start_mcp(self) -> None:
        buffer = StringIO()
        with patch("sys.stdout", buffer):
            code = main(["call", "list_accounts", "{}", "--dry-run"])
        self.assertEqual(code, 0)
        payload = json.loads(buffer.getvalue())
        self.assertTrue(payload["dry_run"])
        self.assertEqual(payload["tool"], "list_accounts")

    def test_publish_defaults_to_dry_run(self) -> None:
        buffer = StringIO()
        with patch("sys.stdout", buffer):
            code = main(["publish", "12"])
        self.assertEqual(code, 0)
        payload = json.loads(buffer.getvalue())
        self.assertTrue(payload["dry_run"])
        self.assertEqual(payload["action"], "publish_version")


if __name__ == "__main__":
    unittest.main()
