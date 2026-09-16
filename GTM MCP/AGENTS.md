# GTM MCP 协作说明

本文件夹是 Google Tag Manager 的本地 MCP。供 Cursor、Codex、Claude Code 以及接手的同事复用。目标是用 Tag Manager API v2 读写真实 GTM 配置，而不是猜测容器里有什么。

除非用户指定其它语言，否则用中文回答。

## 1. 这是什么

- 产品名：`gtm-mcp-agent`
- MCP 在客户端中的名字：`gtm`
- 上游 API：Google Cloud **Tag Manager API v2**（`https://tagmanager.googleapis.com/tagmanager/v2`）
- 传输：本地 stdio，由 `scripts/bootstrap-mcp.ps1` 启动
- 鉴权：服务账号 JSON + GTM User Management，不是浏览器 OAuth

它管理的是 GTM 容器配置（标签、触发器、变量、版本、发布）。它不查询 GA4 报表。流量数字走旁边的 `GA MCP`。

## 2. 对人：第一次怎么用

1. 用 Cursor 或 Codex 打开本文件夹根目录。
2. 复制 `.env.example` 为 `.env`。
3. 按 `README.md` 的「配置 Service Account」创建 JSON，启用 Tag Manager API，并把 `client_email` 加入 GTM。
4. 在 `.env` 写入 `GOOGLE_APPLICATION_CREDENTIALS` 的绝对路径，以及默认 `GTM_CONTAINER_ID`（`GTM-XXXX`）。
5. 运行 `.\scripts\setup.ps1`，再运行 `.\.venv\Scripts\gtm-mcp.exe doctor`。
6. 在对话里说「检查 GTM 连接」。

不要把服务账号 JSON、`.env` 或私钥发给任何 AI。`whoami` 和 `doctor` 只会公开 `client_email` 和 `project_id`。

## 3. 对 AI：何时必须调用这个 MCP

用户提到以下内容时，必须使用 `gtm` MCP，不得用训练数据编造账户内容：

- Google Tag Manager / GTM / 代码容器 / 网页容器
- 标签、触发器、变量、内置变量、文件夹
- workspace、容器版本、发布、回滚、安装 snippet
- GTM-XXXX、All Pages、GA4 Configuration、自定义 HTML 标签
- Consent Mode 在 GTM 里怎么配

不要用这个 MCP 去：

- 查 GA4 用户、会话、收入（用 GA MCP）
- 改 Google Ads 广告系列
- 读取或打印 `.env`、服务账号 JSON、token、私钥

凭据未配置或 API 失败时，停止并给出 `README.md` 里的准确下一步。不能用虚构标签清单代替。

## 4. 强制操作规则

1. **先解析目标。** 站点、容器或 workspace 不确定时，先 `list_accounts` / `list_containers` / `resolve_target`。不要默认混用不同容器。
2. **先审计，再开清单。** 优先 `audit_container` 和 `search_workspace`。`list_tags` 默认 `compact=true`。
3. **数字和名称必须来自工具结果。** 不要猜测 tagId、triggerId、Measurement ID 或线上版本号。
4. **写操作两步确认。** `create_*` / `update_*` / `delete_*` / `enable_built_in_variables` / `create_workspace` / `create_version` / `publish_version` 必须先 `confirm=false` 预览，把准确 target 和 payload 给用户看；用户明确确认后，用完全相同参数加 `confirm=true`。
5. **`create_version` 会删掉当前 workspace。** API 会把 workspace 做成版本，删除该 workspace，再创建一个新 workspace。预览时必须说清楚。它**不会**发布到线上。
6. **`publish_version` 改变线上流量。** 只有用户明确说「发布 / 上线 / publish」时才能走发布预览。审计、创建标签、创建版本都不得顺带发布。
7. **只读模式尊重 `GTM_READ_ONLY=true`。** 此时任何写入都应失败；告诉用户改 `.env`，不要找绕过。
8. **危险修改用独立 workspace。** 用户没指定时，先说明将使用 Default Workspace，并建议先 `create_workspace`。
9. **不要输出秘密。** 可以显示 `client_email`。不可以显示 `private_key`、JSON 全文、`.env` 内容。
10. **ID 不要搞混。**
    - `GTM-XXXX` = 容器 publicId
    - `G-XXXX` = GA4 Measurement ID，只属于标签参数
    - 数字 `accountId` / `containerId` / `workspaceId` / `tagId` 是 API 路径用的

## 5. 推荐调用顺序

### 检查连接

1. `whoami`
2. `check_connection`
3. 需要站点时 `list_containers` 或 `resolve_target`

### 看一个容器

1. `resolve_target`
2. `audit_container`
3. 按名称 `search_workspace`
4. 只对命中的 ID 调用 `get_tag` / `get_trigger` / `get_variable`

### 加一个 GA4 标签（示例）

1. `audit_container` 看是否已有 `gaawc` / `googtag`
2. `list_triggers` 找到 All Pages 或等价触发器
3. `create_tag` 且 `confirm=false`，`preset=ga4_config`，带上 `measurement_id` 和 `firing_trigger_ids`
4. 用户确认后同样参数 `confirm=true`
5. 若用户要上线：先 `create_version` 预览，再单独 `publish_version` 预览。两步都要各确认一次

## 6. 目录职责

- `README.md`：给人看的安装、服务账号、Cursor/Codex 用法
- `AGENTS.md`：本文件，给后续 AI 和同事
- `.env.example` / `.env`：配置模板和本地秘密；`.env` 不可提交
- `.cursor/mcp.json`、`.codex/config.toml`：客户端如何启动 MCP
- `.cursor/rules/gtm-operations.mdc`：Cursor 始终应用的操作规则
- `src/gtm_agent/`：配置、API 客户端、preset 构造、MCP 工具、CLI
- `scripts/bootstrap-mcp.ps1`：创建 `.venv` 并以 stdio 启动
- `scripts/setup.ps1`：显式安装
- `scripts/check_mcp.py`：协议级工具清单校验
- `.cursor/skills/verify-gtm-mcp/`：验证 skill 与 control CLI

启动链：

```text
Cursor / Codex
    -> scripts/bootstrap-mcp.ps1
    -> .venv python -m gtm_agent.mcp_server
    -> Tag Manager API v2
```

CLI 链：

```text
gtm-mcp doctor|tools|accounts|audit|call
    -> 同一套 gtm_agent 代码
```

客户端配置只准引用启动脚本，不准写入私钥。

## 7. CLI 约定

默认 JSON。错误必须带 `next_step`。破坏性命令带 `--dry-run`。

```powershell
.\.venv\Scripts\gtm-mcp.exe doctor
.\.venv\Scripts\gtm-mcp.exe tools
.\.venv\Scripts\gtm-mcp.exe call whoami --dry-run
.\.venv\Scripts\gtm-mcp.exe publish 12 --dry-run
```

`publish` 默认 dry-run。真正发布需要 `--no-dry-run --force`。

改了 UI 或工具行为后，按 `.cursor/skills/verify-gtm-mcp/SKILL.md` 跑验证，不要只用口头声明。

## 8. 不要做的事

- 不要在测试或 doctor 里创建真实标签、删除资源或发布线上版本
- 不要把首次验证做成对生产容器的写入
- 不要用浏览器抓 GTM 网页来代替 API
- 不要把 `create_version` 解释成已经上线
- 不要把 GA4 Property ID、Ads Customer ID 和 GTM 容器 ID 互相替代
