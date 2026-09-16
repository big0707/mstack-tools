# GTM MCP（Google Tag Manager）

把这个文件夹发给同事后，他们用 **Cursor** 或 **Codex** 打开项目，就可以在 Agent 对话里直接查看和（经确认后）修改 Google Tag Manager。

> 检查 GTM 连接，然后审计默认容器里有哪些 GA4 标签和未发布改动。

Cursor/Codex 会调用本项目的 `gtm` MCP。数字、标签、版本都必须来自 Tag Manager API v2，不能编造。

## 已包含的能力

- 项目级 Cursor MCP：`.cursor/mcp.json`
- 项目级 Codex MCP：`.codex/config.toml`
- 给人和其它 AI 的复用说明：`AGENTS.md`
- Cursor 规则：`.cursor/rules/gtm-operations.mdc`
- 自动创建 `.venv` 并启动 stdio MCP
- 账户 / 容器 / workspace 发现与路径解析
- 标签、触发器、变量、内置变量、文件夹的只读清单
- 容器审计、名称搜索、安装 snippet、版本与线上版本
- 写操作强制 `confirm=false` 预览，再 `confirm=true` 执行
- Agent 友好 CLI：`gtm-mcp doctor|tools|accounts|containers|audit|call|snapshot|publish`

本 MCP 使用 Google Cloud 的 **Tag Manager API v2**（`tagmanager.googleapis.com`），不是 GA4 Data API，也不是 Google Ads API。

## 使用者只需完成一次配置

GTM 是私有配置。不要把服务账号私钥提交到这个文件夹或 Git。

### 1. 系统要求

- Windows 10/11
- Python 3.10 或更新版本
- Cursor 或 Codex
- 一个 Google Cloud 项目，已启用 **Tag Manager API**
- 一个服务账号 JSON，并且该账号的 `client_email` 已被加入 GTM

首次打开时，MCP 启动器会自动创建 `.venv` 并安装依赖。

### 2. 配置服务账号

完整步骤见下方「配置 Service Account」。摘要：

1. 在 Google Cloud 启用 **Tag Manager API**。
2. 创建服务账号并下载 JSON key。
3. 把 JSON 里的 `client_email` 加到 GTM **Admin → User Management**。
4. 把 JSON 放到仓库外，在 `.env` 里只写绝对路径。

### 3. 创建本地 `.env`

```powershell
Copy-Item .env.example .env
```

编辑 `.env`：

```dotenv
GTM_ACCOUNT_ID=123456789
GTM_CONTAINER_ID=GTM-XXXXXXX
GTM_CONTAINER_DEMO=GTM-XXXXXXX
GOOGLE_APPLICATION_CREDENTIALS=C:\Users\you\secrets\gtm-service-account.json
GTM_READ_ONLY=false
```

`GTM_CONTAINER_ID` 优先用网页容器的 **GTM-XXXX**。数字 containerId 也可以。`GTM-` 不是 GA4 的 `G-` Measurement ID。

建议先设 `GTM_READ_ONLY=true` 做只读检查，确认连接后再改为 `false`。

### 4. 安装并自检

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
.\.venv\Scripts\gtm-mcp.exe doctor
```

`doctor` 只输出 JSON。成功时应看到 `ok: true` 和 `client_email`。失败时看 `next_step`，不要猜测。

## 配置 Service Account

服务账号要同时满足两件事：**Google Cloud 能调用 Tag Manager API**，以及 **GTM 界面承认这个邮箱**。只完成其中一步会得到 403。

### A. Google Cloud：启用 API 并创建密钥

1. 打开 [Google Cloud Console](https://console.cloud.google.com/)。
2. 选择或创建一个项目。可以和使用 GA4 MCP 的项目相同，但必须单独启用 Tag Manager API。
3. 打开 [Enable Tag Manager API](https://console.cloud.google.com/apis/library/tagmanager.googleapis.com)，点击 **Enable**。
4. 打开 **IAM & Admin → Service Accounts → Create service account**。
   - 名称建议：`gtm-mcp`
   - 不必授予 Editor 之类的 GCP 项目角色。GTM 权限不在这里配。
5. 打开该服务账号 → **Keys → Add key → Create new key → JSON**。
6. 把下载的 JSON 放到仓库外，例如 `C:\Users\you\secrets\gtm-service-account.json`。
7. 记下 JSON 中的 `client_email`，形如：
   `gtm-mcp@your-project.iam.gserviceaccount.com`
8. 不要把 JSON 内容发给 Agent，也不要贴进聊天。

用 `gcloud` 也可以：

```powershell
gcloud services enable tagmanager.googleapis.com --project YOUR_PROJECT_ID
gcloud iam service-accounts create gtm-mcp --project YOUR_PROJECT_ID --display-name "GTM MCP"
gcloud iam service-accounts keys create C:\Users\you\secrets\gtm-service-account.json --iam-account gtm-mcp@YOUR_PROJECT_ID.iam.gserviceaccount.com
```

### B. GTM：把服务账号加成用户

1. 打开 [Google Tag Manager](https://tagmanager.google.com/)。
2. 进入目标账户 → **Admin**。
3. 在 **Account** 栏打开 **User Management**（账户级可覆盖其下所有容器）。
   如果只想开一个容器，改用 **Container** 栏的 User Management。
4. 点击 **+**，输入服务账号的 `client_email`。
5. 权限建议：
   - 只读审计：**Read**
   - 改标签 / 触发器 / 变量：**Edit**
   - 创建版本：**Approve**（对应 API 的 `tagmanager.edit.containerversions`）
   - 发布线上：**Publish**
6. 保存后等一两分钟再跑 `gtm-mcp doctor`。

本 MCP 申请的 OAuth scope：

- `tagmanager.readonly`
- `tagmanager.edit.containers`
- `tagmanager.edit.containerversions`
- `tagmanager.publish`

`GTM_READ_ONLY=true` 时只申请 readonly。GTM 界面权限仍然必须单独授予。

### C. 常见失败

| 现象 | 原因 | 下一步 |
| --- | --- | --- |
| `Tag Manager API has not been used` | Cloud 项目未启用 API | 启用 `tagmanager.googleapis.com` |
| 403 / Permission denied | 服务账号未加入 GTM，或权限不够 | Admin → User Management 加入 `client_email` |
| 找不到容器 | 加错了账户，或用了 `G-` 而不是 `GTM-` | `list_accounts` 后再 `list_containers` |
| 文件不存在 | `.env` 路径写错 | 使用 JSON 的绝对路径 |
| 发布 403 | 只有 Edit，没有 Publish | 在 GTM 给 Publish |

## 在 Cursor 中使用

1. 用 Cursor 打开本文件夹（项目根目录，不要只打开 `src`）。
2. 在 **Settings → Tools & MCP** 确认 `gtm` 已启用。
3. 先说：`检查 GTM 连接。`
4. 再提出具体容器、标签或发布需求。

Cursor 从 `.cursor/mcp.json` 发现 `gtm` MCP，从 `AGENTS.md` 和 `.cursor/rules/gtm-operations.mdc` 读取操作规则。

## 在 Codex 中使用

1. 用 Codex 打开本文件夹。
2. 重启或新开任务，让 `.codex/config.toml` 生效。
3. 先说：`检查 GTM 连接。`

## 可以直接复制的需求

- “检查 GTM 连接，告诉我服务账号邮箱和能看到哪些账户。”
- “列出所有容器，并解析 Demo 对应的 workspace 路径。”
- “审计 GTM-XXXX 的标签类型、暂停标签和未发布改动。”
- “搜索这个容器里所有和 purchase 或 GA4 有关的标签和触发器。”
- “先预览一个 GA4 Configuration 标签，Measurement ID 是 G-XXXX，触发 All Pages；不要创建，等我确认。”
- “先预览从当前 workspace 创建版本 `fix-consent-2026-09-02`，不要发布。”

## MCP 工具

只读：`whoami`、`check_connection`、`list_accounts`、`list_containers`、`get_container`、`get_container_snippet`、`resolve_target`、`list_workspaces`、`get_workspace_status`、`list_tags`、`get_tag`、`list_triggers`、`get_trigger`、`list_variables`、`get_variable`、`list_built_in_variables`、`list_folders`、`search_workspace`、`audit_container`、`list_versions`、`get_version`、`get_live_version`。

写入（必须先 `confirm=false`）：`create_tag`、`update_tag`、`delete_tag`、`create_trigger`、`update_trigger`、`delete_trigger`、`create_variable`、`update_variable`、`delete_variable`、`enable_built_in_variables`、`create_workspace`、`create_version`、`publish_version`。

`create_version` 会删除当前 workspace 并生成新的 workspace，但不会上线。`publish_version` 才会改变线上流量。

## CLI

```powershell
.\.venv\Scripts\gtm-mcp.exe --help
.\.venv\Scripts\gtm-mcp.exe doctor
.\.venv\Scripts\gtm-mcp.exe tools
.\.venv\Scripts\gtm-mcp.exe accounts
.\.venv\Scripts\gtm-mcp.exe containers --account 123456789
.\.venv\Scripts\gtm-mcp.exe audit --container GTM-XXXXXXX
.\.venv\Scripts\gtm-mcp.exe call whoami
.\.venv\Scripts\gtm-mcp.exe publish 12 --dry-run
```

破坏性子命令默认 `--dry-run`。`publish` 必须同时 `--no-dry-run --force` 才会真正发布。

## 生成可分享的干净 ZIP

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\package.ps1
```

生成的 `dist/gtm-mcp-agent.zip` 不含 `.env`、服务账号 JSON 和 `.venv`。

## 常见问题

### 看不到 `gtm` MCP

- 确认打开的是本项目根目录。
- 安装 Python 3.10+。
- 重启 Cursor/Codex。
- 手动运行 `.\scripts\setup.ps1` 查看安装错误。

### 是否可以和 GA MCP 共用同一个服务账号

可以共用同一个 Google Cloud 项目和同一个 JSON，但必须：

1. 额外启用 **Tag Manager API**；
2. 把同一个 `client_email` 加进 GTM User Management。

GA4 Viewer 权限不会自动变成 GTM 权限。

实现参考：[Tag Manager API v2](https://developers.google.com/tag-platform/tag-manager/api/v2)、[Cursor MCP](https://docs.cursor.com/context/model-context-protocol)。
