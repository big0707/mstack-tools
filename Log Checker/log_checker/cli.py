import argparse
import json
import sys
import time
from datetime import datetime, timezone

from .api import SlsReader
from .config import AgentError, ROOT, credentials, load_config
from .metrics import evaluate, normalize, transition
from .queries import PRESETS, build_query
from .storage import append_events, atomic_json, check_lock, load_state, save_state, state_key


def utc(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat().replace("+00:00", "Z")


def emit(value):
    print(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), flush=True)


def target(c):
    return {k: c[k] for k in ("project", "logstore", "region", "endpoint")}


def window(c, minutes=None, end=None):
    minutes = minutes or c["window_minutes"]
    end = end if end is not None else int(time.time()) - c["ingestion_delay_seconds"]
    return end - minutes * 60, end


def read_report(c, reader, minutes=None, end=None):
    start, end = window(c, minutes, end)
    sql = build_query(c)
    recent = reader.query(sql, start, end, 1)
    baseline = reader.query(sql, start - (end - start), start, 1)
    current, previous = normalize(recent["rows"]), normalize(baseline["rows"])
    findings, assessed = evaluate(current, previous, c)
    if not c["schema_verified"]:
        findings.append({"rule": "schema_unverified", "severity": "warning",
                         "message": "字段映射和延迟单位尚未人工核实；当前仅为诊断报告，不能启动持续监控。"})
    status = "critical" if any(f["severity"] == "critical" for f in findings) else "warning" if findings else "ok"
    return {"status": status, "source": "aliyun_sls", "target": target(c), "generated_at": utc(int(time.time())),
            "window": {"start": utc(start), "end": utc(end), "end_epoch": end, "minutes": (end - start) // 60},
            "baseline_window": {"start": utc(start - (end - start)), "end": utc(start)},
            "ingestion_delay_seconds": c["ingestion_delay_seconds"], "current": current, "previous": previous,
            "findings": findings, "assessed_rules": assessed,
            "request_ids": [recent["request_id"], baseline["request_id"]]}


def markdown(report):
    lines = ["# 日志检查", "", f"状态：**{report['status']}**；来源：{report.get('source', 'unknown')}",
             f"生成时间：{report['generated_at']}（UTC）", ""]
    if report.get("source") == "demo":
        lines += ["> 演示数据，不代表网站实际状态。", ""]
    if "error" in report:
        lines += [f"查询失败：{report['error']['code']} — {report['error']['message']}"]
    else:
        c = report["current"]
        fmt = lambda v: "不可判断" if v is None else f"{v:.2%}"
        p95 = "不可判断" if c["p95_seconds"] is None else f"{c['p95_seconds']:.3f} 秒"
        lines += [f"资源：`{report['target']['project']}/{report['target']['logstore']}`",
                  f"窗口：{report['window']['start']} 至 {report['window']['end']}", "",
                  "| 指标 | 当前值 |", "|---|---:|", f"| 请求量 | {c['total']} |",
                  f"| 5xx 比例 | {fmt(c['server_error_rate'])} |", f"| 404 比例 | {fmt(c['not_found_rate'])} |",
                  f"| 429 比例 | {fmt(c['rate_limited_rate'])} |", f"| P95 | {p95} |",
                  f"| 慢请求数 | {c['slow_requests']} |", f"| 前一窗口请求量 | {report['previous']['total']} |", ""]
        lines += [f"- {f['message']}" for f in report["findings"]] or ["本次已评估规则均未触发。"]
    if report.get("unverified_active"):
        lines += ["", "仍有历史告警因本次数据不足而未能核实恢复：" + ", ".join(report["unverified_active"])]
    lines += ["", "流量基线仅为前一相同长度窗口；告警是排查线索，不能据此直接认定攻击或封禁 IP。", ""]
    return "\n".join(lines)


def save_report(report, demo=False):
    folder = ROOT / "outputs" / ("demo" if demo else "latest")
    atomic_json(folder / "report.json", report)
    (folder / "report.md").write_text(markdown(report), encoding="utf-8")
    return str(folder / "report.md")


def check_once(c):
    if not c["schema_verified"]:
        raise AgentError("schema_unverified", "先运行 doctor --online 和 schema，核实字段映射及延迟单位后设置 schema_verified=true。")
    with check_lock():
        state = load_state(c)
        now = int(time.time())
        end = ((now - c["ingestion_delay_seconds"]) // c["poll_seconds"]) * c["poll_seconds"]
        if end <= state.get("last_window_end", 0):
            return {"status": "skipped", "reason": "该窗口已检查；旧窗口不重放告警。", "events": []}, 0
        try:
            report = read_report(c, SlsReader(c), end=end)
        except AgentError as error:
            finding = {"rule": "query_error", "severity": "critical", "message": f"日志查询不可用（{error.code}）；网站状态未知。"}
            state, events = transition(state, [finding], [], utc(now))
            report = {"status": "error", "source": "aliyun_sls", "target": target(c), "generated_at": utc(now),
                      "error": error.as_dict(), "events": events, "active_alerts": list(state["active"].values())}
            exit_code = 2
        else:
            state, events = transition(state, report["findings"], report["assessed_rules"] + ["query_error"], utc(now))
            state["last_window_end"] = end
            report["events"] = events
            report["active_alerts"] = list(state["active"].values())
            report["unverified_active"] = sorted(set(state["active"]) - set(report["assessed_rules"]) - {"query_error"})
            if report["unverified_active"] and report["status"] == "ok":
                report["status"] = "warning"
            exit_code = 1 if state["active"] else 0
        report["state_id"] = state_key(c)
        report["report_path"] = save_report(report)
        # Persist the latest report (including transitions) before advancing dedup state.
        append_events(c, report["events"])
        save_state(c, state)
        return report, exit_code


def doctor(c, online=False):
    result = {"status": "configuration_needed", "target": target(c), "network_checked": False,
              "schema_verified": c["schema_verified"], "runtime": sys.version.split()[0]}
    try:
        *_, source = credentials()
        result["credentials"] = {"present": True, "source": source}
    except AgentError as error:
        result["credentials"] = {"present": False}
        result["next_step"] = error.message
        return result, 2
    if not online:
        result["status"] = "local_ready"
        result["next_step"] = "运行 doctor --online 核验权限、索引和数据；本次未连接阿里云。"
        return result, 0
    reader = SlsReader(c)
    result["schema"] = reader.schema()
    result["missing_configured_fields"] = [name for name in c["fields"].values() if name not in result["schema"]["fields"]]
    start, end = window(c)
    probe = reader.query(build_query(c), start, end, 1)
    result.update(network_checked=True, metrics=normalize(probe["rows"]), query_request_id=probe["request_id"])
    result["status"] = "connected"
    result["next_step"] = "核实 status/request_time 等映射和延迟单位；确认后在配置中设置 schema_verified=true。"
    return result, 0


def demo(c):
    from copy import deepcopy
    demo_config = deepcopy(c)
    demo_config["schema_verified"] = True
    class DemoReader:
        def query(self, sql, start, end, limit):
            return {"rows": [{"total": "1000", "valid_status": "1000", "server_errors": "35",
                              "not_found": "120", "rate_limited": "2", "latency_samples": "1000",
                              "slow_requests": "90", "p95_seconds": "2.8"}], "request_id": "DEMO-NOT-LIVE"}
    report = read_report(demo_config, DemoReader())
    report["source"] = "demo"
    report["report_path"] = save_report(report, demo=True)
    return report


def bounded_int(low, high):
    def parse(value):
        try:
            n = int(value)
        except ValueError:
            raise argparse.ArgumentTypeError("必须是整数") from None
        if not low <= n <= high:
            raise argparse.ArgumentTypeError(f"必须在 {low} 至 {high} 之间")
        return n
    return parse


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="阿里云 SLS 网站日志 Agent（只读 CLI）")
    parser.add_argument("--config", help="配置 JSON 路径；默认使用项目 config.json")
    sub = parser.add_subparsers(dest="command", required=True)
    diag = sub.add_parser("doctor", help="检查配置和凭据是否齐全；不输出密钥")
    diag.add_argument("--online", action="store_true", help="实际核验 SLS 索引读取和聚合查询")
    sub.add_parser("schema", help="读取字段名、类型和 SQL 索引状态")
    query = sub.add_parser("query", help="按预设执行有界聚合查询，不返回完整原始日志")
    query.add_argument("--preset", choices=PRESETS, default="errors")
    query.add_argument("--minutes", type=bounded_int(1, 1440))
    query.add_argument("--limit", type=bounded_int(1, 200), default=20)
    query.add_argument("--show-sql", action="store_true", help="仅输出 SQL，不连接 SLS")
    report = sub.add_parser("report", help="比较当前和前一窗口，保存 JSON/Markdown 诊断报告")
    report.add_argument("--minutes", type=bounded_int(1, 1440))
    sub.add_parser("check", help="检查一个对齐窗口，保存告警与恢复事件并去重")
    watch = sub.add_parser("watch", help="前台持续检查；Ctrl+C 停止，不安装系统任务")
    watch.add_argument("--cycles", type=bounded_int(1, 10000), help="最多运行轮数；省略则持续运行")
    sub.add_parser("demo", help="离线演示，独立目录保存；不读凭据或影响正式告警状态")
    args = parser.parse_args(argv)
    try:
        c = load_config(args.config)
        if args.command == "doctor":
            value, code = doctor(c, args.online)
            emit(value)
            return code
        if args.command == "demo":
            emit(demo(c))
            return 0
        if args.command == "schema":
            emit({"target": target(c), **SlsReader(c).schema()})
            return 0
        if args.command == "query":
            sql = build_query(c, args.preset, args.limit)
            if args.show_sql:
                print(sql)
                return 0
            start, end = window(c, args.minutes)
            emit({"target": target(c), "preset": args.preset, "window": {"start": utc(start), "end": utc(end)},
                  **SlsReader(c).query(sql, start, end, args.limit)})
            return 0
        if args.command == "report":
            result = read_report(c, SlsReader(c), args.minutes)
            result["report_path"] = save_report(result)
            emit(result)
            return 1 if result["findings"] else 0
        if args.command == "check":
            value, code = check_once(c)
            emit(value)
            return code
        cycle, code = 0, 0
        while True:
            value, code = check_once(c)
            # Unchanged runs stay quiet; first run gives a startup snapshot.
            if cycle == 0 or value.get("events"):
                emit(value)
            cycle += 1
            if args.cycles and cycle >= args.cycles:
                return code
            time.sleep(c["poll_seconds"])
    except AgentError as error:
        emit(error.as_dict())
        return 2
    except KeyboardInterrupt:
        emit({"status": "stopped", "message": "监控已停止。"})
        return 130
    except Exception as error:
        # Fail closed without printing arbitrary SDK responses or credential contents.
        emit({"status": "error", "code": "local_error", "error_type": type(error).__name__,
              "message": "本地运行失败；检查依赖、文件权限和配置。未确认网站状态。"})
        return 2
