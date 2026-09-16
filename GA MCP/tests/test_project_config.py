from __future__ import annotations

import json
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ProjectConfigTests(unittest.TestCase):
    def test_cursor_and_codex_configs_are_valid_and_portable(self) -> None:
        cursor = json.loads((ROOT / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
        with (ROOT / ".codex" / "config.toml").open("rb") as file:
            codex = tomllib.load(file)

        self.assertEqual(cursor["mcpServers"]["ga4"]["command"], "powershell.exe")
        self.assertEqual(codex["mcp_servers"]["ga4"]["command"], "powershell.exe")

        serialized = json.dumps(cursor) + repr(codex)
        self.assertNotIn("C:\\Users\\", serialized)
        self.assertIn("scripts/bootstrap-mcp.ps1", serialized)


if __name__ == "__main__":
    unittest.main()

