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

## 身份隔离（自行填写）

把下面的占位符换成你们自己的账号，并写进各项目 `.env` / `catalog.yaml`，不要写回本仓库。

| 身份 | 用途 |
|---|---|
| `YOUR_GMP_SA@YOUR_GCP_PROJECT.iam.gserviceaccount.com` | GMP 人员管理（GA / GTM / Ads 加人减人） |
| `YOUR_ADS_SA@YOUR_GCP_PROJECT.iam.gserviceaccount.com` | Google Ads 投放，不用于管人 |
| `YOUR_GSC_SA@YOUR_GCP_PROJECT.iam.gserviceaccount.com` | Search Console 查询 |
| `YOUR_PRODUCT_ADMIN@example.com` | 产品管理员 Chrome，仅在公开 API 做不到时处理授权 |
| `YOUR_GCP_ADMIN@example.com` | GCP Service Account 生命周期，与产品权限分开 |

人员管理身份和广告投放身份必须隔离。缺少密钥、读不到文件或邮箱不匹配时停止，禁止回退到另一个身份。

## 首次配置

1. 复制各项目的 `.env.example` 为 `.env`，填入自己的路径和 token。
2. 把 Google 服务账号 JSON 放到已被 gitignore 的 `credentials/` 目录，不要提交。
3. 编辑 `Google Marketing Platform/catalog.yaml`，改成你们自己的 GA / GSC / GTM / Ads 资源。
4. Ads 使用 `Adwords API/google-ads.example.yaml` 复制为 `google-ads.yaml`。
5. Log Checker 使用 `config.example.json` 复制为 `config.json`。
6. 在对应项目目录创建 `.venv` 或 `npm install`，再跑该项目的 `doctor` / 鉴权脚本。

## 权限变更与审计

- GMP 写入必须先生成不可变计划，用户确认后再 `gmp apply PLAN_ID --confirm PLAN_ID`。
- 已执行的加人、减人、改权先保存本地结果，再按你们自己的飞书表格追加审计。仓库不包含真实 spreadsheet token。
- 员工离职不等于删除共享 GCP Service Account。
