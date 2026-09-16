# Mstack Tools

**English** | [中文](README.zh-CN.md)

A self-serve marketing toolkit for Google access management, GA4, Tag Manager, Google Ads, Search Console, Feishu, and website log checks. Clone the repo, add your own accounts, and talk to the tools from Cursor or the command line.

This repository ships **code and examples only**. It does not include service-account keys, `.env` files, live account IDs, or reports. Every teammate must create their own Google Cloud project and credentials.

## What's inside

- **Google Marketing Platform**: CLI for GA / GTM / GSC / Ads people access
- **GA MCP / GTM MCP**: Analytics and Tag Manager MCP / CLI
- **Adwords API**: Google Ads delivery and GAQL reports
- **SEO-Agent**: Search Console queries and SEO scripts
- **feishu-cli**: Feishu messages, docs, and sheets
- **Log Checker**: Read-only Alibaba Cloud SLS checks
- **auto bloging**: WordPress setup notes

Each folder has its own README or `AGENTS.md`. Agent routing and a beginner Service Account walkthrough are in [AGENTS.md](AGENTS.md).

## Before you start

1. Prepare your own Google Cloud project, service accounts, Ads developer token, and Feishu app. New to service accounts? Read the beginner section in [AGENTS.md](AGENTS.md).
2. Do not reuse someone else's keys, and do not commit secrets to Git.
3. Copy the example files listed in [AGENTS.md](AGENTS.md) and fill in your own values.

```powershell
# Example: GMP
cd "Google Marketing Platform"
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
copy .env.example .env
# Edit .env and catalog.yaml, then:
.\.venv\Scripts\gmp.exe doctor
```

## Not in this repo

- Service-account private keys such as `*ads-api-*.json` or `gsc-key.json`
- `.env`, `google-ads.yaml`, `config.yaml`, WordPress application passwords
- Account reports and runtime output such as `.query-cache/`, `outputs/`, `reports/`, `ops/`, `.data/`
- Real admin emails, MCC IDs, or Feishu spreadsheet tokens

## License

MIT License. See [LICENSE](LICENSE).
