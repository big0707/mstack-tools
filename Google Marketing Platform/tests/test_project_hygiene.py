from __future__ import annotations

import unittest

from gmp_access.config import ROOT


class ProjectHygieneTests(unittest.TestCase):
    def test_supported_source_has_no_browser_automation_dependency(self) -> None:
        source = ROOT / "src" / "gmp_access"
        combined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in source.rglob("*.py")
            if "__pycache__" not in path.parts
        ).casefold()
        self.assertNotIn("playwright", combined)
        self.assertNotIn("gmp_access.browser", combined)
        self.assertNotIn("from ..browser", combined)


if __name__ == "__main__":
    unittest.main()
