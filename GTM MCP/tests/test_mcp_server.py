from __future__ import annotations

import unittest
from unittest.mock import patch

from gtm_agent.client import Target
from gtm_agent.config import Settings
from gtm_agent.mcp_server import create_tag, publish_version
from gtm_agent.runtime import list_local_tools


FAKE_TARGET = Target(
    account_id="1",
    container_id="2",
    workspace_id="3",
    account_path="accounts/1",
    container_path="accounts/1/containers/2",
    workspace_path="accounts/1/containers/2/workspaces/3",
    public_id="GTM-TEST",
    container_name="Test",
    workspace_name="Default Workspace",
)


class McpServerTests(unittest.TestCase):
    def test_expected_tools_are_registered(self) -> None:
        names = {item["name"] for item in list_local_tools()}
        for required in {
            "whoami",
            "check_connection",
            "list_accounts",
            "list_containers",
            "resolve_target",
            "audit_container",
            "search_workspace",
            "create_tag",
            "create_version",
            "publish_version",
        }:
            self.assertIn(required, names)
        self.assertGreaterEqual(len(names), 30)

    @patch("gtm_agent.mcp_server._target", return_value=FAKE_TARGET)
    @patch(
        "gtm_agent.mcp_server.get_settings",
        return_value=Settings(
            account_id="1",
            container_id="GTM-TEST",
            workspace_id="",
            containers={},
            credentials_path="dummy.json",
            read_only=False,
        ),
    )
    def test_create_tag_preview_does_not_write(self, _settings, _target) -> None:
        with patch("gtm_agent.mcp_server._client") as client_factory:
            result = create_tag(
                name="GA4 Config",
                preset="ga4_config",
                measurement_id="G-123",
                confirm=False,
            )
            client_factory.return_value.create_tag.assert_not_called()
        self.assertTrue(result["requires_confirmation"])
        self.assertFalse(result["applied"])
        self.assertEqual(result["preview"]["tag"]["type"], "gaawc")

    @patch("gtm_agent.mcp_server._target", return_value=FAKE_TARGET)
    @patch(
        "gtm_agent.mcp_server.get_settings",
        return_value=Settings(
            account_id="1",
            container_id="GTM-TEST",
            workspace_id="",
            containers={},
            credentials_path="dummy.json",
            read_only=True,
        ),
    )
    def test_read_only_blocks_publish(self, _settings, _target) -> None:
        with self.assertRaises(RuntimeError):
            publish_version(version_id="5", confirm=True)


if __name__ == "__main__":
    unittest.main()
