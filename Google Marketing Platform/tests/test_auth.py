from __future__ import annotations

import json
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from gmp_access.auth import (
    ADS_PERSONNEL_SERVICE_ACCOUNT,
    ads_client_kwargs,
    ads_service_account_email,
    audit_identity_summary,
    credentials_for,
    identity_summary,
    load_ads_client,
)
from gmp_access.config import load_settings
from gmp_access.errors import GmpError


class AuthTests(unittest.TestCase):
    def _ads_settings(self, root: Path):
        key = root / "personnel.json"
        key.write_text(
            json.dumps({"type": "service_account", "client_email": ADS_PERSONNEL_SERVICE_ACCOUNT}),
            encoding="utf-8",
        )
        delivery_key = root / "delivery.json"
        delivery_key.write_text(
            json.dumps({"type": "service_account", "client_email": "ads-delivery@example.com"}),
            encoding="utf-8",
        )
        config = root / "google-ads.yaml"
        config.write_text(
            "developer_token: test-token\n"
            "json_key_file_path: delivery.json\n"
            "path_to_private_key_file: delivery.pem\n"
            "client_id: delivery-client-id\n"
            "client_secret: delivery-client-secret\n"
            "refresh_token: delivery-refresh-token\n"
            "impersonated_email: delivery@example.com\n"
            "use_application_default_credentials: true\n"
            "login_customer_id: '1234567890'\n"
            "use_proto_plus: true\n",
            encoding="utf-8",
        )
        return replace(
            load_settings(),
            ads_credentials=key,
            ads_yaml=config,
            ads_login_customer_id="123-456-7890",
            oauth_token_file=root / "token.json",
        )

    def test_ads_isolates_shared_yaml_and_ignores_oauth(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = self._ads_settings(root)
            before = settings.ads_yaml.read_bytes()
            with patch("gmp_access.auth.load_oauth_credentials", side_effect=AssertionError("Ads must not load OAuth")):
                kwargs = ads_client_kwargs(settings)
            self.assertEqual(kwargs, {
                "developer_token": "test-token",
                "json_key_file_path": str(settings.ads_credentials.resolve()),
                "login_customer_id": "1234567890",
                "use_proto_plus": True,
            })
            self.assertEqual(settings.ads_yaml.read_bytes(), before)
            self.assertEqual(ads_service_account_email(settings), ADS_PERSONNEL_SERVICE_ACCOUNT)

    def test_ads_read_and_write_routing_do_not_load_general_oauth(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = self._ads_settings(Path(directory))
            with patch("gmp_access.auth.load_oauth_credentials", side_effect=AssertionError("Ads must not load OAuth")):
                for write in (False, True):
                    kwargs = credentials_for(settings, "ads", write=write)
                    self.assertEqual(kwargs["json_key_file_path"], str(settings.ads_credentials.resolve()))

    def test_ads_sdk_receives_only_personnel_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = self._ads_settings(Path(directory))
            client = object()
            with patch("google.ads.googleads.client.GoogleAdsClient.load_from_dict", return_value=client) as load:
                self.assertIs(load_ads_client(settings), client)
            kwargs = load.call_args.args[0]
            self.assertEqual(kwargs["json_key_file_path"], str(settings.ads_credentials.resolve()))
            self.assertNotIn("refresh_token", kwargs)
            self.assertNotIn("impersonated_email", kwargs)

    def test_ads_missing_explicit_key_does_not_fall_back(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = self._ads_settings(Path(directory))
            settings = replace(settings, gmp_org_credentials=settings.ads_credentials, ads_credentials=Path(directory) / "missing.json")
            with patch("gmp_access.auth.load_oauth_credentials", side_effect=AssertionError("Ads must not load OAuth")):
                with self.assertRaisesRegex(GmpError, "找不到 Ads"):
                    ads_client_kwargs(settings)
            self.assertIsNone(ads_service_account_email(settings))

    def test_ads_wrong_identity_or_type_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = self._ads_settings(Path(directory))
            for payload in (
                {"type": "service_account", "client_email": "ads-delivery@example.com"},
                {"type": "authorized_user", "client_email": ADS_PERSONNEL_SERVICE_ACCOUNT},
                {"type": "service_account"},
                [],
            ):
                with self.subTest(payload=payload):
                    settings.ads_credentials.write_text(json.dumps(payload), encoding="utf-8")
                    with self.assertRaisesRegex(GmpError, "身份不匹配"):
                        ads_client_kwargs(settings)
                    self.assertIsNone(ads_service_account_email(settings))

    def test_ads_invalid_json_or_yaml_never_echoes_secret_contents(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = self._ads_settings(Path(directory))
            settings.ads_yaml.write_text("developer_token: [DO_NOT_ECHO_SECRET", encoding="utf-8")
            with self.assertRaises(GmpError) as captured:
                ads_client_kwargs(settings)
            self.assertNotIn("DO_NOT_ECHO_SECRET", str(captured.exception))
            settings.ads_credentials.write_text("{DO_NOT_ECHO_SECRET", encoding="utf-8")
            with self.assertRaises(GmpError) as captured:
                ads_client_kwargs(settings)
            self.assertNotIn("DO_NOT_ECHO_SECRET", str(captured.exception))

    def test_ads_identity_summary_matches_client_with_oauth_present(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = self._ads_settings(Path(directory))
            with patch("gmp_access.auth.load_oauth_credentials", return_value=SimpleNamespace(valid=True)):
                summary = identity_summary(settings)
                kwargs = ads_client_kwargs(settings)
            self.assertTrue(summary["oauth_present"])
            self.assertEqual(summary["ads_sa"], ADS_PERSONNEL_SERVICE_ACCOUNT)
            self.assertEqual(summary["ads_credential_mode"], "service_account")
            self.assertTrue(summary["ads_identity_valid"])
            self.assertEqual(Path(kwargs["json_key_file_path"]), settings.ads_credentials.resolve())

    def test_settings_default_ads_key_reuses_org_key_and_explicit_missing_is_not_replaced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            org_key = Path(directory) / "org.json"
            org_key.write_text("{}", encoding="utf-8")
            with patch("gmp_access.config.load_dotenv"), patch("gmp_access.config._gtm_mcp_credentials", return_value=org_key):
                with patch.dict(os.environ, {}, clear=True):
                    settings = load_settings()
                    self.assertEqual(settings.ads_credentials, org_key)
                missing = Path(directory) / "missing.json"
                with patch.dict(os.environ, {"GMP_ADS_CREDENTIALS": str(missing)}, clear=True):
                    settings = load_settings()
                    self.assertEqual(settings.ads_credentials, missing)

    def test_read_inventory_prefers_dedicated_service_account_over_oauth(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ga_key = Path(directory) / "ga.json"
            ga_key.write_text("{}", encoding="utf-8")
            settings = replace(load_settings(), ga_credentials=ga_key)
            oauth = SimpleNamespace(valid=True)
            dedicated = object()
            with patch("gmp_access.auth.load_oauth_credentials", return_value=oauth), patch(
                "gmp_access.auth.service_account_credentials",
                return_value=dedicated,
            ) as load_sa:
                selected = credentials_for(settings, "ga", write=False)

            self.assertIs(selected, dedicated)
            load_sa.assert_called_once()

    def test_ga_service_account_write_prefers_gmp_org_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ga_key = root / "ga.json"
            org_key = root / "org.json"
            ga_key.write_text("{}", encoding="utf-8")
            org_key.write_text("{}", encoding="utf-8")
            settings = replace(
                load_settings(),
                ga_credentials=ga_key,
                gmp_org_credentials=org_key,
            )
            selected = object()
            with patch("gmp_access.auth.load_oauth_credentials", return_value=None), patch(
                "gmp_access.auth.service_account_credentials",
                return_value=selected,
            ) as load_sa:
                credential = credentials_for(settings, "ga", write=True)

            self.assertIs(credential, selected)
            self.assertEqual(load_sa.call_args.args[0], org_key)

    def test_audit_identity_records_oauth_email_best_effort(self) -> None:
        settings = load_settings()
        base = {"oauth_present": True, "oauth_valid": True}
        with patch("gmp_access.auth.identity_summary", return_value=base), patch(
            "gmp_access.auth.oauth_identity_email",
            return_value="admin@example.com",
        ):
            summary = audit_identity_summary(settings)

        self.assertEqual(summary["oauth_email"], "admin@example.com")

    def test_audit_identity_keeps_evidence_if_userinfo_fails(self) -> None:
        settings = load_settings()
        base = {"oauth_present": True, "oauth_valid": True, "ga_sa": "ga@example.com"}
        with patch("gmp_access.auth.identity_summary", return_value=base), patch(
            "gmp_access.auth.oauth_identity_email",
            side_effect=RuntimeError("userinfo unavailable"),
        ):
            summary = audit_identity_summary(settings)

        self.assertEqual(summary["ga_sa"], "ga@example.com")
        self.assertIn("userinfo unavailable", summary["oauth_email_error"])


if __name__ == "__main__":
    unittest.main()
