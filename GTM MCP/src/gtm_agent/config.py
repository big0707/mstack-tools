from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CREDENTIAL_KEYS = ("client_email", "project_id", "type")


def load_project_env() -> Path:
    """Load `.env` from the project root. Safe to call repeatedly."""
    env_path = PROJECT_ROOT / ".env"
    load_dotenv(env_path, override=False)
    return env_path


def normalize_alias(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None or not value.strip():
        return default
    return value.strip().casefold() in {"1", "true", "yes", "on"}


def is_public_container_id(value: str) -> bool:
    return bool(re.fullmatch(r"GTM-[A-Z0-9]+", value.strip(), flags=re.IGNORECASE))


def is_numeric_id(value: str) -> bool:
    return value.strip().isdigit()


@dataclass(frozen=True)
class Settings:
    account_id: str
    container_id: str
    workspace_id: str
    containers: dict[str, str]
    credentials_path: str | None
    read_only: bool

    def resolve_container_query(self, container: str | None = None) -> str:
        value = (container or self.container_id or "").strip()
        if not value:
            raise ValueError(
                "未指定容器。请传入 GTM-XXXX、数字 containerId、站点别名，"
                "或在 .env 中设置 GTM_CONTAINER_ID。"
            )
        if value.startswith("accounts/"):
            return value
        if is_public_container_id(value) or is_numeric_id(value):
            return value
        alias = normalize_alias(value)
        if alias in self.containers:
            return self.containers[alias]
        choices = ", ".join(sorted(self.containers)) or "(无已配置别名)"
        raise ValueError(
            f"未知 GTM 容器：{container}。可用站点别名：{choices}；"
            "也可以传 GTM-XXXX 或数字 containerId。"
        )


def get_settings(*, require_credentials: bool = True) -> Settings:
    load_project_env()
    account_id = os.getenv("GTM_ACCOUNT_ID", "").strip()
    container_id = os.getenv("GTM_CONTAINER_ID", "").strip()
    workspace_id = os.getenv("GTM_WORKSPACE_ID", "").strip()
    credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip() or None
    read_only = parse_bool(os.getenv("GTM_READ_ONLY"), default=False)
    containers = {
        normalize_alias(name.removeprefix("GTM_CONTAINER_")): value.strip()
        for name, value in os.environ.items()
        if name.startswith("GTM_CONTAINER_")
        and name != "GTM_CONTAINER_ID"
        and value.strip()
    }
    if container_id:
        containers.setdefault("default", container_id)

    if require_credentials and not credentials_path:
        raise RuntimeError(
            "缺少 GOOGLE_APPLICATION_CREDENTIALS。请复制 .env.example 为 .env，"
            "并填入服务账号 JSON 的绝对路径。"
        )
    if require_credentials and credentials_path:
        expanded = Path(credentials_path).expanduser()
        if not expanded.is_file():
            raise RuntimeError(
                "GOOGLE_APPLICATION_CREDENTIALS 指向的文件不存在："
                f"{credentials_path}"
            )

    return Settings(
        account_id=account_id,
        container_id=container_id,
        workspace_id=workspace_id,
        containers=containers,
        credentials_path=credentials_path,
        read_only=read_only,
    )


def read_service_account_identity(credentials_path: str | None) -> dict[str, str]:
    """Return public identity fields only. Never include private_key."""
    if not credentials_path:
        return {}
    path = Path(credentials_path).expanduser()
    if not path.is_file():
        return {"credentials_path_exists": "false"}

    import json

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"无法读取服务账号 JSON：{exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("服务账号 JSON 必须是对象。")

    identity = {
        key: str(payload[key])
        for key in CREDENTIAL_KEYS
        if key in payload and payload[key]
    }
    identity["credentials_path_exists"] = "true"
    return identity
