import json
import math
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class AgentError(Exception):
    def __init__(self, code, message, request_id=None):
        super().__init__(message)
        self.code, self.message, self.request_id = code, message, request_id

    def as_dict(self):
        return {"status": "error", "code": self.code, "message": self.message,
                "request_id": self.request_id}


def load_config(path=None):
    path = Path(path) if path else ROOT / "config.json"
    if path == ROOT / "config.json" and not path.is_file():
        path = ROOT / "config.example.json"
    try:
        config = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(config, dict):
            raise ValueError()
        validate(config)
        return config
    except (OSError, ValueError, KeyError, TypeError):
        raise AgentError("invalid_config", "配置无效；请检查 JSON、字段名、HTTPS endpoint 和阈值范围。") from None


def validate(c):
    for name in ("project", "logstore"):
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,62}", c[name]):
            raise ValueError()
    if not re.fullmatch(r"https://[a-z0-9-]+\.log\.aliyuncs\.com", c["endpoint"]):
        raise ValueError()
    if c["endpoint"] != f'https://{c["region"]}.log.aliyuncs.com':
        raise ValueError()
    for role in ("status", "latency", "path", "ip", "user_agent"):
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", c["fields"][role]):
            raise ValueError()
    if c["latency_unit"] not in ("seconds", "milliseconds") or type(c["schema_verified"]) is not bool:
        raise ValueError()
    for key, lo, hi in (("window_minutes", 1, 1440), ("ingestion_delay_seconds", 0, 3600),
                        ("poll_seconds", 60, 86400), ("timeout_seconds", 1, 60)):
        if type(c[key]) is not int or not lo <= c[key] <= hi:
            raise ValueError()
    t = c["thresholds"]
    for key in ("minimum_requests", "minimum_field_coverage", "server_error_rate", "not_found_rate",
                "rate_limited_rate", "p95_seconds", "slow_seconds", "traffic_drop_ratio", "traffic_spike_ratio"):
        if type(t[key]) not in (int, float) or not math.isfinite(t[key]) or t[key] <= 0:
            raise ValueError()
    for key in ("minimum_field_coverage", "server_error_rate", "not_found_rate", "rate_limited_rate"):
        if t[key] > 1:
            raise ValueError()
    if type(t["minimum_requests"]) is not int or not 0 < t["traffic_drop_ratio"] < 1 < t["traffic_spike_ratio"]:
        raise ValueError()


def credentials():
    # Only this runtime loader handles secrets; no config dump or secret-bearing errors.
    from dotenv import dotenv_values
    env_file = Path(os.environ.get("LOG_CHECKER_ENV_FILE", str(ROOT / ".env")))
    values = dotenv_values(env_file) if env_file.is_file() else {}
    names = ("ALIBABA_CLOUD_ACCESS_KEY_ID", "ALIBABA_CLOUD_ACCESS_KEY_SECRET", "ALIBABA_CLOUD_SECURITY_TOKEN")
    # Do not mix a partial environment identity with secrets from a different file.
    source = "environment" if any(os.environ.get(n) for n in names) else "local_env_file"
    resolved = [os.environ.get(n, "") if source == "environment" else (values.get(n) or "") for n in names]
    if not resolved[0] or not resolved[1]:
        raise AgentError("credentials_missing", "缺少本机 SLS 只读凭据；在本地 .env 或进程环境中配置完整 AK/SK，STS 另需 token。")
    return (*resolved, source)
