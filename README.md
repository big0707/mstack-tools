# Mstack Tools

A self-serve marketing toolkit for Google access management, GA4, Tag Manager, Google Ads, Search Console, Feishu, and website log checks. Clone the repo, add your own accounts, and talk to the tools from Cursor or the command line.

This repository ships **code and examples only**. It does not include service-account keys, `.env` files, live account IDs, or reports. Every teammate must create their own Google Cloud project and credentials.

营销工具合集：Google 权限管理、GA4 / GTM / Ads / GSC、飞书、日志检查和站点内容发布。

这是一份**可自行配置的代码副本**。仓库里没有 Service Account 密钥、没有 `.env`，也没有账号报告或查询缓存。

## What's inside / 里面有什么

- **Google Marketing Platform**：GA / GTM / GSC / Ads 人员权限 CLI
- **GA MCP / GTM MCP**：Analytics 与 Tag Manager 的 MCP / CLI
- **Adwords API**：Google Ads 投放与 GAQL 报告
- **SEO-Agent**：Search Console 查询和 SEO 脚本
- **feishu-cli**：飞书消息、文档和表格
- **Log Checker**：阿里云 SLS 只读巡检
- **auto bloging**：WordPress 配置安全说明

每个子目录有自己的 README 或 `AGENTS.md`。Agent 路由和 Service Account 小白说明见根目录 [AGENTS.md](AGENTS.md)。

## Before you start / 开始之前

1. 准备你们自己的 Google Cloud 项目、Service Account、Ads developer token、飞书应用等。不会用服务账号？先看 [AGENTS.md](AGENTS.md) 里的「Service Account 小白配置」。
2. 不要复用别人机器上的密钥，也不要把密钥提交到 Git。
3. 按 [AGENTS.md](AGENTS.md) 的「首次配置」复制示例文件并填写。

```powershell
# 示例：GMP
cd "Google Marketing Platform"
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
copy .env.example .env
# 编辑 .env 与 catalog.yaml 后再：
.\.venv\Scripts\gmp.exe doctor
```

## Not in this repo / 明确不会出现在本仓库的内容

- `*ads-api-*.json`、`gsc-key.json` 等服务账号私钥
- `.env`、`google-ads.yaml`、`config.yaml`、WordPress Application Password
- `.query-cache/`、`outputs/`、`reports/`、`ops/`、`.data/` 等账号报告和运行产物
- 本机管理员邮箱、MCC 真值、飞书表格 token

## License

MIT License. See [LICENSE](LICENSE).
