#!/usr/bin/env bash
# Bootstrap ~/.agent-reach/config.yaml from env vars or interactive prompts.
# Usage:
#   export FEISHU_APP_ID=cli_xxx FEISHU_APP_SECRET=xxx FEISHU_CHAT_ID=oc_xxx
#   export XUEQIU_COOKIE='xq_a_token=...; ...'
#   bash scripts/setup-agent-reach-config.sh
set -euo pipefail

CONFIG_DIR="${HOME}/.agent-reach"
CONFIG_FILE="${CONFIG_DIR}/config.yaml"
ENV_FILE="${CONFIG_DIR}/config.env"

mkdir -p "$CONFIG_DIR"
chmod 700 "$CONFIG_DIR"

python3 - <<'PY'
import os
from pathlib import Path

try:
    import yaml
except ImportError:
    raise SystemExit("pip install pyyaml")

config_path = Path.home() / ".agent-reach" / "config.yaml"
data: dict = {}
if config_path.exists():
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}

# Map env → config keys (Config.get also reads env at runtime)
env_map = {
    "FEISHU_APP_ID": "feishu_app_id",
    "FEISHU_APP_SECRET": "feishu_app_secret",
    "FEISHU_CHAT_ID": "feishu_chat_id",
    "FEISHU_WEBHOOK_URL": "feishu_webhook_url",
    "FEISHU_WEBHOOK_SECRET": "feishu_webhook_secret",
    "XUEQIU_COOKIE": "xueqiu_cookie",
    "TWITTER_AUTH_TOKEN": "twitter_auth_token",
    "TWITTER_CT0": "twitter_ct0",
    "EXA_API_KEY": "exa_api_key",
    "OPENAI_API_KEY": "openai_api_key",
    "DEEPSEEK_API_KEY": "deepseek_api_key",
    "DEEPSEEK_BASE_URL": "deepseek_base_url",
    "GROQ_API_KEY": "groq_api_key",
    "GITHUB_TOKEN": "github_token",
    "PROXY": "proxy",
}

updated = []
for env_key, cfg_key in env_map.items():
    val = (os.environ.get(env_key) or "").strip()
    if val and not data.get(cfg_key):
        data[cfg_key] = val
        updated.append(cfg_key)

# Default chat_id for 每天股票量化交易 group (used in prior runs on this VPS)
if not data.get("feishu_chat_id"):
    data["feishu_chat_id"] = "oc_856923efb46d3c48405ae54ede7b784b"
    updated.append("feishu_chat_id (default)")

config_path.parent.mkdir(parents=True, exist_ok=True)
config_path.write_text(
    yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False),
    encoding="utf-8",
)
os.chmod(config_path, 0o600)

print(f"Wrote {config_path}")
if updated:
    print("Updated keys:", ", ".join(updated))
else:
    print("No new keys from environment; existing config preserved.")

missing = []
if not (data.get("feishu_webhook_url") or (
    data.get("feishu_app_id") and data.get("feishu_app_secret") and data.get("feishu_chat_id")
)):
    missing.append("feishu (webhook OR app_id+app_secret+chat_id)")
if not data.get("xueqiu_cookie"):
    missing.append("xueqiu_cookie (optional but recommended for quotes)")
if missing:
    print("Still missing:", "; ".join(missing))
PY

# Write env file template for cron (do not overwrite if exists)
if [ ! -f "$ENV_FILE" ]; then
  cat > "$ENV_FILE" <<'EOF'
# Source before cron jobs: export $(grep -v '^#' ~/.agent-reach/config.env | xargs)
# FEISHU_APP_ID=cli_xxxxxxxx
# FEISHU_APP_SECRET=xxxxxxxx
# FEISHU_CHAT_ID=oc_xxxxxxxx
# XUEQIU_COOKIE=xq_a_token=...; u=...; ...
EOF
  chmod 600 "$ENV_FILE"
  echo "Created template: $ENV_FILE"
fi

echo ""
echo "Next:"
echo "  1) Edit secrets: nano ~/.agent-reach/config.env"
echo "  2) Apply: bash scripts/setup-agent-reach-config.sh"
echo "  3) Test:  agent-reach notify feishu --test"
echo "  4) Check: agent-reach doctor"
