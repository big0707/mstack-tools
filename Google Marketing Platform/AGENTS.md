# Google Marketing Platform Access Agent

本目录用于统一管理同事在 Google Analytics、Google Tag Manager、Google Search Console 和 Google Ads 的人员权限。用户通常会用中文描述入职、离职、升职或负责新项目。

## 强制工具边界

1. 默认使用本项目 `gmp` CLI、相邻项目 CLI 及其公开 API 封装。内容查询、分析和日常业务操作仍走 CLI；先查本地入口和帮助，不用网页报表代替。
2. 只有用户针对当前任务明确要求浏览器/UI 操作时，才可使用其指定的产品管理员身份补足 SA / 公开 API 无法完成的权限操作。模板配置和历史记录不代表授权。
3. 必须使用当前 Chrome 控制 skill 和官方连接，先核对可见账号邮箱及具体资源的实际权限。禁止 Cookie / 网页 token 复用、浏览器凭据读取、Google 私有网页 API 或旧 UI 自动化脚本。
4. GCP Service Account 生命周期使用另一身份 `YOUR_GCP_ADMIN@example.com`，主要项目 `YOUR_GCP_PROJECT`；不能与产品权限管理员混用。范围与证据见 [身份说明](knowledge/chrome-identities.md) 和 [根目录规则](../AGENTS.md)。
5. CLI 仍通过不可变计划和 `apply` 执行支持的 API 变更。缺少 `apply` / `history` 时报告 CLI 不完整，禁止 `--execute`。获准的浏览器回退是独立、需确认和审计的跟进，不能伪装成 CLI 成功。
6. 旧 UI / Chrome 脚本不是支持入口；`ops/` 中带日期的截图、清单和结果是证据，不是重放或后续变更授权。URL、旧截图、扩展安装也不是具体执行确认。

## 凭据与项目关联

通过配置路径引用以下相邻项目，不复制密钥：

- GA：`../GA MCP`
- GTM：`../GTM MCP`
- GSC：`../SEO-Agent`
- Ads：只读复用 `../Adwords API` 的 developer token；人员管理身份单独使用 `GMP_ADS_CREDENTIALS`，默认引用 GMP / GTM 的 `YOUR_GMP_SA` 密钥路径。

### Ads 人员管理与广告投放必须隔离

- 本目录的 Ads 人员管理固定使用 `YOUR_GMP_SA@YOUR_GCP_PROJECT.iam.gserviceaccount.com`。
- `../Adwords API` 的广告投放继续使用 `YOUR_ADS_SA@YOUR_GCP_PROJECT.iam.gserviceaccount.com`。不得为了本项目修改其 YAML、代码、凭据或账号权限。
- 本项目仅在内存中组合 Ads SDK 配置，不复制 developer token 或私钥。共享 YAML 的登录身份和通用 `gmp auth login` 都不能覆盖人员管理身份。
- CLI/API 身份选择中，专用密钥缺失、无法读取或邮箱不匹配时必须停止，禁止回退到投放服务账号、共享 YAML 的 OAuth 或其它身份。另行确认的 `product-admin` Chrome 跟进不能覆盖这条程序化身份约束。

不得在调试或对话中读取、打印整份 `.env`、Service Account JSON、Google Ads developer token、OAuth client secret、refresh token 或私钥内容。运行时配置加载器可以读取所需路径值；只可对外报告文件是否存在、凭据类型、账号标识和 API 返回的能力状态。

GA、GTM 的产品级服务账号权限不足时，可由对应资源管理员完成可选 OAuth 登录：

```powershell
.\.venv\Scripts\gmp.exe auth login
```

OAuth 登录不会改变 Ads 的专用服务账号，也不会改变 GSC 缺少公开用户 ACL API 的事实。

## GMP Organization 证据与 API 边界

- `catalog.yaml` 只提供占位组织与角色示例。使用者自行配置组织资源和证据；不能把模板当作已验证的授权。
- 人工截图证据与公开 API 验证必须分开记录，不得用组织角色推断产品权限或 mutation 成功。
- 公开 Google Marketing Platform Admin API 的组织发现能力仅用于组织、Analytics account links、Property usage 和 service level；组织用户或角色管理不属于本 CLI 的写入能力。
- `gmp doctor` 的辅助项 `gmp_org` 分别报告角色证据、API 启用状态和人员 ACL 能力，`gmp discover --product gmp-org` 用于只读发现。
- 员工权限执行通道仍是：GA 用 Analytics Admin API，GTM 用 Tag Manager API，Ads 用 Google Ads API，GSC 返回 `manual_required`。

## 当前能力检查

使用者配置自己的凭据后，每次处理权限前运行 `gmp doctor`，以实时结果为准。仓库不保存具体账号的历史资源数量、组织角色或在线验证结论。

不得把“能读取用户或资源”解释成“能修改用户”。`write_candidate` / `write_unverified` 只允许在用户确认后的 single-use 计划里尝试对应产品 API，并要求写后读取校验；它们不表示远端已改动，也不允许对用户承诺写入一定成功。

## 用户语言映射

- GA、Analytics、Google Analytics → `ga`
- GTM、标签、Tag Manager → `gtm`
- Search Console、SC、GSC → `gsc`
- Adwords、Google Ads、Ads → `ads`
- 入职、新同事、加入 → `onboard` 或 `grant`
- 升职、负责新项目 → `promote` 或 `grant` 的项目模板
- 明确“离职 / 全量收回” → `offboard`
- 删除 / 移除某个品牌或产品 → `revoke`；目标不全时先澄清，不能擅自扩大成离职
- 改成某角色、精确调整 → `set-role`

品牌或资源不明确时先运行 `gmp catalog`，不要猜测或混用 Demo 与其它品牌。只有用户明确要求全部品牌，才能选择 `all`。

## 只读命令

`doctor`、`catalog`、`who`、`discover`、`auth status` 和 `history` 是只读命令，可以直接运行。`task` 只有在解析为只读查询时才可直接返回查询结果。

```powershell
.\.venv\Scripts\gmp.exe doctor
.\.venv\Scripts\gmp.exe catalog
.\.venv\Scripts\gmp.exe who EMAIL
.\.venv\Scripts\gmp.exe discover --product ga
.\.venv\Scripts\gmp.exe discover --product gmp-org
.\.venv\Scripts\gmp.exe history
```

`gmp_org` 是只读辅助诊断面，不是 mutation product；不要把它加入员工授权 action，也不要把 `gmp who` 当成组织成员查询。

## CLI Mutation 必须走不可变计划

CLI 的 `grant`、`revoke`、`set-role`、`onboard`、`offboard`、`promote`，以及解析为 mutation 的 `task`，都必须遵守以下流程。浏览器回退见后文独立跟进规则，不得改写本流程的 API 结果：

1. 运行 `doctor`，确认实时读写能力。
2. 运行 mutation 命令，只生成并持久化计划。
3. 向用户展示计划中的邮箱、操作、品牌、产品、角色、资源名称和资源 ID，以及管理员项、人工项和 Ads 邀请项。
4. 返回不可变 `plan_id`，等待用户针对这份计划明确说“确认 / 执行”。
5. 仅在明确确认后运行：`gmp apply PLAN_ID --confirm PLAN_ID`。
6. 运行 `gmp history`，按产品和资源报告最终结果。
7. 对任何已经 apply 的加人、减人或改权计划，把每个最终 action 逐行同步到指定飞书“操作记录”Sheet，并回读验证；不得只写本地审计。

禁止在原始 mutation 命令上使用 `--execute`。原始命令永远不得直接修改 Google 侧状态。

计划一旦生成不可修改，并绑定生成时的 `catalog.yaml` SHA-256。用户修改邮箱、资源、产品、操作或角色，或者 catalog 在计划生成后发生变化时，旧计划作废，必须创建新计划；不得在 apply 阶段偷偷重解释计划。

计划是 single-use。远端执行尝试正式开始后，无论得到成功、失败、`partial` 或 `unknown`，该 `plan_id` 都不可再次 apply。先用 `gmp who`、`discover` 和产品 API 做只读复核，再根据当前状态生成并确认新计划。只有 start audit 写入前失败、且确认没有远端调用时，CLI 才可撤销本地 claim。

离职计划在创建前和 apply 锁内、claim/audit/mutation 前必须各执行一次 fail-closed 资源完整性门禁：GA 比账号、GTM 比账号（账号级删除覆盖全部容器）、GSC 比 site URL、Ads 比 MCC 与客户树。任何只读错误、catalog-only 或 live-only 差异都不得生成或执行计划。apply 前门禁失败不能消费 plan。

该 CLI 门禁只比较其认证身份可发现的资源，不能证明覆盖管理员浏览器可见或历史 UI 授权的全部资源。全量离职还须在权限页面核对管理员可见清单，并与历史 API/UI 授权记录对账；仅 UI 可见的目标须独立列入确认和回收结果。未核全、不可访问或仍未回收时不得报告“全量完成”，即使原 CLI plan 返回 `complete=true`。不得借浏览器绕过原 CLI 门禁或静默扩大已确认的 API plan。

自然语言示例：

```powershell
.\.venv\Scripts\gmp.exe task "把 xxx@abc.com 加入 demo 的 ga gtm search console 和 adwords，按入职只读权限"
```

确认示例：

```powershell
.\.venv\Scripts\gmp.exe apply PLAN_ID --confirm PLAN_ID
```

## 操作语义

### grant / onboard / promote

- 只新增缺失权限或提升较低权限。
- 已有权限高于计划目标时保持不变，绝不降权。
- 不得把“已拥有更高权限”当成一次新写入。

### set-role

- 精确替换目标角色，可以升权，也可以降权。
- 必须只指定一个产品和一个明确角色。
- 计划中必须展开所有目标资源 ID；模糊角色或多产品请求必须拆分成多份计划。

### revoke

- 只撤销用户明确选择的目标资源。
- 不得扩大到同品牌其它资源、其它产品、Ads MCC 或其它品牌。

### offboard

- 离职是全量操作，而不是普通 `revoke`；该命令不接受品牌或产品范围参数。
- GA 与 GTM 按 catalog 中映射的账号生成账号级全量撤权，因此可能同时移除该账号下未逐项列入 catalog 的资源访问；计划必须展示账号 ID、scope 和 `account_wide_revoke`。
- Ads 覆盖 catalog 中全部客户和 MCC；GSC 展开全部已知站点。
- GSC 项仍返回 `manual_required`；它们必须出现在计划、最终结果和审计中。

## Admin 双重确认与 GSC Owner 禁区

默认拒绝 GA Admin、GTM Admin、Ads ADMIN、GSC Owner 等管理员权限。

只有用户明确点名 GA / GTM / Ads 管理员权限时，生成计划命令才可带 `--allow-admin`；执行同一计划时还必须再次带 `--allow-admin`：

```powershell
.\.venv\Scripts\gmp.exe set-role --email EMAIL --brands BRAND --products ga --role admin --allow-admin
.\.venv\Scripts\gmp.exe apply PLAN_ID --confirm PLAN_ID --allow-admin
```

`--allow-admin` 不得绕过 `doctor`、官方 API 权限检查或 GSC 的 `manual_required`。

GSC Owner 永远不能由本 CLI 执行：即使带 `--allow-admin`，预览也必须返回 `blocked`，由现有 Owner 手动处理。

## GSC 特别规则

- Search Console API 能列出 Property 和当前认证主体的权限，但没有给指定邮箱管理 Full / Restricted User 的公开 ACL 方法。
- 不得把 `sites.add` / `sites.delete` 当作人员权限 API；它们没有目标邮箱参数。
- 不得用内部网页 API、Cookie / token 复用或 Site Verification Owner 操作来冒充 Full / Restricted User 管理。
- GSC 权限项照常进入统一计划；apply 时记录 `manual_required`、目标 Property、目标角色和人工下一步。
- CLI 的 `manual_required` 绝不能计入成功；之后经授权的 Chrome UI 跟进单独记录结果，不能回写旧 API audit 为成功。

## 经授权的 Chrome 权限回退

- 只用于用户要求的授权、成员新增/移除、权限调整，以及必需的权限页核验。`YOUR_PRODUCT_ADMIN@example.com` 不用于报表读取、投放、预算/出价、内容发布、GTM 标签修改/发布或 GCP SA 删除。
- 先查 CLI 能力或明确公开 API 缺口，不盲目重复失败写入。GSC 无用户 ACL API 时可直接进入获准的 UI 跟进；API 不支持不等于要求用户亲自点完所有步骤。
- 先读根目录身份路由和 Chrome skill；执行时核对页面邮箱与精确资源。未连接正确 profile、未登录、无目标资源或无管理权限时停止该项，不改用另一个高权限账号。
- 保存独立且确认后不可修改的 UI 清单：稳定 `ui_plan_id`、实际操作者、对象邮箱、动作、产品、实际资源 ID、目标角色、原因，以及相关 CLI plan ID（如有）。目标变化则新建清单；UI 清单不能传给 `gmp apply`。
- 提交前展示清单并遵守 Chrome skill 的动作时确认；同批准确且未变化的范围可一次确认。安装扩展、指定 profile 或允许日后回退，都不等于确认某次具体权限写入。
- `grant` 仍只增不降，先查已有权限；查询用途使用最小可用角色，不擅自授予 Owner/Admin。域名资源须说明覆盖子域名。找不到资源不能擅自新建、验证或扩大到其它站点。
- 单项提交后回读用户和角色；可用时再用目标身份的 API 验证访问，分别报告“页面已授权”和“查询已通过”。不确定先只读复核，不盲重试。
- 独立本地最终结果落盘后，按下文同步飞书。执行方式使用现有 `manual`，详情标明 `Chrome UI`、实际操作者及验证结果；不写成 `api`，不覆盖旧 `manual_required`。
- 员工离职不等于删除共享 GCP SA。SA 生命周期、密钥和 IAM 变更须独立明确请求、影响说明及必要确认，路由到 `YOUR_GCP_ADMIN@example.com` 或未来经配置验证的专用管理身份。

## Ads 特别规则

- 本项目固定使用专用 `YOUR_GMP_SA` Service Account；投放项目的 `YOUR_ADS_SA` 不能用于本项目人员管理。
- 每次运行 `doctor` 核对实际 `credential_email`、`credential_role` 与 `write`。MCC ADMIN 检查通过后，仍只能在用户确认的计划中调用官方 Ads API；子账号的人员管理能力以目标 API 的实际结果及写后校验为准。
- API 调用成功只表示邀请已发出。收件人接受邮件前，必须报告为“待接受”，不能报告最终开通成功。

## 跨平台非事务结果与审计

GA、GTM、GSC、Ads 之间不是一个事务。apply 必须逐项执行并逐项记录，不得承诺全有或全无，也不得因一个产品成功就汇总为整体成功。

回复用户时至少区分：

- 已实际完成；
- 无需变更；
- Ads 邀请待接受；
- `manual_required`；
- `blocked` / `error`；
- `partial` / `unknown`，并明确最终远端状态尚不能安全断言。

顶层 `ok=true` 只表示没有 `blocked/partial/unknown/error`；只有 `complete=true` 才表示全部动作均为 `ok/skipped`；`requires_follow_up=true` 表示仍有 `manual_required` 或 `pending_acceptance`。任何 `partial` / `unknown` 都要求只读复核且不得重放旧计划。

apply 退出码必须保持：完成为 `0`；仍需人工或接受邀请为 `2`；失败或状态不确定为 `1`。调用方仍须读取 JSON 状态字段，不能只靠退出码推断逐资源结果。

每项结果必须包含产品和资源 ID。执行后运行 `gmp history`，引用对应 `plan_id` 汇报审计结果。日志中不得出现任何密钥或 token。

## 飞书权限操作记录（强制）

所有已确认并执行的 `grant`、`revoke`、`set_role`、`onboard`、`offboard`、`promote` 计划，都必须在本地 finished audit 落盘后，把最终逐资源结果写入以下飞书工作表。Chrome UI 跟进也先保存独立本地最终结果，再追加到同一表：

- 用户提供的 Wiki：`https://your-org.feishu.cn/wiki/YOUR_FEISHU_WIKI_TOKEN?sheet=YOUR_SHEET_ID`
- Wiki node token：`YOUR_FEISHU_WIKI_TOKEN`
- 通过飞书 Wiki API 解析出的 spreadsheet token：`YOUR_FEISHU_SHEET_TOKEN`
- sheet ID：`YOUR_SHEET_ID`
- sheet 名称：`操作记录`
- 唯一允许的工具：`.\feishu-cli\feishu-cli.cmd`

只记录实际执行的最终结果，不记录 dry-run 或待确认清单。CLI 使用 `plan_id`，独立浏览器跟进使用 `ui_plan_id`；详情引用原计划（如有），不覆盖旧行。每个 action 一行，固定列顺序为：

1. `记录ID`：`plan_id:三位序号`，例如 `20872bb1c42f4a56:001`；A 列永远不得为空。
2. `操作时间(UTC)`。
3. `计划ID`。
4. `操作人`：CLI 使用本地 audit 的 `local_actor`；Chrome UI 使用页面核实的 Google 账号邮箱；没有证据时明确写 `unknown`。
5. `对象邮箱`。
6. `动作`：grant / revoke / set_role。
7. `平台`：ga / gtm / gsc / ads。
8. `品牌`。
9. `资源名称`。
10. `资源ID`。
11. `目标权限`。
12. `执行方式`：api / manual。Chrome UI 使用 `manual`，详情中注明浏览器执行和实际操作者，保持现有表结构兼容。
13. `结果`：ok / skipped / pending_acceptance / manual_required / blocked / partial / unknown / error。
14. `详情`：最终结果 message。
15. `后续动作`：必要的 next_step；没有则留空。
16. `原因/工单`：plan reason；不得包含 credential、token、私钥或 OAuth secret。

独立 GCP SA 生命周期的审计约定（供以后明确执行时使用，不改现有 16 列，不表示已实现 GCP provider）：

- `计划ID` 使用该次独立生命周期操作 ID；`记录ID` 仍为操作 ID 加三位序号。先保存本地清单、确认与最终结果，不伪造 `gmp apply`。
- `动作` 使用真实的 `create_service_account` / `disable_service_account` / `enable_service_account` / `delete_service_account`；`平台` 为 `gcp_iam`。这些值只用于独立审计，不是 GMP CLI 的 mutation product 或命令。
- `对象邮箱` 为目标 SA 完整邮箱；`品牌` 无真实对应则留空；`资源名称` 包含实际项目 ID 和 SA 名称；`资源ID` 使用已核对的 GCP 完整资源名。
- `目标权限` 写 `不适用（SA 生命周期，未修改产品成员权限）`；实际执行主体写入 `操作人`。`执行方式`、`结果`、详情与回读规则保持原义，浏览器仍为 `manual` 并注明 `Chrome UI`。
- 密钥或 IAM 授权属于其它操作，不能套上述动作冒充已完成；需要独立请求和审计映射。产品侧回收另行记录，不能由 SA 删除推断。

写入规则：

- 必须先用 `read-sheet` 读取 A 列已有 `记录ID`，相同 ID 已存在时跳过，防止重复记录。
- 空表首次写入时，表头与首批记录一次追加；已有表头必须逐列匹配，绝不能覆盖或静默改列。
- 使用 `append-sheet` 追加，禁止用从 A1 开始的覆盖式 `writeSheetValues`。
- 追加后再次 `read-sheet`，确认本计划的所有 `记录ID` 和逐行内容都存在，才能向用户报告“飞书记录已完成”。
- 飞书会把邮箱和 URL 回读为富文本片段数组；校验时须按片段顺序拼接 `text` 后与原值比较，不能因为不是普通字符串就误判为空或失败。
- `append-sheet` 是非幂等追加。网络、5xx 或 429 导致结果不确定时禁止盲目重试；必须先回读 `记录ID`，然后只追加确认缺失的行。
- `manual_required`、`pending_acceptance`、失败和状态未知也必须记录真实状态，不能只记录成功项。
- 如果 Google 权限已经写入但飞书追加或回读失败，保留本地 audit，向用户明确报告“飞书记录待补”；绝不能回滚或重放原 Google plan。修复后只重试缺失的飞书行。
- 严禁使用 Browser、Chrome、DOM 或网页内部接口操作该表；Wiki token 必须经本地飞书 CLI 的认证 API 解析，或使用上面已验证的 spreadsheet token。

用中文回答，并明确区分“计划已生成”“用户已确认”“API 已执行”“等待邀请接受”和“需要人工处理”。
