from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    property_id: str
    properties: dict[str, str]
    credentials_path: str | None

    def resolve_property_name(self, property: str | None = None) -> str:
        value = (property or self.property_id).strip()
        normalized = normalize_property_alias(value)
        if not value.removeprefix("properties/").isdigit():
            if normalized not in self.properties:
                choices = ", ".join(sorted(self.properties))
                raise ValueError(
                    f"未知 GA4 Property：{property}。可用站点：{choices}，也可以传数字 Property ID。"
                )
            value = self.properties[normalized]
        return value if value.startswith("properties/") else f"properties/{value}"


def normalize_property_alias(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def get_settings(*, require_ga4: bool = True) -> Settings:
    # Reload newly created values in long-lived Cursor/Codex MCP processes.
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    property_id = os.getenv("GA4_PROPERTY_ID", "").strip()
    credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    properties = {
        normalize_property_alias(name.removeprefix("GA4_PROPERTY_")): value.strip()
        for name, value in os.environ.items()
        if name.startswith("GA4_PROPERTY_")
        and name != "GA4_PROPERTY_ID"
        and value.strip()
    }
    if property_id:
        properties.setdefault("demo", property_id)

    if require_ga4 and not property_id:
        raise RuntimeError(
            "缺少 GA4_PROPERTY_ID。请复制 .env.example 为 .env，并填入数字 Property ID。"
        )
    if require_ga4 and property_id and not property_id.removeprefix("properties/").isdigit():
        raise RuntimeError(
            "GA4_PROPERTY_ID 必须是数字 Property ID（不是 G-XXXX Measurement ID）。"
        )
    if require_ga4 and credentials_path and not Path(credentials_path).expanduser().is_file():
        raise RuntimeError(
            "GOOGLE_APPLICATION_CREDENTIALS 指向的文件不存在："
            f"{credentials_path}"
        )
    invalid_properties = {
        alias: value
        for alias, value in properties.items()
        if not value.removeprefix("properties/").isdigit()
    }
    if invalid_properties:
        invalid_aliases = ", ".join(sorted(invalid_properties))
        raise RuntimeError(f"这些 GA4 Property ID 不是数字：{invalid_aliases}")

    return Settings(
        property_id=property_id,
        properties=properties,
        credentials_path=credentials_path,
    )
