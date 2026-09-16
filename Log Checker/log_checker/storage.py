import hashlib
import json
import os
from contextlib import contextmanager
from pathlib import Path

from .config import AgentError, ROOT


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    try:
        tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def state_key(c):
    return hashlib.sha256(json.dumps(c, sort_keys=True).encode()).hexdigest()[:16]


def load_state(c):
    path = ROOT / "state" / (state_key(c) + ".json")
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or not isinstance(value.get("active", {}), dict):
            raise ValueError()
        if any(not isinstance(item, dict) for item in value.get("active", {}).values()):
            raise ValueError()
        if type(value.get("last_window_end", 0)) is not int:
            raise ValueError()
        return value
    except (ValueError, OSError):
        raise AgentError("invalid_state", "告警状态文件损坏；先保留文件排查，禁止当成首次运行重置。") from None


def save_state(c, state):
    atomic_json(ROOT / "state" / (state_key(c) + ".json"), state)


def append_events(c, events):
    if not events:
        return
    folder = ROOT / "state"
    folder.mkdir(exist_ok=True)
    path = folder / (state_key(c) + "-events.jsonl")
    # Retain one previous 5 MiB event journal, plus the current journal.
    if path.exists() and path.stat().st_size >= 5 * 1024 * 1024:
        os.replace(path, path.with_suffix(".previous.jsonl"))
    with path.open("a", encoding="utf-8") as stream:
        for event in events:
            stream.write(json.dumps(event, ensure_ascii=False) + "\n")


@contextmanager
def check_lock():
    folder = ROOT / "state"
    folder.mkdir(exist_ok=True)
    with (folder / "check.lock").open("a+b") as stream:
        stream.seek(0)
        if os.name == "nt":
            import msvcrt
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise AgentError("already_running", "另一个 check 正在运行，请稍后重试。") from None
            try:
                yield
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise AgentError("already_running", "另一个 check 正在运行，请稍后重试。") from None
            try:
                yield
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)
