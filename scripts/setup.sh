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

# "0m" (fully disabled) turned out to also silently break one-off reminders --
# they route through the same heartbeat mechanism to deliver. "24h" keeps cost
# low (default is 30m) while keeping reminders working.
npx openclaw config set agents.defaults.heartbeat.every "24h"

# "coding" is OpenClaw's default profile (shell/file/runtime access) — unnecessary
# attack surface for a chat-only assistant. "messaging" + web keeps search working
# without exec/runtime tools. MCP integrations (Gmail, Calendar, etc. in later
# phases) aren't affected by this — profiles only gate built-in tools.
#
# read/write/edit and memory_get/memory_search (group:memory) are also "coding"-only
# by default, which silently breaks the built-in MEMORY.md + daily-notes system on
# "messaging" — the model reports "saved" but has no tool that can actually write the
# file. Re-added narrowly (no exec, no apply_patch) and scoped to the workspace dir
# only via tools.fs.workspaceOnly, so this doesn't reopen general filesystem access.
# "cron" (also coding-only by default) lets the assistant schedule its own recurring
# jobs from a chat request ("track this and tell me if it changes"), not just run
# crons an operator set up via CLI.
npx openclaw config set tools.profile messaging
npx openclaw config set tools.alsoAllow '["group:web", "group:memory", "read", "write", "edit", "cron"]' --strict-json
npx openclaw config set tools.fs.workspaceOnly true --strict-json

# Default verbose mode leaks tool-call activity (e.g. "web_fetch: ...") as its own
# outbound message on chat channels — not something a texting-style assistant should show.
npx openclaw config set agents.defaults.verboseDefault off

# Telegram's own streaming/progress mode is a separate lever from the agent-level
# verbose setting above, and controls the actual channel delivery pipeline (docs
# claim "block" suppresses tool narration — tested, false, it still leaked raw
# web_fetch output). "progress" mode is the one that correctly sends an early ack
# message and supports suppressing tool narration via its own toolProgress flag.
# The ack itself is an OpenClaw-generated placeholder label, not the model calling
# a message tool — override its default whimsical text (e.g. "tidepooling...")
# with something that actually matches what SOUL.md asks for.
npx openclaw config set channels.telegram.streaming.mode progress
npx openclaw config set channels.telegram.streaming.progress.toolProgress false --strict-json
npx openclaw config set channels.telegram.streaming.progress.labels '["on it", "checking now", "got it", "one sec", "looking into it"]' --strict-json

# Memory search (semantic/vector recall over MEMORY.md and daily notes) defaults to
# ON with OpenAI as the embedding provider — a second cloud provider this project
# avoids (see docs/DESIGN.md "Resolved decisions"). The plain-text MEMORY.md + daily
# notes system (memory/YYYY-MM-DD.md) still works fully without this; it's driven by
# agents.defaults.startupContext, which is on by default and needs no config here.
npx openclaw config set agents.defaults.memorySearch.enabled false --strict-json

# In-conversation "write it down proactively" instructions aren't reliable enough
# alone (tested — the model skipped the memory write most of the time). This once-daily
# job reviews the day's Telegram conversation and consolidates anything durable into
# MEMORY.md / memory/YYYY-MM-DD.md. --no-deliver keeps it silent (no Telegram message).
#
# sessions_history defaults to "tree" visibility (only the job's own session), which
# blocks it from reading the Telegram session at all. "agent" widens it to any session
# under our single "main" agent — still scoped to just this agent, not cross-agent.
npx openclaw config set tools.sessions.visibility agent
#
# Note: cron add/edit need operator.write scope. A fresh CLI device is usually only
# pre-approved for operator.read, so this may need a one-time manual approval: if it
# errors with "scope upgrade pending approval", run
# `openclaw devices approve --latest --token "$GATEWAY_TOKEN"` and re-run this block.
GATEWAY_TOKEN=$(python3 -c "import json; print(json.load(open('$HOME/.openclaw/openclaw.json')).get('gateway',{}).get('auth',{}).get('token',''))")
npx openclaw cron add \
  --name "Daily memory consolidation" \
  --description "Reviews the day's Telegram conversation and distills anything durable into MEMORY.md / today's daily note" \
  --cron "7 0 * * *" \
  --tz "America/Toronto" \
  --agent main \
  --session isolated \
  --tools "read write edit sessions_history sessions_list" \
  --timeout-seconds 900 \
  --expect-final \
  --no-deliver \
  --message "Daily memory consolidation. Use sessions_history to review today's conversation in session key agent:main:telegram:direct:$TELEGRAM_ALLOWED_USER_ID (the direct chat with Elijah). Read MEMORY.md first so you don't duplicate what's already saved. Identify anything durable worth keeping long-term: decisions made, preferences stated, facts about Elijah, things researched or compared, ongoing goals or interests. Write concise, factual entries, no narration: lasting facts/preferences go in MEMORY.md, a log of what happened goes in memory/YYYY-MM-DD.md for today's date (create memory/ if it doesn't exist). If nothing noteworthy happened today, do nothing -- don't write empty or filler entries. This is a silent background task, do not send a message to any chat." \
  --token "$GATEWAY_TOKEN"

# Optional: flight-search MCP server (Ignav), our own Python MCP server in mcp/flights/.
# Only wired up if IGNAV_API_KEY is set in .env. OpenClaw sanitizes the environment it
# passes to MCP child processes, so the key does NOT inherit from the gateway's .env —
# it must be injected explicitly into the server's config (lands in openclaw.json, 600,
# same as the Telegram token).
if [ -n "${IGNAV_API_KEY:-}" ] && [[ "$IGNAV_API_KEY" != *"your-actual"* ]]; then
  FLIGHTS_DIR="$(pwd)/mcp/flights"
  python3 -m venv "$FLIGHTS_DIR/.venv"
  "$FLIGHTS_DIR/.venv/bin/pip" install --quiet -r "$FLIGHTS_DIR/requirements.txt"
  FLIGHTS_JSON=$(FLIGHTS_DIR="$FLIGHTS_DIR" python3 -c "
import json, os
d = os.environ['FLIGHTS_DIR']
print(json.dumps({
    'command': os.path.join(d, '.venv/bin/python'),
    'args': [os.path.join(d, 'server.py')],
    'env': {'IGNAV_API_KEY': os.environ['IGNAV_API_KEY']},
}))
")
  npx openclaw mcp set flights "$FLIGHTS_JSON"
  unset FLIGHTS_JSON
fi

# Optional: Google Workspace MCP server (Gmail read+draft, Calendar view+add
# events, Tasks) in mcp/google/. Only the venv + registration are scriptable —
# the OAuth grant itself needs a human in a browser (Google requires this, it
# cannot be automated) and is NOT run here. If mcp/google/client_secret.json
# exists (downloaded manually from Google Cloud Console — see mcp/google/README.md)
# but token.json doesn't yet, this sets up the venv and tells you to run the
# one-time `python3 authorize.py` step yourself, then re-run this script (or
# just the mcp set command it prints) to register it.
GOOGLE_DIR="$(pwd)/mcp/google"
if [ -f "$GOOGLE_DIR/client_secret.json" ]; then
  python3 -m venv "$GOOGLE_DIR/.venv"
  "$GOOGLE_DIR/.venv/bin/pip" install --quiet -r "$GOOGLE_DIR/requirements.txt"
  if [ -f "$GOOGLE_DIR/token.json" ]; then
    npx openclaw mcp set google-workspace "$(python3 -c "
import json
print(json.dumps({
    'command': '$GOOGLE_DIR/.venv/bin/python',
    'args': ['$GOOGLE_DIR/server.py'],
}))
")"
  else
    echo
    echo "Google Workspace: venv ready, but not authorized yet. Run this once, then re-run setup:"
    echo "  cd $GOOGLE_DIR && ./.venv/bin/python authorize.py"
  fi
fi

chmod 600 .env
find "$HOME/.openclaw" -type f -exec chmod 600 {} \; 2>/dev/null
find "$HOME/.openclaw" -type d -exec chmod 700 {} \; 2>/dev/null

echo
echo "Setup complete. Start the gateway with: npm start"
