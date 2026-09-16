import logging

from .config import AgentError, credentials


class SlsReader:
    """Expose only index inspection and bounded GetLogs requests."""

    def __init__(self, config):
        from aliyun.log import LogClient
        key, secret, token, self.credential_source = credentials()
        self.config = config
        # SDK exception/debug messages can include query content or response bodies.
        logging.getLogger("aliyun.log").setLevel(logging.CRITICAL)
        self.client = LogClient(config["endpoint"], key, secret, securityToken=token or None,
                                region=config["region"], source="log-checker")
        self.client.timeout = config["timeout_seconds"]

    def _call(self, method, *args):
        from aliyun.log import LogException
        try:
            return method(*args)
        except LogException as exc:
            code = exc.get_error_code()
            # Do not emit SDK message, headers, body, or a traceback containing credentials.
            import re
            code = code if re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", code or "") else "sls_error"
            raise AgentError(code, "SLS 查询失败；核对地域、RAM 只读权限、凭据有效期及字段索引。", exc.get_request_id()) from None
        except Exception:
            raise AgentError("connection_error", "无法完成 SLS 请求；检查网络、代理及 endpoint。") from None

    def schema(self):
        c = self.config
        response = self._call(self.client.get_index_config, c["project"], c["logstore"])
        raw = response.get_index_config().to_json()
        fields = {name: {"type": item.get("type"), "sql_enabled": item.get("doc_value", False)}
                  for name, item in raw.get("keys", {}).items()}
        return {"fields": fields, "request_id": response.get_request_id()}

    def query(self, sql, start, end, limit=100):
        from aliyun.log import GetLogsRequest
        if not (0 < end - start <= 86400 and 1 <= limit <= 200):
            raise AgentError("invalid_window", "单次查询范围须为 1 秒至 24 小时，返回上限为 200 行。")
        c = self.config
        request = GetLogsRequest(c["project"], c["logstore"], start, end, "", sql,
                                 line=limit, reverse=False, power_sql=False)
        response = self._call(self.client.get_logs, request)
        if not response.is_completed():
            raise AgentError("incomplete_query", "SLS 返回不完整结果；本次不判断网站正常，也不解除已有告警。", response.get_request_id())
        return {"rows": [log.get_contents() for log in response.get_logs()][:limit],
                "request_id": response.get_request_id(), "complete": True}
