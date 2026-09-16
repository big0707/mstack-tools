PRESETS = ("overview", "errors", "not-found", "slow", "top-paths", "top-ips", "bots")


def expressions(c):
    f = c["fields"]
    status = f'try_cast("{f["status"]}" AS bigint)'
    raw_latency = f'try_cast("{f["latency"]}" AS double)'
    latency = f"CASE WHEN {raw_latency} >= 0 THEN {raw_latency} END"
    if c["latency_unit"] == "milliseconds":
        latency = f"({latency}) / 1000.0"
    path = f'split_part(cast("{f["path"]}" AS varchar), \'?\', 1)'
    return status, latency, path


def build_query(c, preset="overview", limit=20):
    s, latency, path = expressions(c)
    if preset == "overview":
        return f'''* | SELECT count(*) AS total,
count(CASE WHEN {s} BETWEEN 100 AND 599 THEN 1 END) AS valid_status,
count(CASE WHEN {s} BETWEEN 500 AND 599 THEN 1 END) AS server_errors,
count(CASE WHEN {s} = 404 THEN 1 END) AS not_found,
count(CASE WHEN {s} = 429 THEN 1 END) AS rate_limited,
count({latency}) AS latency_samples,
approx_percentile({latency}, 0.95) AS p95_seconds,
count(CASE WHEN {latency} > {c['thresholds']['slow_seconds']} THEN 1 END) AS slow_requests
FROM log LIMIT 1'''
    where = {"errors": f"{s} BETWEEN 500 AND 599", "not-found": f"{s} = 404",
             "slow": f"{latency} > {c['thresholds']['slow_seconds']}"}.get(preset)
    if where:
        return f'''* | SELECT {path} AS path, {s} AS status, count(*) AS requests,
approx_percentile({latency}, 0.95) AS p95_seconds FROM log
WHERE {where} GROUP BY {path}, {s} ORDER BY requests DESC LIMIT {limit}'''
    if preset == "top-paths":
        return f"* | SELECT {path} AS path, count(*) AS requests FROM log GROUP BY {path} ORDER BY requests DESC LIMIT {limit}"
    if preset == "top-ips":
        ip = c["fields"]["ip"]
        return f'* | SELECT "{ip}" AS ip, count(*) AS requests FROM log GROUP BY "{ip}" ORDER BY requests DESC LIMIT {limit}'
    if preset == "bots":
        ua = c["fields"]["user_agent"]
        # A UA claim is not verified crawler identity.
        family = f'''CASE
WHEN lower("{ua}") LIKE '%googlebot%' THEN 'Googlebot (UA claim)'
WHEN lower("{ua}") LIKE '%bingbot%' THEN 'Bingbot (UA claim)'
WHEN lower("{ua}") LIKE '%gptbot%' THEN 'GPTBot (UA claim)'
WHEN lower("{ua}") LIKE '%claudebot%' THEN 'ClaudeBot (UA claim)'
WHEN lower("{ua}") LIKE '%bot%' OR lower("{ua}") LIKE '%spider%' THEN 'Other bot (UA claim)'
ELSE 'Other/unknown' END'''
        return f"* | SELECT {family} AS agent_family, count(*) AS requests FROM log GROUP BY {family} ORDER BY requests DESC LIMIT {limit}"
    raise ValueError("Unknown query preset")
