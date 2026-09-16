from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import Settings
from .errors import GmpError

ADS_PERSONNEL_SERVICE_ACCOUNT = "YOUR_GMP_SA@YOUR_GCP_PROJECT.iam.gserviceaccount.com"

WRITE_SCOPES = (
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/analytics.manage.users",
    "https://www.googleapis.com/auth/analytics.readonly",
    "https://www.googleapis.com/auth/tagmanager.manage.users",
    "https://www.googleapis.com/auth/tagmanager.readonly",
    "https://www.googleapis.com/auth/webmasters.readonly",
)

READ_SCOPES = {
    "ga": (
        "https://www.googleapis.com/auth/analytics.readonly",
        "https://www.googleapis.com/auth/analytics.manage.users.readonly",
    ),
    "gtm": ("https://www.googleapis.com/auth/tagmanager.readonly",),
    "gsc": ("https://www.googleapis.com/auth/webmasters.readonly",),
    "gmp_org": ("https://www.googleapis.com/auth/marketingplatformadmin.analytics.read",),
}

SERVICE_ACCOUNT_WRITE_SCOPES = {
    "ga": (
        "https://www.googleapis.com/auth/analytics.manage.users",
        "https://www.googleapis.com/auth/analytics.readonly",
    ),
    "gtm": (
        "https://www.googleapis.com/auth/tagmanager.manage.users",
        "https://www.googleapis.com/auth/tagmanager.readonly",
    ),
    "gsc": ("https://www.googleapis.com/auth/webmasters",),
    "gmp_org": ("https://www.googleapis.com/auth/marketingplatformadmin.analytics.update",),
}


def _sa_email(path: Path | None) -> str | None:
    if not path or not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    email = payload.get("client_email") if isinstance(payload, dict) else None
    return str(email) if email else None


def service_account_email(path: Path | None) -> str | None:
    return _sa_email(path)


def ads_service_account_email(settings: Settings) -> str | None:
    try:
        _ads_credentials_path(settings)
        return ADS_PERSONNEL_SERVICE_ACCOUNT
    except GmpError:
        return None


def _ads_credentials_path(settings: Settings) -> Path:
    """Resolve the personnel identity without ever falling back to Ads delivery auth."""
    path = settings.ads_credentials or settings.gmp_org_credentials or settings.gtm_credentials
    next_step = (
        f"设置 GMP_ADS_CREDENTIALS 指向 {ADS_PERSONNEL_SERVICE_ACCOUNT} 的服务账号密钥；"
        "本项目不使用 Adwords API 的投放身份或通用 OAuth"
    )
    if not path or not path.is_file():
        raise GmpError("找不到 Ads 人员管理专用服务账号密钥。", next_step)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise GmpError("Ads 人员管理服务账号密钥无法读取。", next_step) from exc
    if (
        not isinstance(payload, dict)
        or payload.get("type") != "service_account"
        or str(payload.get("client_email") or "").casefold() != ADS_PERSONNEL_SERVICE_ACCOUNT.casefold()
    ):
        raise GmpError("Ads 人员管理凭据身份不匹配，已拒绝连接。", next_step)
    return path.resolve()


def oauth_identity_email(settings: Settings) -> str | None:
    """Return the authenticated user's email through Google's official OAuth2 API.

    A stored OAuth token changes which identity GA/GTM actually use.  In that
    mode it is unsafe to infer write readiness from the service-account files that
    merely remain configured as a fallback.
    """
    creds = load_oauth_credentials(settings, refresh=True, persist_refresh=True)
    if not creds:
        return None
    from googleapiclient.discovery import build

    payload = (
        build("oauth2", "v2", credentials=creds, cache_discovery=False)
        .userinfo()
        .get()
        .execute()
    )
    email = payload.get("email")
    return str(email) if email else None


def service_account_credentials(path: Path, scopes: tuple[str, ...]) -> Any:
    from google.oauth2 import service_account

    return service_account.Credentials.from_service_account_file(str(path), scopes=list(scopes))


def load_oauth_credentials(
    settings: Settings,
    *,
    require: bool = False,
    refresh: bool = True,
    persist_refresh: bool = True,
) -> Any | None:
    token_file = settings.oauth_token_file
    if not token_file.is_file():
        if require:
            raise GmpError(
                "还没有用户 OAuth token。",
                "运行 gmp auth login，用 GA/GTM 管理员 Google 账号授权；Ads 固定使用专用服务账号",
            )
        return None
    from google.oauth2.credentials import Credentials

    creds = Credentials.from_authorized_user_file(str(token_file))
    if refresh and creds and creds.expired and creds.refresh_token:
        from google.auth.transport.requests import Request

        creds.refresh(Request())
        if persist_refresh:
            token_file.write_text(creds.to_json(), encoding="utf-8")
    if require and (not creds or not creds.valid):
        raise GmpError("管理员 OAuth token 无效或已过期。", "重新运行 gmp auth login")
    return creds


def credentials_for(settings: Settings, product: str, *, write: bool = False) -> Any:
    if product == "ads":
        return ads_client_kwargs(settings)
    oauth = load_oauth_credentials(settings)
    if write:
        if oauth:
            return oauth
        sa_path = {
            "ga": settings.gmp_org_credentials or settings.ga_credentials,
            "gtm": settings.gtm_credentials,
            "gsc": settings.gsc_credentials,
            "gmp_org": settings.gmp_org_credentials,
        }.get(product)
        if sa_path and sa_path.is_file():
            scopes = SERVICE_ACCOUNT_WRITE_SCOPES.get(product, WRITE_SCOPES)
            return service_account_credentials(sa_path, scopes)
        raise GmpError(
            f"{product} 没有可写凭证。",
            "运行 gmp auth login，或把服务账号升级为管理员后再试",
        )
    sa_path = {
        "ga": settings.ga_credentials,
        "gtm": settings.gtm_credentials,
        "gsc": settings.gsc_credentials,
        "gmp_org": settings.gmp_org_credentials,
    }.get(product)
    if sa_path and sa_path.is_file():
        return service_account_credentials(sa_path, READ_SCOPES.get(product, WRITE_SCOPES))
    if oauth:
        return oauth
    raise GmpError(
        f"{product} 没有可读凭证。",
        "在 .env 里设置对应 GMP_*_CREDENTIALS，或运行 gmp auth login",
    )


def ads_client_kwargs(settings: Settings) -> dict[str, Any]:
    key_path = _ads_credentials_path(settings)
    if not settings.ads_yaml or not settings.ads_yaml.is_file():
        raise GmpError("找不到 Google Ads YAML。", "设置 GMP_ADS_YAML 指向 Adwords API 项目的 google-ads.yaml")
    import yaml

    try:
        shared = yaml.safe_load(settings.ads_yaml.read_text(encoding="utf-8")) or {}
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise GmpError("Google Ads YAML 无法读取。", "检查 GMP_ADS_YAML，勿输出密钥文件内容") from exc
    if not isinstance(shared, dict) or not isinstance(shared.get("developer_token"), str) or not shared["developer_token"].strip():
        raise GmpError("Google Ads YAML 缺少 developer_token。", "检查 GMP_ADS_YAML 指向的配置")
    # A strict allowlist prevents shared OAuth, impersonation, ADC, or key paths
    # from silently changing the principal. Never write to the shared YAML.
    return {
        "developer_token": shared["developer_token"],
        "use_proto_plus": shared.get("use_proto_plus", True),
        "login_customer_id": settings.ads_login_customer_id.replace("-", ""),
        "json_key_file_path": str(key_path),
    }


def load_ads_client(settings: Settings):
    from google.ads.googleads.client import GoogleAdsClient

    return GoogleAdsClient.load_from_dict(ads_client_kwargs(settings))


def identity_summary(settings: Settings) -> dict[str, Any]:
    oauth = load_oauth_credentials(settings, refresh=False, persist_refresh=False)
    ads_email = ads_service_account_email(settings)
    return {
        "ga_sa": _sa_email(settings.ga_credentials),
        "gsc_sa": _sa_email(settings.gsc_credentials),
        "gtm_sa": _sa_email(settings.gtm_credentials),
        "gmp_org_sa": _sa_email(settings.gmp_org_credentials),
        "ads_yaml_exists": bool(settings.ads_yaml and settings.ads_yaml.is_file()),
        "ads_sa": ads_email,
        "ads_credential_mode": "service_account",
        "ads_expected_sa": ADS_PERSONNEL_SERVICE_ACCOUNT,
        "ads_identity_valid": ads_email is not None,
        "oauth_token": settings.oauth_token_file.is_file(),
        "oauth_client": bool(settings.oauth_client_id) or settings.oauth_client_file.is_file(),
        "oauth_present": bool(oauth),
        "oauth_valid": bool(oauth and oauth.valid),
    }


def audit_identity_summary(settings: Settings) -> dict[str, Any]:
    """Return credential metadata plus the executing OAuth user's email when available.

    Identity lookup is read-only and best-effort.  A transient userinfo failure must
    not erase the service-account evidence or make an already confirmed plan unsafe
    to audit.
    """
    summary = identity_summary(settings)
    if summary["oauth_present"]:
        try:
            summary["oauth_email"] = oauth_identity_email(settings)
        except Exception as exc:
            summary["oauth_email_error"] = str(exc)
    return summary


def run_oauth_login(settings: Settings) -> dict[str, Any]:
    from google_auth_oauthlib.flow import InstalledAppFlow

    settings.oauth_token_file.parent.mkdir(parents=True, exist_ok=True)
    if settings.oauth_client_file.is_file():
        flow = InstalledAppFlow.from_client_secrets_file(str(settings.oauth_client_file), scopes=list(WRITE_SCOPES))
    elif settings.oauth_client_id and settings.oauth_client_secret:
        flow = InstalledAppFlow.from_client_config(
            {
                "installed": {
                    "client_id": settings.oauth_client_id,
                    "client_secret": settings.oauth_client_secret,
                    "redirect_uris": ["http://localhost"],
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            },
            scopes=list(WRITE_SCOPES),
        )
    else:
        raise GmpError(
            "没有 OAuth 客户端。",
            "在 Google Cloud 创建一个 Desktop OAuth client，保存为 credentials/oauth-client.json，"
            "或设置 GMP_OAUTH_CLIENT_ID / GMP_OAUTH_CLIENT_SECRET。授权账号必须是 GA/GTM 管理员；Ads 固定使用专用服务账号",
        )
    creds = flow.run_local_server(port=0, prompt="consent")
    settings.oauth_token_file.write_text(creds.to_json(), encoding="utf-8")
    return {
        "ok": True,
        "token_file": str(settings.oauth_token_file),
        "scopes": list(WRITE_SCOPES),
        "next_step": "再运行 gmp doctor，检查 GA/GTM 的权限；Ads 固定使用专用服务账号，不受本次 OAuth 登录影响",
    }
