#!/usr/bin/env bash
# Reproduces the manual Phase 1 setup: auth, Telegram channel, allowlist, owner, model.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo "No .env found — copying .env.example to .env."
  cp .env.example .env
  echo "Fill in ANTHROPIC_API_KEY, TELEGRAM_BOT_TOKEN, and TELEGRAM_ALLOWED_USER_ID in .env, then re-run: npm run setup"
  exit 1
fi

set -a
source .env
set +a

for var in ANTHROPIC_API_KEY TELEGRAM_BOT_TOKEN TELEGRAM_ALLOWED_USER_ID; do
  val="${!var:-}"
  if [ -z "$val" ] || [[ "$val" == *"your-actual"* ]]; then
    echo "Error: $var is not set in .env" >&2
    exit 1
  fi
done

npx openclaw onboard --non-interactive --accept-risk --skip-health \
  --auth-choice apiKey --anthropic-api-key "$ANTHROPIC_API_KEY" \
  --gateway-bind loopback --no-install-daemon --skip-channels

npx openclaw channels add --channel telegram --token "$TELEGRAM_BOT_TOKEN"

npx openclaw config set channels.telegram.dmPolicy allowlist
npx openclaw config set channels.telegram.allowFrom "[\"$TELEGRAM_ALLOWED_USER_ID\"]" --strict-json
npx openclaw config set commands.ownerAllowFrom "[\"telegram:$TELEGRAM_ALLOWED_USER_ID\"]" --strict-json
npx openclaw config set agents.defaults.model.primary "anthropic/claude-sonnet-4-6"

# Disabled per OpenClaw's own guidance: heartbeats default to every 30 minutes
# and burn real API credits with no proactivity routines configured yet (Phase 5).
npx openclaw config set agents.defaults.heartbeat.every "0m"

# "coding" is OpenClaw's default profile (shell/file/runtime access) — unnecessary
# attack surface for a chat-only assistant. "messaging" + web keeps search working
# without exec/filesystem tools. MCP integrations (Gmail, Calendar, etc. in later
# phases) aren't affected by this — profiles only gate built-in tools.
npx openclaw config set tools.profile messaging
npx openclaw config set tools.alsoAllow '["group:web"]' --strict-json

chmod 600 .env
find "$HOME/.openclaw" -type f -exec chmod 600 {} \; 2>/dev/null
find "$HOME/.openclaw" -type d -exec chmod 700 {} \; 2>/dev/null

echo
echo "Setup complete. Start the gateway with: npm start"
