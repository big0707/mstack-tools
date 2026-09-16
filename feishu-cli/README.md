# 飞书 CLI / Portable Feishu CLI

这是一个放在 `tools/feishu-cli` 内的便携飞书 CLI，供本项目和 AI Agent 调用，用于发送群消息、创建飞书文档、创建/读取飞书表格。

它已经兼容项目原有的调用方式：

```powershell
tools\feishu-cli\send-file.ps1 -ChatId oc_xxx -File reports\report.md
```

也可以直接调用新 CLI：

```powershell
tools\feishu-cli\feishu-cli.cmd send --chat-id oc_xxx --file reports\report.md
```

## 功能

- 发送文本或 Markdown 文件内容到飞书群。
- 创建飞书文档，支持标题、列表、代码块、粗体等基础 Markdown。
- 文档内插入真实表格，绕开飞书 Markdown 表格渲染不稳定的问题。
- 创建飞书电子表格并写入二维数据。
- 向现有飞书工作表末尾追加二维数据，不覆盖已有数据。
- 读取飞书电子表格并输出 JSON。
- 查询机器人所在群的 `chat_id`。
- 通过邮箱或手机号查询用户 `open_id`。
- 结构化 JSON 输出，适合 AI Agent 解析。
- API 请求带超时、重试和 tenant token 自动刷新。
- 读文件自动识别编码（UTF-8 / UTF-8 BOM / UTF-16 LE/BE / GBK 回退），Windows 上错误编码的文件不会再把中文读坏。
- 写文档/表格/发消息前自动做乱码检测：内容含 `??`、U+FFFD 或中文旁的半角问号时直接报错拒发，防止把乱码写进飞书。确认误报时可加 `--force` 跳过。

## 文件结构

```text
feishu-cli/
├── src/
│   ├── api.js        # 飞书 API 封装
│   ├── cli.js        # 命令行入口
│   └── index.js      # SDK 类
├── feishu-cli.cmd    # Windows 启动器
├── send-file.ps1     # 本项目报告发送 wrapper
├── .env.example      # 环境变量示例
├── package.json
└── package-lock.json
```

## 安装

需要 Node.js 18+。

```powershell
cd tools\feishu-cli
npm install
```

如果从完整项目包迁移，`node_modules` 可能已经随包带上；没有的话重新运行 `npm install` 即可。

## 配置

复制 `.env.example` 为 `.env`：

```powershell
Copy-Item .env.example .env
```

填写：

```env
FEISHU_APP_ID=cli_xxxxxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxx
FEISHU_DEFAULT_FOLDER_TOKEN=
FEISHU_DEFAULT_SHARE_MODE=internal
FEISHU_INTERNAL_LINK_PERMISSION=tenant_readable
FEISHU_DEFAULT_MEMBER_IDS=
FEISHU_DEFAULT_MEMBER_PERMISSION=view
```

`.env` 是敏感文件，不要提交到代码仓库，也不要放进公开分享包。

## 飞书应用权限

在飞书开放平台创建企业自建应用，并至少开启：

- `docx:document`：创建/编辑云文档。
- `im:message` 与 `im:message:send_as_bot`：以机器人身份发送消息。
- `contact:user.base:readonly`：通过邮箱/手机号查询用户 open_id。
- 如需电子表格，开启 Sheets/Drive 相关权限。
- 在「应用能力 -> 机器人」启用机器人，并把机器人加入目标群。

权限边界：

- 本 CLI 使用应用身份 `tenant_access_token`，不是任何同事的个人账号。
- 默认只应操作应用创建的文档、应用被显式加为协作者的文档，或应用已有管理权限的文档。
- 不要开启“读取/搜索企业所有云文档”“审计/管理全租户文件”“以用户身份访问全部文档”等全局权限。
- 如果某些文档只能由指定文档管理员编辑和授权分享，不要把应用加为这些文档的协作者，也不要给应用管理权限。
- 需要 AI 处理既有文档时，由 owner 或管理员临时把应用加为协作者，并按任务授予 `view` / `edit` / `full_access`，任务结束后可移除。

## 带表格的长报告：publish_markdown.py

`create-doc` 的 `_textToBlocks` 不解析 Markdown 表格（`| a | b |` 会变成一行竖线文本），`--table-file` 也只支持一张表且只能追加到文档末尾。报告类文档请用 Python 版发布器，它会把每张 Markdown 表格就地转成飞书真实表格：

```powershell
python tools\feishu-cli\publish_markdown.py --file reports\report.md --title "文档标题"
```

可选参数：`--folder-token`、`--private`、`--member-ids ou_a,ou_b`、`--notify-chat oc_xxx`、`--notify-user ou_xxx`。
不传 `--title` 时取 Markdown 里第一个 `#` 标题，并从正文中移除以免重复。

支持：`#`~`######` 标题、`-`/`*` 无序列表、`1.` 有序列表、` ``` ` 代码块、`**粗体**`、`*斜体*`、`` `行内代码` ``、Markdown 表格（含对齐分隔行）、`---` 分隔线（忽略）。凭据同样读 `.env`，默认企业内部链接可阅读。

发布后回读校验（确认没有编码损坏、表格行列数正确）：

```powershell
python tools\feishu-cli\verify_doc.py <document_id> outputs\feishu_verify.txt
```

为什么用 Python 而不是 Node：本机只有 Adobe 附带的 Node v16，缺少全局 `fetch`，`src/api.js` 起不来。装了 Node 18+ 之后原 CLI 的其他命令仍然可用。

Windows 上不要用 `python ... | Write-Host` 之类方式看输出，PowerShell 控制台代码页会把中文显示成乱码——那只是显示问题，写入飞书的内容是 UTF-8，用 `verify_doc.py` 回读确认即可。

## 常用命令

### 群与用户 ID

用你们自己的飞书 `chat_id` / `open_id`，不要把通讯录提交到 Git。

```powershell
.\feishu-cli.cmd notify --chat oc_your_chat_id -m "消息内容"
```

私聊发给指定同事：

```powershell
.\feishu-cli.cmd notify --user ou_your_open_id -m "消息内容"
```

在 目标工作群内 @ 指定人：

```powershell
.\feishu-cli.cmd notify --chat oc_your_chat_id --at ou_your_open_id -m "请看这份报告"
```

在 目标工作群内 @ 所有人：

```powershell
.\feishu-cli.cmd notify --chat oc_your_chat_id --at all -m "日报已更新"
```

发送报告文件到 目标工作群：

```powershell
.\send-file.ps1 -ChatId oc_your_chat_id -File ..\..\reports\report.md
```

发送文件内容到群：

```powershell
.\feishu-cli.cmd send --chat-id oc_xxx --file ..\..\reports\report.md
```

先创建飞书文档，再把链接发到群：

```powershell
.\feishu-cli.cmd send --chat-id oc_xxx --file ..\..\reports\report.md --as-doc
```

默认会设为企业内部拿到链接可访问；只有明确需要外部访问时才加 `--public`。
机密文档使用 `--private --member-ids ou_xxx`，只给显式授权成员访问。

项目 wrapper：

```powershell
.\send-file.ps1 -ChatId oc_xxx -File ..\..\reports\report.md
.\send-file.ps1 -ChatId oc_xxx -File ..\..\reports\report.md -AsDoc -Public
```

列出机器人所在群：

```powershell
.\feishu-cli.cmd list-chats
```

发送普通消息：

```powershell
.\feishu-cli.cmd notify --chat oc_xxx -m "群内消息"
.\feishu-cli.cmd notify --chat oc_xxx --at all -m "@所有人"
.\feishu-cli.cmd notify --chat oc_xxx --at "ou_aaa,ou_bbb" -m "@指定人"
```

创建文档：

```powershell
.\feishu-cli.cmd create-doc --title "项目周报" --content-file report.md
```

创建文档并通知用户：

```powershell
.\feishu-cli.cmd create-doc --title "项目周报" --content-file report.md --notify-user ou_xxx
```

创建文档并插入真实表格：

```powershell
.\feishu-cli.cmd create-doc --title "得分表" --content "以下是得分：" --table-file table.json
```

`table.json` 示例：

```json
[["姓名","得分","评级"],["Alice","92","A"],["Bob","85","B"]]
```

创建电子表格：

```powershell
.\feishu-cli.cmd create-sheet --title "广告日报" --data-file sheet-data.json
```

向现有工作表追加数据（不会从 A1 重写已有内容）：

```powershell
.\feishu-cli.cmd append-sheet --token "<spreadsheet_token>" --sheet "<sheet_id>" --data '[["2026-09-03","someone@example.com","新增 GA 权限"]]'
```

Windows 或包含较多中文时推荐使用 JSON 文件，避免命令行引号转义：

```powershell
.\feishu-cli.cmd append-sheet --token "<spreadsheet_token>" --sheet "<sheet_id>" --data-file append-rows.json
```

`append-rows.json` 必须是非空二维 JSON 数组。命令使用飞书官方
`POST /sheets/v2/spreadsheets/{spreadsheetToken}/values_append` 接口，并显式传入
`insertDataOption=INSERT_ROWS`，只在表格末尾插入新行。单次最多 5000 行、100 列，
每个字符串单元格最多 50000 字符。`--data` 与 `--data-file` 必须二选一。
命令把 `range` 设为完整 `sheet_id`（飞书 Range 语法中的整表非空范围），不会用一个
固定的小范围在长表中间插行。

追加是非幂等操作：CLI 特意关闭了这个请求的网络、5xx 和 429 自动重试，防止响应丢失后
重复追加。如果返回“追加请求结果不确定”，不要直接重跑命令；先用 `read-sheet` 读取表格，
按每条操作记录中的唯一记录 ID 检查该行是否已经存在，再决定是否补写。因此用于审计日志时，
每一行都应带由调用方生成且重试时保持不变的唯一记录 ID。

读取电子表格：

```powershell
.\feishu-cli.cmd read-sheet -t "<spreadsheet_token>" -s "<sheet_id>" -r "A1:Z100"
```

查询用户 open_id：

```powershell
.\feishu-cli.cmd get-user --email someone@example.com
```

## 输出格式

所有命令输出 JSON：

```json
{
  "success": true,
  "data": {
    "messageId": "om_xxx"
  }
}
```

失败时：

```json
{
  "success": false,
  "error": "错误信息"
}
```

## 打包给其他人

把整个 `tools/feishu-cli` 目录复制到项目包里即可。要正常使用，需要满足：

- 目标机器安装 Node.js 18+。
- `tools/feishu-cli/.env` 存在且填好飞书 App ID / App Secret。
- 或者运行命令时传 `--app-id` / `--app-secret`。
- 目标群已添加机器人。

如果不想把飞书 App Secret 发给同事，可以只发 `.env.example`，由管理员本地补 `.env`。

## Windows 注意

- 多行 Markdown 用 `--content-file` 或 `send --file`，不要在命令行里硬塞多行。
- JSON 数据用 `--table-file` / `--data-file`，避免 PowerShell/cmd 引号转义问题。
- CLI 会自动处理 UTF-8 BOM 和 CRLF 换行。
- `feishu-cli.cmd` 只是 Windows 启动器，实际入口是 `src/cli.js`。

## 乱码防护（重要）

之前多次出现飞书文档里中文变成 `??` 的事故，根因是源文件在 Windows 上被以 GBK/ANSI/UTF-16 编码写坏。现在 CLI 有两道防线：

1. **读取自动识别编码**：`--file` / `--content-file` / `--table-file` / `--data-file` 读入时自动识别 UTF-8（含 BOM）、UTF-16 LE/BE（含无 BOM）、GBK，不会再把非 UTF-8 文件读成乱码。
2. **写入前乱码检测**：`send` / `create-doc` / `create-sheet` 在调用飞书 API 之前检查标题、正文、表格数据；发现 U+FFFD、连续 `??` 或中文旁的半角问号，会输出 `success: false` 并退出码 1，**不会创建文档**。

出现拒发时的处理：

- 说明本地源文件本身已经是乱码，先用 UTF-8 重建源文件再重试（Python 用 `encoding="utf-8"`，PowerShell 用 `[System.IO.File]::WriteAllText($path, $text, (New-Object System.Text.UTF8Encoding($false)))`）。
- 如果确认内容本来就该有连续问号（极少见），加 `--force` 跳过检查。

自测：

```powershell
node test-encoding.mjs
```

## 作为模块调用

```javascript
import FeishuCLI from './src/index.js';

const feishu = new FeishuCLI({
  appId: process.env.FEISHU_APP_ID,
  appSecret: process.env.FEISHU_APP_SECRET
});

const doc = await feishu.createDocument({
  title: '数据分析报告',
  content: '报告内容...'
});

await feishu.notifyUser({
  chatId: 'oc_xxx',
  message: `文档已创建: ${doc.data.url}`
});
```

## 安全规则

- 不要提交 `.env`。
- 不要在日志里打印 App Secret。
- 发给外部或同事的 zip 默认不应包含 `.env`，除非明确接受这个风险。
- 默认分享模式是企业内部链接：`FEISHU_DEFAULT_SHARE_MODE=internal`。
- `--public` 会把文档设为外部链接可编辑，飞书页面可能显示“外部”；除非明确需要外部访问，否则不要使用。
- 机密内容使用 `--private`，并通过 `--member-ids` 或 `FEISHU_DEFAULT_MEMBER_IDS` 授权指定成员。
- `--private` 会主动关闭链接共享：`external_access=false`、`link_share_entity=closed`。
- 查看本应用创建的文档，建议配置 `FEISHU_DEFAULT_FOLDER_TOKEN` 到固定文件夹；所有文档和表格都集中创建到该目录。
