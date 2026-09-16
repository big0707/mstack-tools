# Mstack Tools：Agent 导航

本目录是营销工具工作区，不是单个应用。先按任务进入对应项目，再读该项目的 `AGENTS.md`、README 和适用 skill；命令必须在对应项目目录运行。

**每位使用者必须用自己的账号、Service Account、`.env` 和 `catalog.yaml`。** 仓库里只有示例和占位符，没有可用的生产密钥。

## 各项目负责什么

| 目录 | 职责与适用场景 | 入口 / 重要边界 |
|---|---|---|
| `Google Marketing Platform` | 统一管理 GA、GTM、GSC、Google Ads 的人员权限：入职、离职、晋升、项目授权、加人/减人/改权 | [项目规则](Google%20Marketing%20Platform/AGENTS.md)；`.\.venv\Scripts\gmp.exe --help`，先 `doctor` / `catalog`，API 写入须确认不可变计划。GSC CLI 返回 `manual_required`。 |
| `GA MCP` | GA4 历史/实时报告、元数据、Audience 查询与受控修改 | [项目规则](GA%20MCP/AGENTS.md)、[README](GA%20MCP/README.md)；`ga4-mcp.exe` 是 stdio MCP 服务。人员授权走 GMP。 |
| `GTM MCP` | GTM 容器、标签、触发器、变量、工作区、版本与发布 | [项目规则](GTM%20MCP/AGENTS.md)；`.\.venv\Scripts\gtm-mcp.exe --help`。写入先预览再确认；创建版本不等于发布。 |
| `Adwords API` | Google Ads 广告投放操作、GAQL 查询和报告 | [README](Adwords%20API/README.md)；`.\.venv\Scripts\adwords-agent.exe --help`。投放身份与 GMP 管人身份必须分开。 |
| `SEO-Agent` | GSC 搜索表现查询、关键词/页面/国家/设备分析及 SEO 脚本 | [README](SEO-Agent/README.md)；先配置自己的 GSC Service Account，再运行 `scripts\check_gsc_auth.py`、`scripts\gsc_query.py --site <实际资源ID>`。 |
| `feishu-cli` | 飞书消息、文档、Wiki、电子表格读写 | [README](feishu-cli/README.md)；`.\feishu-cli.cmd --help`。用自己的飞书应用凭证。 |
| `Log Checker` | 阿里云 SLS 网站日志查询、错误/慢请求/流量异常检查 | [项目规则](Log%20Checker/AGENTS.md)；复制 `config.example.json` 为 `config.json`，填写自己的 Project / Logstore。仅 SDK 只读访问。 |
| `auto bloging` | WordPress 配置安全说明 | 每位使用者在自己的 WordPress 后台创建 Application Password，不要提交密码文件。 |
| `go-to-market` | 待建设的占位目录 | 当前只有空的 `Agent.md`。 |

## 默认工具路由

- 内容读取和业务操作默认使用本地 CLI，或从命令行调用这些项目已有的公开 API 封装。
- 飞书始终使用根目录 `feishu-cli`。不要误用 `Adwords API/tools/feishu-cli` 的旧副本。
- 不读取、打印或复制整份 `.env`、服务账号 JSON、developer token、OAuth secret、refresh token、私钥或浏览器凭据库。
- 不要把一个站或一个广告账户的凭据套到其它资源。
- 生成 API Key、token、Service Account 之后，把文件放在本机被 gitignore 的目录，让 Agent 本地读取。不要把密钥粘到对话里发给 AI。

## Service Account 小白配置

Service Account 可以理解成「给程序用的 Google 机器人账号」。人用 `xxx@gmail.com` 登录网页；程序用一份 JSON 密钥文件调用 API。仓库里没有现成密钥，你必须自己做一份。

### 1. 准备一个 Google Cloud 项目

公司统一管理时，用公司的 Google Cloud，并请管理员帮你开项目或授权。也可以用自己的 Google 账号。

1. 打开 [选择项目 / 服务账号](https://console.cloud.google.com/projectselector2/iam-admin/serviceaccounts?supportedpurview=project)。
2. 右上角选一个已有项目；没有项目就点 **新建项目**，名称随便，例如 `my-mstack-tools`。
3. 创建后确认顶栏已经切到这个项目。

### 2. 创建一个服务账号

1. 打开 [IAM → 服务账号](https://console.cloud.google.com/iam-admin/serviceaccounts)。
2. 点 **创建服务账号**。
3. 填一个好记的名字，例如 `ga-reader`、`gtm-ops`、`ads-delivery`。
4. 这一步可以先不勾任何 Google Cloud 项目权限。真正要用的权限，是后面加到 GA / GTM / Ads / Search Console 里，不是先在 Cloud 里乱开 Owner。
5. 创建完成后，记下完整邮箱，长这样：`名字@你的项目名.iam.gserviceaccount.com`。

建议按用途分开建，不要一个账号既管人又投放广告：

| 你想做什么 | 建议单独建一个服务账号 | 之后要把它加到哪里 |
|---|---|---|
| 给同事加 / 减 GA、GTM、Ads 权限 | GMP 管人专用 | GA 账号、GTM 账号、Ads MCC |
| 查 GA4 报告、改 Audience | GA 查询/写入 | 对应 GA4 媒体资源，至少 Viewer |
| 看或改 GTM 标签 | GTM 操作 | 对应 GTM 账号/容器 |
| 投放、拉广告报告 | Ads 投放专用 | Ads MCC / 子账号，并单独配 developer token |
| 查 Search Console | GSC 查询 | 每个要查的网站/网域资源 |

管人账号和投放账号必须分开。缺密钥、读不到文件、或邮箱对不上时停下，不要拿另一个账号凑合。

### 3. 下载 JSON 密钥（最容易出事的一步）

1. 在服务账号列表里，点这一行右边的 **三个点** → **管理密钥**。
2. **添加密钥** → **创建新密钥** → 选 **JSON** → 创建。
3. 浏览器会自动下载一个 `.json` 文件。这就是私钥，等同于这个机器人的密码。

保管规则：

- 只放在自己电脑上，建议放到各项目的 `credentials/` 目录。这些目录已被 `.gitignore` 忽略。
- 不要提交到 Git，不要发到聊天、邮件或飞书群。
- 不要把 JSON 全文贴给 Cursor / ChatGPT。需要 AI 帮忙配置时，只告诉它「密钥在哪个本地路径」。
- 只读、多人共用的账号也要限制知情范围；能写数据的密钥更不能外传。
- 密钥泄露了，立刻在同一页删掉这把 key，再新建一把。

### 4. 把服务账号加到真正要用的产品里

下载 JSON 只完成了一半。还要在对应产品里，用这个服务账号的**邮箱**把它加成成员：

1. **GA4**：管理 → 账号/媒体资源权限 → 加上述邮箱。
2. **GTM**：管理 → 用户权限 → 加上述邮箱。
3. **Search Console**：设置 → 用户和权限 → 加上述邮箱。
4. **Google Ads**：工具与设置 → 访问权限和管理 → 用这个邮箱邀请；Ads 投放另外还要 developer token。

加完再跑各项目的 `doctor` / `check_gsc_auth.py`。报「没有权限」时，先核对邮箱有没有加到**那个**资源，不要换另一把密钥碰运气。

### 5. 让本仓库的工具找到这份 JSON

复制各项目的 `.env.example` 为 `.env`，填**本机绝对路径**，不要把 JSON 内容粘进 `.env`。

```powershell
# GA MCP 示例
GOOGLE_APPLICATION_CREDENTIALS=C:\Users\你的用户名\secrets\ga4-service-account.json

# GTM MCP 示例
GOOGLE_APPLICATION_CREDENTIALS=C:\Users\你的用户名\secrets\gtm-service-account.json
```

SEO-Agent 把 JSON 放到 `SEO-Agent/credentials/gsc-key.json`。  
GMP 在 `Google Marketing Platform/.env` 里分别填写 GA / GSC / GTM / Ads 管人密钥路径。  
Ads 投放复制 `Adwords API/google-ads.example.yaml` 为 `google-ads.yaml`，填你们自己的 developer token 和客户 ID。

## 身份占位符（自行替换，不要写回仓库）

| 身份 | 用途 |
|---|---|
| `YOUR_GMP_SA@YOUR_GCP_PROJECT.iam.gserviceaccount.com` | GMP 人员管理（GA / GTM / Ads 加人减人） |
| `YOUR_ADS_SA@YOUR_GCP_PROJECT.iam.gserviceaccount.com` | Google Ads 投放，不用于管人 |
| `YOUR_GSC_SA@YOUR_GCP_PROJECT.iam.gserviceaccount.com` | Search Console 查询 |
| `YOUR_PRODUCT_ADMIN@example.com` | 产品管理员 Chrome，仅在公开 API 做不到时处理授权 |
| `YOUR_GCP_ADMIN@example.com` | GCP Service Account 生命周期，与产品权限分开 |

## 首次配置

1. 按上面的步骤建好 Service Account，下载 JSON，并加到对应产品。
2. 复制各项目的 `.env.example` 为 `.env`，填入自己的路径和 token。
3. 编辑 `Google Marketing Platform/catalog.yaml`，改成你们自己的 GA / GSC / GTM / Ads 资源。
4. Ads 使用 `Adwords API/google-ads.example.yaml` 复制为 `google-ads.yaml`。
5. Log Checker 使用 `config.example.json` 复制为 `config.json`。
6. 在对应项目目录创建 `.venv` 或 `npm install`，再跑该项目的 `doctor` / 鉴权脚本。

## 权限变更与审计

- GMP 写入必须先生成不可变计划，用户确认后再 `gmp apply PLAN_ID --confirm PLAN_ID`。
- 已执行的加人、减人、改权先保存本地结果，再按你们自己的飞书表格追加审计。仓库不包含真实 spreadsheet token。
- 员工离职不等于删除共享 GCP Service Account。
