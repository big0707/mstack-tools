from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values, load_dotenv

from .catalog import Catalog, load_catalog


ROOT = Path(__file__).resolve().parents[2]


def sibling(*parts: str) -> Path:
    return ROOT.parent.joinpath(*parts)


DEFAULT_PATHS = {
    "ga": sibling("GA MCP", "credentials", "ga-service-account.json"),
    "gsc": sibling("SEO-Agent", "credentials", "gsc-key.json"),
    "ads_yaml": sibling("Adwords API", "google-ads.yaml"),
}


@dataclass(frozen=True)
class Settings:
    root: Path
    catalog: Catalog
    ga_credentials: Path | None
    gsc_credentials: Path | None
    gtm_credentials: Path | None
    gmp_org_credentials: Path | None
    ads_yaml: Path | None
    oauth_client_file: Path
    oauth_token_file: Path
    oauth_client_id: str
    oauth_client_secret: str
    ads_login_customer_id: str
    ads_api_version: str
    ads_credentials: Path | None = None


def _optional_file(value: str | None, fallback: Path | None = None) -> Path | None:
    raw = (value or "").strip()
    if raw:
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = ROOT / path
        return path
    if fallback and fallback.is_file():
        return fallback
    return None


def _gtm_mcp_credentials() -> Path | None:
    """Resolve GTM MCP's configured credential path without copying the key."""
    env_path = sibling("GTM MCP", ".env")
    if not env_path.is_file():
        return None
    raw = str(dotenv_values(env_path).get("GOOGLE_APPLICATION_CREDENTIALS") or "").strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = env_path.parent / path
    return path if path.is_file() else None


def load_settings(catalog_path: Path | None = None) -> Settings:
    process_gtm_credentials = os.getenv("GMP_GTM_CREDENTIALS", "").strip()
    load_dotenv(ROOT / ".env", override=False)
    catalog = load_catalog(catalog_path or ROOT / "catalog.yaml")
    configured_gtm = _optional_file(process_gtm_credentials) if process_gtm_credentials else None
    gtm_credentials = configured_gtm or _gtm_mcp_credentials() or _optional_file(
        os.getenv("GMP_GTM_CREDENTIALS")
    )
    gmp_org_credentials = _optional_file(os.getenv("GMP_ORG_CREDENTIALS")) or gtm_credentials
    return Settings(
        root=ROOT,
        catalog=catalog,
        ga_credentials=_optional_file(os.getenv("GMP_GA_CREDENTIALS"), DEFAULT_PATHS["ga"]),
        gsc_credentials=_optional_file(os.getenv("GMP_GSC_CREDENTIALS"), DEFAULT_PATHS["gsc"]),
        gtm_credentials=gtm_credentials,
        gmp_org_credentials=gmp_org_credentials,
        ads_yaml=_optional_file(os.getenv("GMP_ADS_YAML"), DEFAULT_PATHS["ads_yaml"]),
        oauth_client_file=_optional_file(os.getenv("GMP_OAUTH_CLIENT_FILE"), ROOT / "credentials" / "oauth-client.json")
        or ROOT / "credentials" / "oauth-client.json",
        oauth_token_file=_optional_file(os.getenv("GMP_OAUTH_TOKEN_FILE"), ROOT / "credentials" / "token.json")
        or ROOT / "credentials" / "token.json",
        oauth_client_id=os.getenv("GMP_OAUTH_CLIENT_ID", "").strip(),
        oauth_client_secret=os.getenv("GMP_OAUTH_CLIENT_SECRET", "").strip(),
        ads_login_customer_id=os.getenv("GMP_ADS_LOGIN_CUSTOMER_ID", catalog.ads_mcc_id).strip()
        or catalog.ads_mcc_id,
        ads_api_version=os.getenv("GMP_ADS_API_VERSION", "v24").strip() or "v24",
        ads_credentials=_optional_file(os.getenv("GMP_ADS_CREDENTIALS")) or gmp_org_credentials,
    )
