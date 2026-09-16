from __future__ import annotations

import json
import sys
from typing import Any


def ensure_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def dump(payload: Any, *, ok: bool = True, exit_code: int | None = None) -> int:
    ensure_utf8()
    text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write(text + "\n")
    if exit_code is not None:
        return exit_code
    return 0 if ok else 1
