#!/usr/bin/env python3
"""GSC Search Analytics 查询工具（纯 Python，不依赖 Node/MCP）。

用法（项目根目录运行）:
  python scripts/gsc_query.py --site sc-domain:example.com
  python scripts/gsc_query.py --site sc-domain:example.com --dimension page
  python scripts/gsc_query.py --site sc-domain:example.com --days 90 --limit 50
  python scripts/gsc_query.py --site sc-domain:example.com --dimension query,page --contains tools
"""
import argparse
import sys
from datetime import date, timedelta

# Windows 控制台默认 GBK，查询词里有泰文/阿拉伯文等会报编码错
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

KEY_FILE = "credentials/gsc-key.json"
SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", required=True, help="要查询的实际 GSC 资源 ID，例如 sc-domain:example.com")
    ap.add_argument("--dimension", default="query", help="query/page/country/device，逗号分隔可组合")
    ap.add_argument("--days", type=int, default=28)
    ap.add_argument("--start", help="YYYY-MM-DD，指定后忽略 --days")
    ap.add_argument("--end", help="YYYY-MM-DD，默认 3 天前（GSC 数据延迟）")
    ap.add_argument("--limit", type=int, default=25)
    ap.add_argument("--contains", help="按 page 包含字符串过滤")
    args = ap.parse_args()

    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    end = args.end or (date.today() - timedelta(days=3)).isoformat()
    start = args.start or (date.fromisoformat(end) - timedelta(days=args.days)).isoformat()
    dims = [d.strip() for d in args.dimension.split(",")]

    creds = service_account.Credentials.from_service_account_file(KEY_FILE, scopes=SCOPES)
    service = build("searchconsole", "v1", credentials=creds)

    body = {
        "startDate": start,
        "endDate": end,
        "dimensions": dims,
        "rowLimit": args.limit,
    }
    if args.contains:
        body["dimensionFilterGroups"] = [{
            "filters": [{"dimension": "page", "operator": "contains", "expression": args.contains}]
        }]

    resp = service.searchanalytics().query(siteUrl=args.site, body=body).execute()
    rows = resp.get("rows", [])

    print(f"站点: {args.site}   日期: {start} ~ {end}   维度: {','.join(dims)}\n")
    if not rows:
        print("(无数据)")
        return

    header = " | ".join(f"{d:40s}" if d in ("query", "page") else f"{d:10s}" for d in dims)
    print(f"{header} | {'clicks':>7s} | {'impr':>9s} | {'ctr':>6s} | {'pos':>5s}")
    print("-" * (len(header) + 40))
    for r in rows:
        keys = " | ".join(
            f"{k[:40]:40s}" if dims[i] in ("query", "page") else f"{k:10s}"
            for i, k in enumerate(r["keys"])
        )
        print(f"{keys} | {r['clicks']:7.0f} | {r['impressions']:9.0f} | {r['ctr']*100:5.1f}% | {r['position']:5.1f}")

    total_clicks = sum(r["clicks"] for r in rows)
    total_impr = sum(r["impressions"] for r in rows)
    print(f"\n合计(top {len(rows)}): clicks={total_clicks:.0f}, impressions={total_impr:.0f}")


if __name__ == "__main__":
    main()
