from __future__ import annotations

import subprocess
from pathlib import Path
from shutil import which

from .config import FeishuConfig


class FeishuDeliveryError(RuntimeError):
    """Raised when the Feishu CLI exits unsuccessfully."""


def build_feishu_command(config: FeishuConfig, *, chat_id: str, file: str | Path) -> list[str]:
    values = {
        "cli_path": config.cli_path,
        "chat_id": chat_id,
        "file": str(file),
    }
    return [part.format(**values) for part in config.send_command]


def send_file(
    config: FeishuConfig,
    *,
    file: str | Path,
    chat_id: str | None = None,
    dry_run: bool = False,
) -> str:
    target_chat_id = chat_id or config.default_chat_id
    if not target_chat_id:
        raise FeishuDeliveryError("Feishu chat_id is required.")

    if not Path(file).exists():
        raise FeishuDeliveryError(f"Report file not found: {file}")

    command = build_feishu_command(config, chat_id=target_chat_id, file=file)
    if dry_run:
        return " ".join(command)

    executable = command[0]
    if which(executable) is None and not Path(executable).exists():
        raise FeishuDeliveryError(
            f"Feishu CLI executable not found: {executable}. "
            "Set feishu.cli_path in config.yaml to the real CLI path."
        )

    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        raise FeishuDeliveryError(
            f"Feishu CLI failed with code {completed.returncode}: {completed.stderr.strip()}"
        )
    return completed.stdout.strip()
