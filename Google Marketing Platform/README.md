# Google Marketing Platform Access Agent

在这个目录里，用一个 Agent 统一管理同事的 **Google Analytics（GA4）、Google Tag Manager（GTM）、Google Search Console（GSC）和 Google Ads** 权限。

本项目也提供 Google Marketing Platform 组织层的只读发现。组织、角色和证据需要使用者自行配置；示例配置不代表任何真实账号的权限或在线验证结果。

你可以直接说：

> 把 `user@example.com` 加入 Demo 的 GA、GTM、Search Console 和 Adwords，按入职只读权限。

Agent 会先保存不可变计划，经你确认后调用官方 API。SA / 公开 API 无法完成的权限项，可按指定 Chrome 管理员身份独立跟进；这不改变 CLI 对 GSC 返回 `manual_required` 的事实。

## 安全边界

- 默认使用本地 CLI 和公开 API；不使用管理员浏览器读取报表或进行日常业务操作。
- 只有用户明确要求浏览器/UI 操作时，才由其指定的产品管理员补足 SA / API 能力；GCP SA 生命周期使用独立身份。详见 [身份说明](knowledge/chrome-identities.md) 和 [根目录规则](../AGENTS.md)。
- 浏览器走当前 Chrome skill，核对可见身份、准确资源，并在提交前确认清单。禁止 Cookie / token 复用、浏览器凭据读取、私有网页 API 或旧 UI 脚本。
- 所有变更命令只生成计划，不能直接执行；不支持在原始命令后添加 `--execute`。
- 计划创建后内容不可修改。邮箱、品牌、产品、角色或资源有任何变化，都必须生成新的 `plan_id`。
- apply 会校验计划生成时的 `catalog.yaml` 指纹；catalog 后续有任何变化，旧计划都会失效。
- 计划是 single-use：远端执行尝试正式开始后，无论结果是成功、失败、`partial` 还是 `unknown`，都不能重放旧计划；先只读复核，再按当前状态生成新计划。
- 离职计划会在生成前和 apply 锁内各做一次只读资源完整性核对；GA/GTM 按账号边界，GSC 按站点，Ads 按 MCC 与客户树。读取失败或 catalog 双向不一致都会在任何远端写入前阻断。
- 执行时必须同时提供计划 ID 和同值确认参数：`gmp apply PLAN_ID --confirm PLAN_ID`。
- 可由 API 管理的 GA / GTM / Ads Admin 权限，还需要在生成计划和执行计划两个阶段都显式提供 `--allow-admin`。GSC Owner 不可由本 CLI 执行。
- 四个平台采用跨平台非事务执行。系统逐项执行、逐项审计，不会把“部分完成”说成“全部成功”。

## 连接与能力检查

配置自己的凭据后运行 `gmp doctor`，以当前结果判断读取、人员管理和后续处理能力。仓库不包含真实账号的连接结果或历史资源数量。

重要限制：

- `gmp auth login` 可以为 GA、GTM 提供可选管理员 OAuth，但不会覆盖 Ads 的专用服务账号，也不能补出一个不存在的 GSC 用户 ACL API。
- 公开的 [Google Marketing Platform Admin API v1alpha](https://developers.google.com/marketing-platform/devguides/api/admin/v1/rest) 只公开组织读取、Analytics account links、Property usage 和 service level 相关方法；它没有 `users`、`memberships`、`roles` 或 `permissions` 资源，不能新增、删除或修改组织人员角色。
- GMP Admin API 未启用时会阻止 `gmp_org` 的组织 / Analytics account link 读取；启用 API 也不会提供组织人员 ACL endpoint。
- `write_candidate=true` / `write_unverified=true` 只表示凭据值得在已确认计划中尝试产品 API，并不表示已经验证写权限，更不表示人员权限已经修改。
- GSC Full / Restricted 权限进入同一跨平台计划；CLI 结果只能是 `manual_required`。经确认的 Chrome 跟进另存实际结果，不能把旧 API 审计改成成功。
- Ads API 发出用户邀请后，状态是“待接受”；收件人必须点击邮件并接受，才算最终获得权限。
- `--allow-admin` 只是额外安全确认，不会绕过 Google API、本账号角色或 GSC 的能力限制。

## 关联现有项目

本 Agent 引用相邻项目已经配置的凭据和资源目录，不复制任何密钥：

| 产品 | 关联项目 | 使用内容 |
|---|---|---|
| GMP Organization | `GMP_ORG_CREDENTIALS`（默认复用 GTM 凭据路径） | `YOUR_GMP_SA` 身份与 Your Organization 组织证据；仅用于公开 v1alpha 只读组织 / Analytics account link 能力 |
| GA4 | `../GA MCP` + GMP organization 凭据候选 | Analytics Admin API 凭据、账号、Property 与 AccessBindings |
| GTM | `../GTM MCP` | Tag Manager API 凭据、Your Organization、Container 与 UserPermissions |
| GSC | `../SEO-Agent` | Search Console Service Account 与 Property 列表 |
| Google Ads | `../Adwords API` + 专用人员管理密钥路径 | 只读复用 developer token；使用 `YOUR_GMP_SA` 管理人员，不采用投放项目的登录身份 |

`.env` 只保存相邻凭据路径，不保存密钥内容。OAuth client 与 token 只允许放在已被 `.gitignore` 排除的 `credentials/` 目录；不要把 secret、refresh token 或私钥写入 `.env`、源码、对话或日志。

### Ads 身份隔离

- `Google Marketing Platform`：固定使用 `YOUR_GMP_SA@YOUR_GCP_PROJECT.iam.gserviceaccount.com` 管理人员。
- `Adwords API`：保留 `YOUR_ADS_SA@YOUR_GCP_PROJECT.iam.gserviceaccount.com` 管理广告投放；其配置无需修改。
- `GMP_ADS_CREDENTIALS` 是本项目可选的专用密钥路径，未配置时引用 GMP / GTM 的密钥路径。代码校验固定邮箱，密钥缺失或身份错误就停止，绝不回退到投放身份。
- `GMP_ADS_YAML` 仅作为 developer token 等必要非身份参数的只读来源。共享 YAML 的登录身份、代登录和通用 OAuth token 都不参与本项目的 Ads 身份选择。配置只在内存组合，不复制密钥或改写共享文件。
- MCC 的 ADMIN 角色不等于所有子账号的人员写入均已验证；仍按用户确认的计划执行，并逐项报告 API 与回读结果。

管理员 OAuth 是 GA、GTM 的一种可选写入身份；如果 Service Account 的产品级 API 权限不足，可用对应资源的管理员账号完成 OAuth（Ads 始终保留上述专用身份）：

```powershell
.\.venv\Scripts\gmp.exe auth login
.\.venv\Scripts\gmp.exe doctor
```

## 安装与只读检查

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
.\.venv\Scripts\gmp.exe doctor
.\.venv\Scripts\gmp.exe catalog
.\.venv\Scripts\gmp.exe auth status
.\.venv\Scripts\gmp.exe discover --product gmp-org
```

`doctor` 现在包含辅助项 `products.gmp_org`，明确区分组织证据、API 启用状态和人员 ACL 能力。`gmp discover --product gmp-org` 只读取组织与 Analytics account links；它不能列出组织用户或证明组织角色。当前 API 未启用时该命令失败是预期状态，不影响产品 ACL 流程。

在承诺任何写入前都要先运行 `doctor`。`catalog` 用于核对品牌别名和实际资源 ID；不要根据品牌名称猜资源。

## 两阶段变更流程

### 1. 生成不可变计划

自然语言示例：

```powershell
.\.venv\Scripts\gmp.exe task "把 user@example.com 加入 demo 的 ga gtm sc adwords，按入职只读权限"
```

显式命令示例：

```powershell
.\.venv\Scripts\gmp.exe grant --email user@example.com --brands demo --products ga,gtm,gsc,ads --preset onboard
```

命令会保存计划并返回 `plan_id`。确认前至少核对：

- 人员邮箱和操作类型；
- 品牌、产品、资源名称与资源 ID；
- 目标角色与操作语义；现有权限会在 apply 时由 API 再读取并做幂等差异判断；
- 哪些项目可自动执行，哪些是 `manual_required`；
- 是否包含 GA / GTM / Ads Admin、被拒绝的 GSC Owner 请求或 Ads MCC；
- Ads 邀请是否需要收件人接受。

### 2. 明确确认并执行

```powershell
.\.venv\Scripts\gmp.exe apply PLAN_ID --confirm PLAN_ID
```

例如计划 ID 是 `0123456789abcdef`：

```powershell
.\.venv\Scripts\gmp.exe apply 0123456789abcdef --confirm 0123456789abcdef
```

如果用户修改了邮箱、资源或角色，不要执行旧计划，重新生成计划。

即使用户没有修改参数，只要 `catalog.yaml` 的指纹与计划生成时不同，apply 也会拒绝旧计划。一个计划的远端执行尝试一旦开始便被消费；遇到 `blocked`、`error`、`partial` 或 `unknown` 时，先用 `gmp who` / `discover` 复核，再生成并确认新计划，绝不能重放旧 `plan_id`。

管理员权限需要双重确认：

```powershell
.\.venv\Scripts\gmp.exe set-role --email user@example.com --brands demo --products ga --role admin --allow-admin
.\.venv\Scripts\gmp.exe apply PLAN_ID --confirm PLAN_ID --allow-admin
```

GSC Owner 不在这条自动化路径内：即使传入 `--allow-admin`，计划预览也会被拒绝；必须由现有 Owner 在 Search Console 手动处理并复核。

## 各操作的精确定义

| 操作 | 语义 |
|---|---|
| `grant` | 只新增缺失权限或提升较低权限，绝不降低已有权限。已有角色更高时应返回不变。 |
| `set-role` | 精确替换目标角色，可能升权也可能降权。必须只指定一个产品和一个明确角色；资源清单必须在计划中展开。 |
| `revoke` | 只撤销命令中列出的目标资源，不扩展到同品牌其它资源或其它产品。 |
| `onboard` | 按入职模板生成 `grant` 计划，仍遵守“只增不降”。 |
| `promote` | 按晋升 / 新项目模板生成提升计划，不能借此降低已有权限。 |
| `offboard` | 离职专用：先实时核对 catalog 完整性；GA 和 GTM 按已映射账号执行账号级全量撤权（因此也可能影响该账号下未逐项列入 catalog 的资源）；Ads 覆盖完整实时客户树与 MCC；GSC 全部实时已知站点进入 `manual_required`。 |
| `task` | 把中文自然语言解析成上述操作。只读查询可直接返回；任何 mutation 仍只生成计划。 |

常用示例：

```powershell
# 只新增 / 提升，不降低现有权限
.\.venv\Scripts\gmp.exe grant --email user@example.com --brands demothree --products ga,gtm,ads --preset project

# 精确设定一个产品的角色
.\.venv\Scripts\gmp.exe set-role --email user@example.com --brands demo --products ga --role editor

# 只撤 Demo 的 GA 目标资源
.\.venv\Scripts\gmp.exe revoke --email user@example.com --brands demo --products ga

# 离职：生成全资源清理计划
.\.venv\Scripts\gmp.exe offboard --email user@example.com
```

`offboard` 故意不接受 `--brands` 或 `--products`；需要局部撤权时必须使用 `revoke`，防止把局部参数静默扩大成全量离职操作。确认离职计划时重点核对 GA / GTM 的账号级动作、`account_wide_revoke` 标记和 `offboard_preflight` 报告。若预览后新建了资源，apply 前的第二次核对会拒绝旧边界；先更新 catalog，再生成新计划。

CLI 的完整性门禁不代表管理员浏览器可见及历史 UI 授权的全部资源都已覆盖。全量离职还须核对这些资源，独立确认和回收 UI-only 项；未核全或未处理的目标须明确报告，不能仅凭原 CLI `complete=true` 宣称整体离职完成，也不能借 UI 绕过 CLI 门禁。

## 结果与审计

一次 `apply` 可能同时出现：`ok`（写后校验完成）、`skipped`（无需变更）、`pending_acceptance`、`manual_required`、`blocked`、`partial`、`unknown` 或 `error`。输出必须按“产品 + 资源 ID”逐项报告。

结果字段的含义是：顶层 `ok=true` 表示没有 `blocked/partial/unknown/error`；只有 `complete=true` 才表示所有动作都是 `ok/skipped`；`requires_follow_up=true` 表示仍有 GSC `manual_required` 或 Ads `pending_acceptance`。`partial` / `unknown` 表示远端最终状态不能安全断言，必须只读复核且不得重放旧计划。

CLI 退出码：`0` 表示 `complete=true`；`2` 表示调用本身没有失败但仍有 `manual_required` / `pending_acceptance` 等后续事项；`1` 表示 blocked、unknown、error、校验失败或其它失败。自动化必须同时读取 JSON 的 `ok`、`complete` 和 `requires_follow_up`，不能只看 `ok`。

查看审计历史：

```powershell
.\.venv\Scripts\gmp.exe history
```

`history` 用于追踪计划内容、确认信息、每次执行尝试和逐资源结果。审计记录不得包含 token、私钥或 OAuth secret。

## 浏览器权限跟进、入口与历史材料

受支持的程序化入口只有安装后的 `gmp` CLI，即 `.\.venv\Scripts\gmp.exe`。文档新增权限回退不会增加 GSC ACL API，也不改变 CLI 的确认、single-use、身份隔离和验证逻辑。

SA / API 做不到的人员权限可使用当前 Chrome skill 连接指定 profile，按 [项目规则](AGENTS.md) 的“经授权的 Chrome 权限回退”执行：独立准确清单、必要确认、权限回读与访问验证。找不到资源不能擅自创建、验证或换号扩大范围。

API 和 UI 实际执行的权限结果都须通过本地 `feishu-cli` 追加到[飞书操作记录](https://your-org.feishu.cn/wiki/YOUR_FEISHU_WIKI_TOKEN?sheet=YOUR_SHEET_ID)并回读。保留旧 `manual_required` 行；UI 跟进用独立 ID，执行方式为 `manual`，详情标明 `Chrome UI` 和操作者。

旧 UI / Chrome 脚本以及 `ops/` 的历史快照不是可重新执行的授权入口，不能绕过计划、确认或身份检查。待确认表单不是已授权；安全 CLI 验证 skill 仍只读，不增加真实写入或浏览器测试。
