# Cloud Development

推荐方式：把源码放到一个私有 GitHub 仓库，然后用 GitHub Codespaces 或 VS Code Dev Containers 在云端继续开发。

## 不能提交的内容

这些文件只保留在本机或云端 Secret，不进 Git：

- `google-ads.yaml`
- `config.yaml`
- `ads-api-*.json`
- `google-ads-service-account.json`
- `reports/*.md`

## GitHub Codespaces Secrets

在 GitHub 仓库里进入:

`Settings -> Secrets and variables -> Codespaces -> New repository secret`

添加这些 Secrets：

```text
GOOGLE_ADS_DEVELOPER_TOKEN
GOOGLE_ADS_SERVICE_ACCOUNT_JSON
GOOGLE_ADS_LOGIN_CUSTOMER_ID
GOOGLE_ADS_DEFAULT_CUSTOMER_ID
GOOGLE_ADS_API_VERSION
FEISHU_CHAT_ID
```

其中：

- `GOOGLE_ADS_LOGIN_CUSTOMER_ID` 是 MCC ID，不带横杠。
- `GOOGLE_ADS_DEFAULT_CUSTOMER_ID` 是实际操作广告账号 ID，不带横杠。
- `GOOGLE_ADS_SERVICE_ACCOUNT_JSON` 是整个 service account JSON 文件内容。

Codespaces 启动后会自动运行：

```bash
bash scripts/init_cloud_config.sh
```

如果你后续新增或修改 Secret，可以手动重新生成：

```bash
bash scripts/init_cloud_config.sh
python -m adwords_agent.cli accounts
```

## 飞书 CLI

为了项目可迁移，飞书 CLI 放在：

```text
tools/feishu-cli
```

云端 Linux 环境通常不能直接运行 Windows `.exe`。如果你使用 Codespaces，建议把飞书发送改成 Linux 可运行的 CLI、Node 脚本或 Python 脚本，然后让 `tools/feishu-cli/send-file.ps1` 或一个同等脚本调用它。

## 发布到云端运行

开发环境和定时运行可以分开：

- 开发：GitHub Codespaces / Cloud Workstations
- 定时任务：GitHub Actions schedule、Google Cloud Run Jobs、Windows Task Scheduler 云主机

如果只需要“在家继续开发”，先用 Codespaces 最简单。
