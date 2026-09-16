from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from gmp_access.audit import audit_path, read_history
from gmp_access.config import load_settings


class AuditTests(unittest.TestCase):
    def test_plan_filter_happens_before_limit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = replace(load_settings(), root=Path(directory))
            path = audit_path(settings)
            path.parent.mkdir(parents=True, exist_ok=True)
            rows = [{"plan_id": "wanted", "event": "started"}]
            rows.extend(
                {"plan_id": f"other-{index}", "event": "finished"}
                for index in range(30)
            )
            path.write_text(
                "".join(json.dumps(row) + "\n" for row in rows),
                encoding="utf-8",
            )

            filtered = read_history(settings, limit=20, plan_id="wanted")

            self.assertEqual(filtered, [{"plan_id": "wanted", "event": "started"}])


if __name__ == "__main__":
    unittest.main()
