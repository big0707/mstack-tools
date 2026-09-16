# 本地验证记录

验证日期：2026-09-04。范围：本地 CLI、官方 SDK 适配、告警逻辑和本地持久化。

- Python：3.12.14；独立虚拟环境 `.venv`。
- 依赖：`aliyun-log-python-sdk==0.9.50`、`python-dotenv==1.2.3`。
- `python -m pip check`：通过，无依赖冲突。
- `python -m unittest discover -s tests -v`：14 项通过。
- `log-checker.cmd --help`：正常列出 8 个命令。
- `log-checker.cmd doctor`：如实返回 `configuration_needed`、`credentials.present=false`、`network_checked=false`。
- `log-checker.cmd demo`：生成独立的 `outputs/demo/report.json` 和 `report.md`，内容标明演示数据。
- `log-checker.cmd query --preset overview --show-sql`、`query --preset bots --show-sql`：能够离线输出实际查询 SQL。
- `log-checker.cmd check`：在字段未核验时拒绝启动，返回 `schema_unverified`。

测试使用官方 SDK 的实际请求/响应类以及本地构造的返回值；完整验证了异常→去重→查询失败→恢复的状态和事件落盘、低样本/无数据/字段覆盖不足时不误解除告警、失败内容不输出凭据或 SDK 原始错误正文。

尚未验证：真实阿里云权限、地域、字段索引、SLS SQL 执行、日志内容及延迟单位。用户明确选择暂不提供凭据，先完成 Agent 和配置说明。未启动持续监控、系统调度或任何通知通道。
