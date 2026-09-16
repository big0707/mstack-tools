# GA4 报告与 Audience Agent

本文件夹是一个可直接在 Codex 或 Cursor 中使用的 GA4 数据报告项目。

- 用户提出 Google Analytics、流量、渠道、页面、事件、转化、电商、收入、用户或实时数据需求时，必须调用 `ga4` MCP；不得估算或编造账户数据。
- 根据用户提到的站点选择对应 `property`；站点或 Property 不确定时先调用 `list_properties`，不得默认混用不同站点的数据。
- 字段名不确定时先调用 `get_metadata`，不要反复猜测不兼容的 dimension/metric。
- 历史数据使用 `run_report`；只有明确询问“现在、实时、最近几分钟”时使用 `run_realtime_report`。
- 用户未指定日期时，默认查询截至昨天的最近 30 个完整自然日，并说明这一假设。用户询问表现变化但未指定基准时，使用紧邻的等长上一周期比较。
- 必须完成查询后再写结论。若 MCP 或 GA4 凭据未配置，停止并根据 `README.md` 给出准确配置步骤，不能用虚构数字替代。
- 默认直接在对话中输出 Markdown 报告；用户明确要求文件时才创建报告文件。
- 报告应按需求包含：结论摘要、精确查询/对比周期、KPI 表及变化率、趋势或排名明细、基于证据的洞察、数据质量说明。
- 明确区分 GA4 返回事实与分析解释。相关性不代表因果；返回行少于 `row_count` 时必须说明结果被截断。
- 相关时注明 metrics、dimensions、filters、Property 时区和货币，并提醒 `(not set)`、阈值、归因与当天不完整数据问题。
- 报告、元数据、Audience 查询和 Google Ads 链接查询工具只读。不得读取、输出或要求用户粘贴 `.env`、服务账号 JSON、token 或私钥内容。
- 只有用户明确要求创建、修改或归档 GA4 Audience 时，才可使用对应写入工具；不得顺带修改其他 GA4 或 Google Ads 配置。
- `create_audience`、`update_audience`、`archive_audience` 必须采用两步确认：先以 `confirm=false` 获取预览，向用户展示准确 Property、Audience 名称、条件、成员期限和影响；获得明确确认后，才可用完全相同的参数和 `confirm=true` 执行。
- Audience 条件和成员资格期限创建后不可修改。条件不明确时必须询问，不能猜测。归档前必须用 `get_audience` 核实完整资源名。
- 若用户要求“广告可用”的 Audience，创建前先用 `list_google_ads_links` 验证链接与个性化广告设置；创建后根据返回的 `ads_personalization_enabled` 如实说明，不能保证立即可用于投放。
- 除非用户指定其他语言，否则用中文回答。
