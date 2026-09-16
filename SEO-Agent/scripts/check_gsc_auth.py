#!/usr/bin/env python3
"""GSC 鉴权自检：列出 service account 有权限访问的所有站点。
在项目根目录运行: python scripts/check_gsc_auth.py
"""
import json

from google.oauth2 import service_account
from googleapiclient.discovery import build

KEY_FILE = "credentials/gsc-key.json"
SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]

with open(KEY_FILE, encoding="utf-8") as f:
    sa_email = json.load(f)["client_email"]
print(f"Service Account: {sa_email}\n")

credentials = service_account.Credentials.from_service_account_file(
    KEY_FILE, scopes=SCOPES
)
service = build("webmasters", "v3", credentials=credentials)
resp = service.sites().list().execute()

entries = resp.get("siteEntry", [])
if not entries:
    print("没有任何站点权限。请到 Search Console -> 设置 -> 用户和权限，")
    print(f"把 {sa_email} 添加为该资源的用户（完整权限）。")
else:
    print(f"共 {len(entries)} 个站点:")
    for e in sorted(entries, key=lambda x: x["siteUrl"]):
        print(f"  {e['permissionLevel']:20s} {e['siteUrl']}")
