# Adwords API Agent

这是一个面向 Codex 使用的 Google Ads API 自动化项目。它把三类事情拆开：

- 广告操作：创建 Responsive Search Ad、更新 RSA 文案、暂停广告。
- 报告任务：用 GAQL 查询每日数据并输出 Markdown。
- 飞书投递：通过项目内的飞书 CLI 包装脚本把报告发到指定群。

Google 已经把旧 AdWords API 替换为 Google Ads API。本项目保留 `adwords-agent` 这个命令名，但底层使用官方 `google-ads` Python client。

## 当前配置

- MCC / `login_customer_id`：已配置在 `google-ads.yaml`
- 默认操作广告账号 / `default_customer_id`：已配置在 `config.yaml`
- Service Account JSON：放在项目根目录，`google-ads.yaml` 使用相对路径引用
- 飞书 CLI：统一放到 `tools/feishu-cli`

`config.yaml`、`google-ads.yaml`、Service Account JSON 和报告文件都已加入 `.gitignore`，不要提交到代码仓库。

## 安装

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e .[dev]
```

检查 Google Ads 鉴权：

```powershell
.\.venv\Scripts\python -m adwords_agent.cli accounts
```

## 云端开发

项目已经支持 Dev Container / GitHub Codespaces。源码可以放到私有 GitHub 仓库；密钥不要提交，用 Codespaces Secrets 或云端环境变量生成本地配置。

云端需要设置这些环境变量：

```text
GOOGLE_ADS_DEVELOPER_TOKEN
GOOGLE_ADS_SERVICE_ACCOUNT_JSON
GOOGLE_ADS_LOGIN_CUSTOMER_ID
GOOGLE_ADS_DEFAULT_CUSTOMER_ID
GOOGLE_ADS_API_VERSION
FEISHU_CHAT_ID
```

生成云端本地配置：

```bash
bash scripts/init_cloud_config.sh
python -m adwords_agent.cli accounts
```

详细说明见 [docs/cloud-dev.md](docs/cloud-dev.md)。

## 长期协作规则

- 所有项目内文本、Markdown、JSON、CSV、YAML、脚本和报告文件统一使用 UTF-8 编码；Windows 环境读写文件时必须显式指定 UTF-8，避免中文变成 `????`。
- 给飞书创建文档时，必须先确认本地源文件不是乱码；发现源文件已损坏时，先重建源文件，再重新生成飞书文档。
- 飞书 CLI 已内置乱码防线（2026-07-09 起）：读文件自动识别 UTF-8/UTF-16/GBK 编码；写文档、表格、发消息前自动检测 `??`、U+FFFD 等乱码特征，命中直接报错拒发（退出码 1）。看到"疑似乱码，已拒绝写入飞书"的报错时，不要加 `--force` 硬发，先重建 UTF-8 源文件。
- Excel / xlsx 结果如果要发到飞书，应优先创建飞书电子表格，也就是 `/sheets/` 类型；不要把 xlsx 误复刻成 docx 文档内表格，除非用户明确要求文档表格。
- 遇到新的踩坑、权限问题、编码问题、API 参数差异或可复用经验时，必须同步更新主目录 `README.md`，让后续 AI 和同事先读主 README 就能继承规则。
- 飞书文档默认使用企业内部链接权限：组织内拿到链接的人可访问，不使用外部公开链接。
- 只有用户明确说明“机密”“仅授权人可见”等场景，才使用 private 模式：仅应用创建者、应用和显式授权成员可访问。
- 飞书文档如使用 `--public` 或链接公开权限，飞书可能显示为“外部”；除非用户明确要求外部链接，否则不要使用。
- 为了方便查看本应用创建的文档，优先把 `FEISHU_DEFAULT_FOLDER_TOKEN` 指向一个固定飞书文件夹，例如 `ADS Agent Reports`；所有 Codex/Cursor 只要复用同一份 `.env`，创建的文档都会进入同一个目录。
- 重要报告发群时，消息里保留文档标题、类型、链接和日期；后续可以再维护一个 `ADS Agent 文档索引` 飞书电子表格，集中登记所有自动创建的 docx/sheets 链接。
- 飞书 CLI 使用应用身份 `tenant_access_token`，不是某个同事的个人身份；默认只能操作应用创建的文档、应用被加为协作者的文档，或应用已有管理权限的文档。
- 不要给飞书应用开启“读取/搜索企业所有云文档”“审计/管理全租户文件”“以用户身份访问全部文档”等全局权限；如果某些文档只能由指定管理员编辑和授权分享，就不要把应用加为这些文档的协作者，也不要给应用管理权限。
- 需要 AI 处理既有飞书文档时，必须由文档 owner 或有管理权限的人把应用显式加为协作者，且按任务给 `view` / `edit` / `full_access`，任务结束后可移除。

## Codex 输入需求

先用自然语言解析成计划：

```powershell
.\.venv\Scripts\python -m adwords_agent.cli task "创建广告，客户 2345678901，广告组 999888777，落地页 https://example.com"
```

为了可靠执行，真正 mutate 建议使用 JSON 任务文件。默认是 dry-run，不会改 Google Ads：

```powershell
.\.venv\Scripts\python -m adwords_agent.cli create-rsa examples\create_rsa.json
```

确认无误后加 `--execute`：

```powershell
.\.venv\Scripts\python -m adwords_agent.cli create-rsa examples\create_rsa.json --execute
```

更新广告文案：

```powershell
.\.venv\Scripts\python -m adwords_agent.cli update-rsa examples\update_rsa.json --execute
```

暂停广告：

```powershell
.\.venv\Scripts\python -m adwords_agent.cli pause-ad --customer-id 2345678901 --ad-group-id 987654321 --ad-id 111222333 --execute
```

## 报告

查看内置报告：

```powershell
.\.venv\Scripts\python -m adwords_agent.cli list-reports
```

生成 Markdown：

```powershell
.\.venv\Scripts\python -m adwords_agent.cli report --name daily_campaign --date-range YESTERDAY
```

## 飞书 CLI

为了方便整个项目文件夹一键转移，飞书相关文件统一放在：

```text
tools\feishu-cli
```

把你之前那个飞书 CLI 可执行文件复制到这个目录，文件名用下面任意一个：

- `feishu.exe`
- `feishu-cli.exe`
- `lark.exe`
- `lark-cli.exe`
- `feishu.ps1`
- `lark.ps1`

项目会调用：

```powershell
tools\feishu-cli\send-file.ps1
```

默认包装脚本会执行：

```powershell
feishu send --chat-id oc_xxx --file reports\report.md
```

如果你之前那个应用的参数不是这个格式，只改 `tools\feishu-cli\send-file.ps1` 一处即可。

只打印将要执行的飞书命令，不实际发送：

```powershell
.\.venv\Scripts\python -m adwords_agent.cli send-report reports\daily_campaign-20260616-171647.md --chat-id oc_xxx --dry-run
.\.venv\Scripts\python -m adwords_agent.cli feishu-test --chat-id oc_xxx --file reports\daily_campaign-20260616-171647.md
```

发送已有报告文件：

```powershell
.\.venv\Scripts\python -m adwords_agent.cli send-report reports\daily_campaign-20260616-171647.md --chat-id oc_xxx
```

生成报告后发送到飞书：

```powershell
.\.venv\Scripts\python -m adwords_agent.cli report --name daily_campaign --send-feishu --chat-id oc_xxx
```

## 每天自动发送飞书报告

先手动跑一次，确认 Google Ads 凭据和飞书 CLI 都可用：

```powershell
.\scripts\run_daily_report.ps1 -ReportName daily_campaign -ChatId oc_xxx
```

注册 Windows 每日计划任务，例如每天 09:00：

```powershell
.\scripts\register_daily_report_task.ps1 -At "09:00" -ReportName daily_campaign -ChatId oc_xxx
```

## 安全策略

- 广告 mutate 命令默认 dry-run。
- 只有加 `--execute` 才会真实调用 Google Ads API。
- 建议先创建为 `PAUSED`，人工检查后再启用。
- Cloud IAM 不需要给 Service Account 额外项目角色。
- 真正控制广告权限的是 Google Ads/MCC 里的账号访问权限。

## 转化金额核对注意事项

- 比较 Ads 的 `conversion_action.value_settings` 与 GTM 已发布标签参数；Ads 生成的安装代码不代表网页已经部署的代码。
- `always_use_default_value=true` 时使用 Ads 默认金额；为 `false` 时默认金额主要用于事件金额缺失或无效等情况。当前设置不能反推历史报表一直采用相同金额，金额设置变更也不追溯重算此前转化。
- API v24 不能在 SELECT 中选整个 `conversion_action.google_analytics_4_settings`，需要选择支持的具体子字段；`ChangeEventResourceType` 不包含 `ConversionAction`，不能承诺通过 change_event 重建转化动作金额的变更历史。

## 暂停全部广告时的 API 注意事项

- 2026-09-15 经本机 v24 SDK 验证：`CampaignService.mutate_campaigns` 的 `validate_only` 和 `partial_failure` 应放入 `MutateCampaignsRequest`，再通过 `request=request` 调用；不能作为该方法的直接关键字参数。
- 实验系列（`campaign.experiment_type=EXPERIMENT`）不能直接修改系列状态，否则会返回 `CANNOT_MODIFY_FOR_TRIAL_CAMPAIGN`。盘点“全部启用”时同时读取 `campaign.primary_status` 和 `primary_status_reasons`；原始状态为 `ENABLED` 的历史实验可能已是 `ENDED / CAMPAIGN_ENDED`，不能把它算作仍在投放，也不能声称已将它暂停。
- 批量暂停须保存原状态、逐项计划和 API 校验结果。执行后直接回读目标状态，并另查 `change_event`；历史记录尚未出现时明确记录“未观察到”，不得替代或夸大直接回读证据。

## 官方资料

- [Google Ads API Python client](https://developers.google.com/google-ads/api/docs/client-libs/python)
- [Create responsive search ads](https://developers.google.com/google-ads/api/docs/responsive-search-ads/create-responsive-search-ads)
- [Mutate responsive search ads](https://developers.google.com/google-ads/api/docs/ads/mutate-ads)
