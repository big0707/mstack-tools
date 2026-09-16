import math

from .config import AgentError

COUNTS = ("total", "valid_status", "server_errors", "not_found", "rate_limited", "latency_samples", "slow_requests")


def normalize(rows):
    # A count(*) aggregate must yield one row even for an empty log interval.
    if len(rows) != 1:
        raise AgentError("invalid_metrics", "聚合未返回唯一一行；不能把空结果当成零流量。")
    raw = rows[0]
    try:
        result = {}
        for key in COUNTS:
            value = float(raw[key])
            if not math.isfinite(value) or value < 0 or not value.is_integer():
                raise ValueError()
            result[key] = int(value)
        n = result["total"]
        if any(result[key] > n for key in COUNTS[1:]):
            raise ValueError()
        if sum(result[k] for k in ("server_errors", "not_found", "rate_limited")) > result["valid_status"]:
            raise ValueError()
        if result["slow_requests"] > result["latency_samples"]:
            raise ValueError()
        p95 = raw.get("p95_seconds")
        result["p95_seconds"] = None if p95 in (None, "", "null", "NULL") else float(p95)
        if result["p95_seconds"] is not None and (not math.isfinite(result["p95_seconds"]) or result["p95_seconds"] < 0):
            raise ValueError()
        if result["latency_samples"] > 0 and result["p95_seconds"] is None:
            raise ValueError()
        for key, count in (("server_error_rate", "server_errors"), ("not_found_rate", "not_found"),
                           ("rate_limited_rate", "rate_limited"), ("status_coverage", "valid_status"),
                           ("latency_coverage", "latency_samples")):
            result[key] = result[count] / n if n else None
        return result
    except (ValueError, TypeError, KeyError, OverflowError):
        raise AgentError("invalid_metrics", "聚合字段缺失或数值无效；请核对字段映射和 SQL 索引。") from None


def evaluate(current, previous, c):
    t = c["thresholds"]
    findings, assessed = [], {"no_data"}

    def issue(rule, severity, message):
        findings.append({"rule": rule, "severity": severity, "message": message})

    if not current["total"]:
        issue("no_data", "warning", "当前窗口没有日志；可能是采集中断、延迟或没有请求，需核实。")
        return findings, sorted(assessed)
    assessed.add("sample_size")
    eligible = current["total"] >= t["minimum_requests"]
    if not eligible:
        issue("sample_size", "warning", f"当前仅 {current['total']} 条日志；不足 {t['minimum_requests']} 条，不判断错误率和延迟恢复。")
    for group in ("status", "latency"):
        assessed.add(group + "_coverage")
        if current[group + "_coverage"] < t["minimum_field_coverage"]:
            issue(group + "_coverage", "warning", f"{group} 有效字段覆盖率不足，相关规则暂停判断。")
    if eligible and current["status_coverage"] >= t["minimum_field_coverage"]:
        for rule, label in (("server_error_rate", "5xx 比例"), ("not_found_rate", "404 比例"), ("rate_limited_rate", "429 比例")):
            assessed.add(rule)
            if current[rule] >= t[rule]:
                issue(rule, "critical" if rule == "server_error_rate" else "warning",
                      f"{label} {current[rule]:.2%}，达到阈值 {t[rule]:.2%}。")
    if eligible and current["latency_coverage"] >= t["minimum_field_coverage"]:
        assessed.add("p95_seconds")
        if current["p95_seconds"] > t["p95_seconds"]:
            issue("p95_seconds", "warning", f"P95 {current['p95_seconds']:.3f} 秒，超过 {t['p95_seconds']} 秒。")
    assessed.add("traffic_baseline")
    if previous["total"] >= t["minimum_requests"]:
        assessed.update(("traffic_drop", "traffic_spike"))
        ratio = current["total"] / previous["total"]
        if ratio < t["traffic_drop_ratio"]:
            issue("traffic_drop", "warning", f"流量为前一相同长度窗口的 {ratio:.1%}。")
        if ratio > t["traffic_spike_ratio"]:
            issue("traffic_spike", "warning", f"流量为前一相同长度窗口的 {ratio:.2f} 倍；需核实访问来源。")
    else:
        issue("traffic_baseline", "warning", "前一窗口样本不足，暂停流量突增/下降判断。")
    return findings, sorted(assessed)


def transition(previous_state, findings, assessed, observed_at):
    """Recover only explicitly assessed rules. API failures never clear site alerts."""
    active = dict(previous_state.get("active", {}))
    fresh = {item["rule"]: item for item in findings}
    events = []
    for rule, finding in fresh.items():
        old = active.get(rule)
        if old is None or old.get("severity") != finding["severity"]:
            events.append({"kind": "opened" if old is None else "changed", "at": observed_at, **finding})
        active[rule] = finding
    for rule in list(active):
        if rule in assessed and rule not in fresh:
            events.append({"kind": "recovered", "at": observed_at, "rule": rule,
                           "severity": "info", "message": "查询已恢复。" if rule == "query_error" else "该项已回到阈值内。"})
            del active[rule]
    return {**previous_state, "active": active}, events
