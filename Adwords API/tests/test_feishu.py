import os
from pathlib import Path

from adwords_agent.config import FeishuConfig
from adwords_agent.feishu import build_feishu_command


def test_build_feishu_command_uses_template() -> None:
    config = FeishuConfig(
        cli_path="feishu",
        default_chat_id="oc_xxx",
        send_command=[
            "{cli_path}",
            "send",
            "--chat-id",
            "{chat_id}",
            "--file",
            "{file}",
        ],
    )

    report_path = Path("reports/report.md")
    command = build_feishu_command(
        config,
        chat_id="oc_123",
        file=report_path,
    )

    assert command == [
        "feishu",
        "send",
        "--chat-id",
        "oc_123",
        "--file",
        os.fspath(report_path),
    ]
