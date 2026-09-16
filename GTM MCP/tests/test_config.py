from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from gtm_agent.config import (
    Settings,
    read_service_account_identity,
)


class ConfigTests(unittest.TestCase):
    def test_alias_and_public_id_resolution(self) -> None:
        settings = Settings(
            account_id="123",
            container_id="GTM-ABCDE",
            workspace_id="",
            containers={"demo": "GTM-DEMO1", "demothree": "GTM-DEMO2"},
            credentials_path=None,
            read_only=False,
        )
        self.assertEqual(settings.resolve_container_query(), "GTM-ABCDE")
        self.assertEqual(settings.resolve_container_query("Demo"), "GTM-DEMO1")
        self.assertEqual(settings.resolve_container_query("GTM-ZZZZ"), "GTM-ZZZZ")
        self.assertEqual(settings.resolve_container_query("987654"), "987654")
        with self.assertRaises(ValueError):
            settings.resolve_container_query("unknown-site")

    def test_identity_omits_private_key(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "sa.json"
            path.write_text(
                json.dumps(
                    {
                        "type": "service_account",
                        "project_id": "demo-project",
                        "client_email": "gtm-mcp@demo-project.iam.gserviceaccount.com",
                        "private_key": "-----BEGIN PRIVATE KEY-----\\nSECRET\\n-----END PRIVATE KEY-----\\n",
                    }
                ),
                encoding="utf-8",
            )
            identity = read_service_account_identity(str(path))
        self.assertEqual(identity["client_email"], "gtm-mcp@demo-project.iam.gserviceaccount.com")
        self.assertEqual(identity["project_id"], "demo-project")
        self.assertNotIn("private_key", identity)


if __name__ == "__main__":
    unittest.main()
