# Log Checker · 网站日志 Agent

在这个文件夹中通过本地 CLI 查询阿里云 SLS 日志。所有云端操作都走官方 Python SDK 只读访问。

复制 `config.example.json` 为 `config.json`，填入你们自己的 Project / Logstore / 地域。凭据放在 `.env`，不要提交。

## 接通步骤

### 1. 检查环境

本机已创建独立 `.venv` 并安装依赖，直接运行：

```powershell
cd '.\Log Checker'
.\log-checker.cmd doctor
```

如在另一台电脑使用，先准备 Python 3.10+：

```powershell
.\scripts\setup.ps1 -PythonExe 'C:\实际路径\python.exe'
```

该脚本只安装本项目依赖。没有凭据时 `doctor` 返回退出码 2 属于正常提示，不代表安装失败。

### 2. 配置阿里云只读凭据

请管理员为专用 RAM 身份提供目标日志库的**日志查询与索引读取权限**，尽量限制到上表资源。可以让管理员评估官方 `AliyunLogReadOnlyAccess` 只读策略及其授权范围；本项目不自动创建身份、授权或索引。网页登录状态不会自动成为 SDK 凭据。

仅在本机将 `.env.example` 复制为 `.env`，用文本编辑器填写：

```powershell
if (-not (Test-Path -LiteralPath '.env')) {
    Copy-Item -LiteralPath '.env.example' -Destination '.env'
}
```

- `ALIBABA_CLOUD_ACCESS_KEY_ID`：AccessKey ID。
- `ALIBABA_CLOUD_ACCESS_KEY_SECRET`：AccessKey Secret。
- `ALIBABA_CLOUD_SECURITY_TOKEN`：仅使用 STS 临时凭据时填写；过期后需更新完整凭据。

不要把密钥发到聊天里，也不要把 `.env` 分享或提交到 Git。本项目 `.gitignore` 已排除它。如果凭据已有专用本地文件，可在当前 PowerShell 设置 `$env:LOG_CHECKER_ENV_FILE = 'C:\实际路径\sls.env'`。

运行时支持完整的进程环境变量或上述本地 `.env`；只要进程环境存在任一凭据变量，就要求该环境中的凭据完整，避免不同身份混配。目前**不直接加载 aliyun CLI profiles、不自动刷新 STS**。

### 3. 核验资源与字段

```powershell
.\log-checker.cmd doctor --online
.\log-checker.cmd schema
.\log-checker.cmd query --preset overview --minutes 15
.\log-checker.cmd report --minutes 15
```

`doctor --online` 实际读取字段索引，并测试聚合查询；`schema` 输出字段名、类型和 SQL 索引状态，不输出原始日志。核对 `config.json` 中的 `fields`，尤其是状态码和耗时字段。耗时若为毫秒，将 `latency_unit` 改为 `milliseconds`。索引缺失或 SQL 不兼容时停止并报告，不自动修改云端索引。

确认目标正确、查询完整、字段有效覆盖率合理、耗时单位正确后，才将 `schema_verified` 设置为 `true`。该标志是人工核验记录，程序不会擅自设置。`report` 允许先做诊断，但会提示字段未核实；`check` / `watch` 在核实前拒绝启动。

### 4. 开始检查与监控

```powershell
# 单次检查，写入本地结果和告警状态
.\log-checker.cmd check

# 前台每 5 分钟检查一次，Ctrl+C 停止
.\log-checker.cmd watch

# 只运行一轮，适合接入其他调度器
.\log-checker.cmd watch --cycles 1
```

电脑休眠、关机或关闭前台进程时不会继续检查。当前未安装 Windows 计划任务、Codex 自动化或远端服务，也未接入飞书/邮件。以后要求“定时检查并通知我”时，可让 Codex 创建本任务的定时跟进，调用 `check`，仅在新增异常、恢复、故障或需人工处理时通知；选择一种调度方式即可。

## 可以问 Agent 什么

- “检查 Demo 最近 15 分钟有没有异常。”
- “最近 1 小时哪些页面返回 5xx 最多？”
- “找出最近 1 小时的 404 和慢页面。”
- “最近 30 分钟访问最多的 IP 是哪些？”
- “比较最近 15 分钟和前 15 分钟的流量。”
- “看一下 Googlebot、Bingbot、GPTBot 等声明的爬虫访问量。”

| 命令 | 用途 |
|---|---|
| `doctor` / `doctor --online` | 本地诊断 / 实际连接核验 |
| `schema` | 查看索引字段、类型和 SQL 状态 |
| `query --preset errors` | 5xx 页面排行 |
| `query --preset not-found` | 404 页面排行 |
| `query --preset slow` | 慢页面与 P95 |
| `query --preset top-paths` | 热门路径 |
| `query --preset top-ips` | 高频 IP 排行 |
| `query --preset bots` | 按 User-Agent 声明粗分爬虫 |
| `query --preset overview` | 总量、错误率、字段覆盖率、P95 |
| `query --preset errors --show-sql` | 离线查看实际 SQL |
| `report --minutes 60` | 当前窗口与前一窗口的诊断报告 |
| `check` | 检查对齐窗口、告警去重、恢复记录 |
| `watch` | 前台持续运行 |
| `demo` | 演示报告，不调用阿里云 |

`query` 支持 `--minutes 1..1440`、`--limit 1..200`。高级定制可在 `log_checker/queries.py` 增加有界聚合预设；当前没有任意 SQL 或完整原始日志导出入口。

## 默认监控规则

| 规则 | 默认触发条件 |
|---|---|
| 5xx | 比例 ≥ 1% |
| 404 | 比例 ≥ 10% |
| 429 | 比例 ≥ 1% |
| P95 响应耗时 | > 2 秒 |
| 慢请求统计 | 请求耗时 > 2 秒 |
| 流量下降 | 当前量 < 前一窗口的 50% |
| 流量突增 | 当前量 > 前一窗口的 3 倍 |
| 无日志 | 当前窗口 0 条，提示排查采集/延迟/流量 |
| 数据质量 | 样本不足、字段覆盖率不足时提示无法判断 |
| 查询失败 | 独立故障事件，保留已有网站告警 |

默认观察 15 分钟，每 5 分钟检查，避开最近 120 秒以容纳采集延迟，并向下对齐到 5 分钟边界。相邻检查窗口有重叠；每次比较的当前/前一窗口相邻且不重叠。时间统一显示 UTC。

错误率和延迟判断至少需要 100 条请求、相关字段有效覆盖率至少 99%；覆盖不足或无数据时不解除之前的该类告警。流量比较需要前一窗口至少 100 条。阈值均在 `config.json`，是初始默认值，未按网站历史流量校准；相邻窗口比较不等于季节性异常检测。

同一规则持续触发时只记录首次事件，恢复后记录恢复；同一已完成窗口不会重放。规则严重等级变化会记录变更。查询失败或 SLS `Incomplete` 不会当成正常。修改目标、字段或阈值会生成新的状态 ID，旧状态保留，不跨配置错误解除告警。

## 输出、成本与边界

- `outputs/latest/report.json`、`report.md`：最近一次诊断/检查快照。
- `state/<配置ID>.json`：告警状态与最近成功窗口。
- `state/<配置ID>-events.jsonl`：告警和恢复事件，达到 5 MiB 时轮换并保留上一份。
- `outputs/demo/`：明确标注为演示数据；不会写入正式告警状态。
- 退出码：`0` 成功/未触发/窗口跳过，`1` 异常或诊断提醒，`2` 配置或运行失败，`130` 手动停止。`demo` 成功返回 `0`，即使演示中含告警。

每次 `report/check` 通常执行两次聚合；`query` 一次；`doctor --online` 一次索引读取加一次聚合。SDK 可能内部重试，SLS 查询可能产生阿里云费用，不承诺免费。默认不启用增强 SQL。输出使用聚合数据；路径去掉 `?` 查询参数，不获取 Cookie、请求头、请求体或原始 UA。高频 IP 和爬虫 UA 不能直接作为恶意判断依据，不会自动封禁 IP 或更改网站配置。

## 验证

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
.\log-checker.cmd demo
```

测试覆盖 SDK 请求/响应契约、缺凭据和脱敏、窗口边界、异常→去重→失败→恢复、空结果/低覆盖率保护与持久化。测试使用本地构造的响应，**不能代替真实 SLS SQL、索引和授权验证**。

实现依据为已安装的[阿里云官方 SLS Python SDK](https://github.com/aliyun/aliyun-log-python-sdk) `0.9.50` 源码；依赖版本固定在 `requirements.txt`。SDK 中其他云端写入能力未暴露给本 CLI。
