# Setup guide — Phase 1

Get a working AI chatbot you can text via Telegram, powered by Claude with web search.

## Prerequisites

- macOS (Apple Silicon) with Homebrew installed
- A Telegram account on your phone
- A Claude API key from Anthropic

## Step 1 — Install Node.js

OpenClaw requires Node.js 22 or 24.

```bash
brew install node@24
node --version  # should print v24.x.x (v22.x.x also works)
```

## Step 2 — Get a Claude API key

1. Go to https://platform.claude.com
2. Create an account (or sign in)
3. Go to API Keys → Create Key
4. Copy the key — it starts with `sk-ant-`
5. Under Plans & Billing, add credits — API calls fail with a billing error until the account has a positive balance (the free trial credit isn't always applied automatically)

Save this key — you'll need it in Step 4.

## Step 3 — Create a Telegram bot

1. Open Telegram on your phone
2. Search for `@BotFather` and start a chat
3. Send `/newbot`
4. Follow the prompts — give it a name (e.g., "My Assistant") and a username (e.g., `my_assistant_12345_bot`)
5. BotFather gives you a bot token — copy it
6. Send `/mybots` → select your bot → Bot Settings → Group Privacy → Turn OFF (so it can read messages)

To find your Telegram user ID (needed for the allowlist):
1. Search for `@userinfobot` on Telegram
2. Start a chat — it replies with your user ID (a number like `123456789`)

## Step 4 — Clone the repo and install dependencies

```bash
git clone <this-repo-url> text-assistant
cd text-assistant
npm install
```

This installs the exact pinned OpenClaw version from `package.json` locally into `node_modules/` — no global install needed, and it stays reproducible across machines (e.g. migrating to a Mac mini later).

## Step 5 — Configure the environment

```bash
cp .env.example .env
nano .env   # or open with any editor
```

Fill in the three values from Steps 2 and 3:

```
ANTHROPIC_API_KEY=sk-ant-your-actual-key
TELEGRAM_BOT_TOKEN=your-actual-bot-token
TELEGRAM_ALLOWED_USER_ID=your-actual-user-id
```

## Step 6 — Run the automated setup

```bash
npm run setup
```

This runs OpenClaw's onboarding non-interactively using the values from `.env`, and:
- Configures Claude API auth
- Adds the Telegram channel with your bot token
- Locks the DM allowlist to your Telegram user ID only
- Sets you as the command owner (required for privileged commands like `/config`)
- Sets the model to `claude-sonnet-4-6` (best balance of quality and cost)

It's safe to re-run any time — it overwrites config idempotently rather than duplicating it.

## Step 7 — Start the Gateway

```bash
npm start
```

Leave this running in a terminal (or see the Troubleshooting section for running it detached). You should see `ready` and `[telegram] starting provider` in the output.

## Step 8 — Test it

1. Open Telegram on your phone
2. Find your bot and send it a message: "Hello, what can you do?"
3. It should respond via Claude

Try a web search: "What's the weather in Toronto right now?"

## Step 9 — Verify the security setup

Run the built-in security checker:

```bash
npm run doctor
```

This surfaces any risky configurations (e.g., DM policies that are too open, missing command owner). Fix anything it flags.

## What you have now

- A working AI assistant you can text via Telegram
- Powered by Claude Sonnet 4.6 with web search capability
- Running locally on your MacBook, fully reproducible via `npm install && npm run setup`
- No data going anywhere except Anthropic's API (which doesn't train on API inputs)

## What's next

Phase 2: Add the memory layer (SQLite + Chroma + auto-compaction). See `docs/DESIGN.md` for the full build order.

## Troubleshooting

**Running the Gateway in the background**
`npm start` runs in the foreground. To detach it from your terminal session:
```bash
nohup npm start > /tmp/openclaw-gateway.log 2>&1 &
disown
```
Check it's up with `npm run status` or `tail -f /tmp/openclaw-gateway.log`.

**"command not found: openclaw"**
Use the npm scripts (`npm start`, `npm run setup`, `npm run doctor`) — they resolve the locally pinned binary automatically. If you want the bare `openclaw` command available directly, `npm install -g openclaw` and add npm's global bin to your PATH:
```bash
export PATH="$(npm config get prefix)/bin:$PATH"
```
Add this to your `~/.zshrc` to make it permanent.

**Bot doesn't respond on Telegram**
- Check the bot token is correct in `.env`, then re-run `npm run setup`
- Make sure the Gateway is running (`npm run status`)
- Check your Telegram user ID matches `TELEGRAM_ALLOWED_USER_ID` in `.env`

**"Your credit balance is too low" errors**
- Go to https://platform.claude.com → Plans & Billing → add credits
- This is a billing issue, not a config issue — no restart needed once credits are added

**"API key invalid" errors**
- Verify your Claude API key at https://platform.claude.com/settings/keys
- Make sure there are no extra spaces or newlines in the `.env` value
