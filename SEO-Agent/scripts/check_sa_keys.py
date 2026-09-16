#!/usr/bin/env python3
"""列出 GSC service account 的所有用户密钥（用于轮换排查）。
在项目根目录运行: python scripts/check_sa_keys.py
"""
import json
import sys

from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

KEY = "credentials/gsc-key.json"
d = json.load(open(KEY, encoding="utf-8"))
email = d["client_email"]
local_kid = d["private_key_id"]
print(f"Service Account: {email}")
print(f"本地这份 key 的 ID: {local_kid}\n")

creds = service_account.Credentials.from_service_account_file(
    KEY, scopes=["https://www.googleapis.com/auth/cloud-platform"]
)
s = AuthorizedSession(creds)
r = s.get(
    f"https://iam.googleapis.com/v1/projects/-/serviceAccounts/{email}/keys",
    params={"keyTypes": "USER_MANAGED"},
)
print(f"HTTP {r.status_code}")
if r.status_code == 200:
    keys = r.json().get("keys", [])
    print(f"共 {len(keys)} 把用户管理的密钥:")
    for k in keys:
        kid = k["name"].split("/")[-1]
        mark = "  <== 当前在用的这份" if kid == local_kid else ""
        print(f"  {kid}")
        print(f"    创建: {k.get('validAfterTime', '?')}  过期: {k.get('validBeforeTime', '?')}{mark}")
else:
    print(r.text[:500])
