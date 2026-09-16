#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

missing=0
for name in GOOGLE_ADS_DEVELOPER_TOKEN GOOGLE_ADS_SERVICE_ACCOUNT_JSON GOOGLE_ADS_LOGIN_CUSTOMER_ID GOOGLE_ADS_DEFAULT_CUSTOMER_ID; do
  if [[ -z "${!name:-}" ]]; then
    echo "Missing env: $name"
    missing=1
  fi
done

if [[ "$missing" -eq 1 ]]; then
  echo "Skipped config generation. Set the env vars above in your cloud dev environment."
  exit 0
fi

printf '%s' "$GOOGLE_ADS_SERVICE_ACCOUNT_JSON" > google-ads-service-account.json
chmod 600 google-ads-service-account.json

cat > google-ads.yaml <<YAML
developer_token: "${GOOGLE_ADS_DEVELOPER_TOKEN}"
json_key_file_path: "google-ads-service-account.json"
login_customer_id: "${GOOGLE_ADS_LOGIN_CUSTOMER_ID}"
use_proto_plus: true
YAML

cat > config.yaml <<YAML
google_ads:
  yaml_path: google-ads.yaml
  api_version: ${GOOGLE_ADS_API_VERSION:-v24}
  default_customer_id: "${GOOGLE_ADS_DEFAULT_CUSTOMER_ID}"

reports:
  dir: reports

feishu:
  cli_path: tools/feishu-cli/send-file.ps1
  default_chat_id: "${FEISHU_CHAT_ID:-}"
  send_command:
    - "pwsh"
    - "-NoProfile"
    - "-ExecutionPolicy"
    - "Bypass"
    - "-File"
    - "{cli_path}"
    - "-ChatId"
    - "{chat_id}"
    - "-File"
    - "{file}"
YAML

mkdir -p reports
echo "Generated google-ads.yaml and config.yaml."
