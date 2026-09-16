from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


DEFAULT_CONFIG_PATH = Path("config.yaml")


@dataclass(frozen=True)
class FeishuConfig:
    cli_path: str = "feishu"
    default_chat_id: str | None = None
    send_command: list[str] = field(
        default_factory=lambda: [
            "{cli_path}",
            "send",
            "--chat-id",
            "{chat_id}",
            "--file",
            "{file}",
        ]
    )


@dataclass(frozen=True)
class AppConfig:
    google_ads_yaml_path: str = "google-ads.yaml"
    google_ads_api_version: str = "v24"
    default_customer_id: str | None = None
    reports_dir: str = "reports"
    feishu: FeishuConfig = field(default_factory=FeishuConfig)


def load_config(path: str | Path | None = None) -> AppConfig:
    config_path = Path(path or os.getenv("ADWORDS_AGENT_CONFIG", DEFAULT_CONFIG_PATH))
    raw: dict[str, Any] = {}
    if config_path.exists():
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}

    google_ads = raw.get("google_ads", {})
    reports = raw.get("reports", {})
    feishu = raw.get("feishu", {})

    return AppConfig(
        google_ads_yaml_path=os.getenv(
            "GOOGLE_ADS_CONFIGURATION_FILE_PATH",
            str(google_ads.get("yaml_path", "google-ads.yaml")),
        ),
        google_ads_api_version=os.getenv(
            "GOOGLE_ADS_API_VERSION",
            str(google_ads.get("api_version", "v24")),
        ),
        default_customer_id=os.getenv(
            "GOOGLE_ADS_CUSTOMER_ID", google_ads.get("default_customer_id")
        ),
        reports_dir=str(reports.get("dir", "reports")),
        feishu=FeishuConfig(
            cli_path=os.getenv("FEISHU_CLI", str(feishu.get("cli_path", "feishu"))),
            default_chat_id=os.getenv(
                "FEISHU_CHAT_ID", feishu.get("default_chat_id")
            ),
            send_command=list(
                feishu.get(
                    "send_command",
                    [
                        "{cli_path}",
                        "send",
                        "--chat-id",
                        "{chat_id}",
                        "--file",
                        "{file}",
                    ],
                )
            ),
        ),
    )
