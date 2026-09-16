# SEO Agent

通用 Google Search Console 命令行工具，支持鉴权检查、搜索表现查询和 MCP 调用。所有命令在本项目根目录运行。

## 安装与配置

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
```

把你自己的 GSC 服务账号 JSON 放到 `credentials/gsc-key.json`，并将该账号添加到需要查询的 Search Console 资源。凭据目录已被 Git 忽略，不能提交真实密钥。

```powershell
.\.venv\Scripts\python scripts\check_gsc_auth.py
.\.venv\Scripts\python scripts\gsc_query.py --site sc-domain:example.com
.\.venv\Scripts\python scripts\gsc_query.py --site sc-domain:example.com --dimension page --limit 50
.\.venv\Scripts\python scripts\gsc_query.py --site sc-domain:example.com --dimension query,page --contains tools
```

`example.com` 是示例，必须替换成自己有权限的实际资源 ID。`--site` 必填，没有默认产品或站点。

## MCP 调用

`scripts/gsc_mcp.py` 调用本机的 `suganthan-gsc-mcp`；没有全局安装时通过 `npx` 启动，需要 Node.js。运行前显式配置自己的凭据路径及资源：

```powershell
$env:GSC_KEY_FILE = 'credentials/gsc-key.json'
$env:GSC_SITE_URL = 'sc-domain:example.com'
.\.venv\Scripts\python scripts\gsc_mcp.py list_tools
```

多站点可改用 `GSC_SITE_URLS`（以逗号分隔资源 ID）。未配置凭据或站点时会在启动 MCP 前报错。

## 保留的工具

| 脚本 | 用途 |
|---|---|
| `scripts/check_gsc_auth.py` | 列出当前服务账号可访问的 GSC 资源 |
| `scripts/gsc_query.py` | 按查询词、页面、国家或设备查询搜索表现 |
| `scripts/gsc_mcp.py` | 从命令行调用 GSC MCP 工具 |
| `scripts/gsc_discover_api.py` | 查看 Google API discovery 中的方法 |
| `scripts/check_sa_keys.py` | 检查当前服务账号的密钥元数据，需要对应 IAM 权限 |

广告投放与人员权限管理分别使用工作区的专用项目，凭据不能混用。
