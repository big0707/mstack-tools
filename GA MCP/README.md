# GA4 报告与 Audience Agent（Cursor + Codex）

把这个文件夹发给同事后，他们用 **Cursor** 或 **Codex** 打开项目，就可以直接在 Agent 对话中提出数据需求，例如：

> 查询最近 30 天各渠道的用户、会话和收入，与之前 30 天比较，输出一份中文报告。

Cursor/Codex 会自动调用本项目的 GA4 MCP、执行真实查询，并在对话中输出 Markdown 报告。不需要另外启动聊天程序，也不需要 `OPENAI_API_KEY`。

## 已包含的能力

- 项目级 Codex MCP 配置：`.codex/config.toml`
- 项目级 Cursor MCP 配置：`.cursor/mcp.json`
- Codex Agent 规则：`AGENTS.md`
- Cursor Agent 规则：`.cursor/rules/ga4-reporting.mdc`
- 自动环境安装和 MCP 启动
- 历史报表、实时数据、字段元数据、过滤、排序和分页
- 默认中文报告、同期比较、口径和数据质量说明
- 受控的 GA4 Audience 创建、改名/改描述和归档工具
- Audience 写入前强制预览和二次确认；报告及其他配置保持只读

## 使用者只需完成一次配置

GA4 是私有数据，因此每位使用者仍需要合法凭据。不要把服务账号私钥提交到这个文件夹或 Git。

## 生成可分享的干净 ZIP

项目维护者可以运行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\package.ps1
```

生成的 `dist/ga4-report-agent.zip` 可以直接发给使用者。打包脚本会排除 `.env`、服务账号 JSON、`.venv`、缓存和本地数据。不要直接把现有 `.venv` 一起复制给别人。

### 1. 系统要求

- Windows 10/11
- Python 3.10 或更新版本（安装时启用 `py` launcher 或加入 PATH）
- Cursor 或 Codex

首次打开时，MCP 启动器会自动创建 `.venv` 并安装依赖。首次运行可能需要一两分钟和网络访问，后续启动不会重复安装。

### 2. 准备 Google 权限

1. 在 Google Cloud 项目中启用 **Google Analytics Data API**。如需管理 Audience，同时启用 **Google Analytics Admin API**。
2. 创建服务账号并下载 JSON key。
3. 在 GA4 打开 **管理 → Property access management**。
4. 把 JSON 中的 `client_email` 加入 GA4。只查询报告授予 **Viewer** 即可；需要创建、修改或归档 Audience 时授予 **Editor**。
5. 找到 GA4 的数字 **Property ID**；不要使用 `G-XXXX` Measurement ID。

参考：[Google Analytics Data API quickstart](https://developers.google.com/analytics/devguides/reporting/data/v1/quickstart)

### 3. 创建本地 `.env`

在项目根目录复制配置模板：

```powershell
Copy-Item .env.example .env
```

编辑 `.env`：

```dotenv
GA4_PROPERTY_ID=123456789
GA4_PROPERTY_DEMO=123456789
GA4_PROPERTY_DEMOTHREE=123456782
GA4_PROPERTY_DEMOFOUR=123456781
GA4_PROPERTY_DEMOTWO=123456780
GA4_PROPERTY_DEMOFIVE=123456783
GA4_PROPERTY_DEMOSIX=123456784
GA4_PROPERTY_DEMOSEVEN=123456785
GOOGLE_APPLICATION_CREDENTIALS=C:\Users\you\secrets\ga4-service-account.json
```

服务账号 JSON 建议放在项目文件夹之外。`.env`、常见凭据文件名和本地环境已经加入 `.gitignore` 与 `.cursorignore`。

## 在 Codex 中使用

1. 用 Codex 打开本文件夹并信任项目。
2. 重启 Codex 或新开一个任务，让项目级 MCP 配置生效。
3. 先输入：

   > 检查 GA4 连接。

4. 连接成功后直接提出报告需求。

Codex 从 `.codex/config.toml` 发现 `ga4` MCP，从 `AGENTS.md` 获取报告规则。

## 在 Cursor 中使用

1. 用 Cursor 打开本文件夹。
2. 在 **Settings → Tools & MCP** 中确认 `ga4` 已启用；第一次出现执行/工具确认时允许只读查询。
3. 打开 Agent 对话，先输入：

   > 检查 GA4 连接。

4. 连接成功后直接提出报告需求。

Cursor 从 `.cursor/mcp.json` 发现 `ga4` MCP，从 `.cursor/rules/ga4-reporting.mdc` 获取报告规则。

## 可以直接复制的需求

- “查询最近 30 个完整日的用户、会话、参与率和收入，与之前 30 天比较，输出管理层摘要。”
- “分析上个月各默认渠道组的获客表现，按会话排序，指出增长和下滑最大的渠道。”
- “最近 14 天每天的购买收入、购买次数和购买用户趋势如何？”
- “列出自然搜索访问量最高的 20 个落地页，并给出参与率和转化表现。”
- “现在最近 30 分钟有哪些国家和页面最活跃？”
- “搜索这个 Property 中所有与 checkout 有关的自定义 dimensions 和 metrics。”
- “先预览一个过去 30 天访问过定价页、但没有注册的 Audience；不要创建，等我确认。”

## 报告输出约定

除非需求另有说明，Agent 会：

- 使用截至昨天的最近 30 个完整自然日；
- 需要判断变化时查询紧邻的等长上一周期；
- 在对话中输出标题、摘要、KPI、趋势/排名、洞察和口径说明；
- 标明实际日期、dimensions、metrics、filters、时区和货币；
- 将事实和解释分开，不把相关性表述为因果关系；
- 对阈值、归因、`(not set)`、截断和当天不完整数据进行提示。

## MCP 工具

- `list_properties`：列出可按站点名选择的 Property。
- `check_connection`：验证凭据和 Property 权限。
- `run_report`：查询历史 GA4 报表。
- `run_realtime_report`：查询最近 1–30 分钟实时数据。
- `get_metadata`：搜索当前 Property 可用的标准或自定义字段。
- `list_audiences`：分页列出 Property 中的 Audience。
- `get_audience`：读取一个 Audience 的完整定义。
- `list_google_ads_links`：检查 Property 已连接的 Google Ads 账号及个性化广告设置。
- `create_audience`：预览或创建 Audience；只有 `confirm=true` 才会写入。
- `update_audience`：预览或修改 Audience 名称/描述；条件和成员期限不可修改。
- `archive_audience`：预览或归档 Audience；归档属于破坏性操作。

## Audience 安全流程与广告同步

Audience 写入使用 Google Analytics Admin API 和 `analytics.edit` OAuth scope。工具采用两步流程：

1. Agent 先以 `confirm=false` 返回完整预览，不修改 GA4。
2. 用户确认准确的 Property、名称、条件、成员期限和排除方式。
3. Agent 使用完全相同的参数并设置 `confirm=true`，才会实际写入。

Audience 条件和成员资格期限创建后不可修改；不再需要的 Audience 只能归档。当前工具支持常用的简单事件、字符串、列表、数字和区间条件，不支持顺序型 Audience。

要将 Audience 用于广告，GA4 Property 还必须已经链接 Google Ads，并开启个性化广告；再营销还需要 Google Signals 或 User-provided data collection。满足条件时，GA4 会把 Audience 自动同步到已链接的 Google Ads，通常需要最多约两天。这个 MCP 不建立或修改 Google Ads 链接，也不把 Audience 添加到广告系列。

## 常见问题

### 看不到 `ga4` MCP

- 确认已经打开的是项目根目录，而不是其中的子目录。
- 确认安装了 Python 3.10+。
- 重启 Cursor/Codex 或新开任务。
- 手动运行 `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1` 检查安装错误。

### `Permission denied` 或 `property not found`

- 检查 `.env` 中是否为数字 Property ID。
- 检查服务账号 `client_email` 是否已加入这个 Property：报告查询至少 Viewer，Audience 写入需要 Editor。
- 检查 Google Analytics Data API 是否已启用；Audience 工具还需要 Google Analytics Admin API。

### 是否可以真正做到“拿到文件夹就零配置”

只有把 MCP 部署成一个带身份验证的远程服务才可以做到。对于当前本地方案，GA4 私有凭据不能安全地打包进文件夹，所以每位使用者至少要完成一次 `.env` 配置。如果需要给很多人使用，下一阶段应把这个 MCP 部署为 Streamable HTTP 服务并接入公司登录。

实现参考：[Cursor MCP](https://docs.cursor.com/context/model-context-protocol)、[Cursor Project Rules](https://docs.cursor.com/context/rules)、[Codex MCP](https://developers.openai.com/codex/mcp/)、[GA4 dimensions & metrics](https://developers.google.com/analytics/devguides/reporting/data/v1/api-schema)。
