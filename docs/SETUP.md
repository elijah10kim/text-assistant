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
node --version  # should print v24.x.x
```

## Step 2 — Get a Claude API key

1. Go to https://platform.claude.com
2. Create an account (or sign in)
3. Go to API Keys → Create Key
4. Copy the key — it starts with `sk-ant-`
5. You get $5 in free credits to start (no credit card needed)

Save this key — you'll need it in Step 5.

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

## Step 4 — Install OpenClaw

```bash
# Install OpenClaw globally
npm install -g openclaw

# Verify installation
openclaw --version
```

## Step 5 — Configure the project

```bash
# Navigate to your cloned repo
cd personal-assistant

# Copy the environment template
cp .env.example .env

# Edit .env with your values
nano .env   # or open with any editor
```

Fill in these three values (leave the rest for later phases):

```
ANTHROPIC_API_KEY=sk-ant-your-actual-key
TELEGRAM_BOT_TOKEN=your-actual-bot-token
TELEGRAM_ALLOWED_USER_ID=your-actual-user-id
```

## Step 6 — Run the guided setup

OpenClaw has a built-in onboarding wizard:

```bash
openclaw onboard
```

This walks you through:
- Setting up the Gateway
- Configuring your workspace
- Connecting the Telegram channel
- Setting your AI provider (select Anthropic / Claude)

When asked for the model, use `claude-sonnet-4-6` (best balance of quality and cost).

## Step 7 — Test it

1. Open Telegram on your phone
2. Find your bot and send it a message: "Hello, what can you do?"
3. It should respond via Claude

Try a web search: "What's the weather in Toronto right now?"

## Step 8 — Verify the security setup

Run the built-in security checker:

```bash
openclaw doctor
```

This surfaces any risky configurations (e.g., DM policies that are too open). Fix anything it flags.

## What you have now

- A working AI assistant you can text via Telegram
- Powered by Claude Sonnet 4.6 with web search capability
- Running locally on your MacBook
- No data going anywhere except Anthropic's API (which doesn't train on API inputs)

## What's next

Phase 2: Install Ollama and set up model routing so sensitive queries stay fully local. See [PHASE-2.md](PHASE-2.md) (coming soon).

## Troubleshooting

**"command not found: openclaw"**
Make sure npm global bin is in your PATH:
```bash
export PATH="$HOME/.npm-global/bin:$PATH"
```
Add this to your `~/.zshrc` to make it permanent.

**Bot doesn't respond on Telegram**
- Check the bot token is correct in `.env`
- Make sure the Gateway is running (`openclaw` in terminal — it should show "Gateway started")
- Check your Telegram user ID matches `TELEGRAM_ALLOWED_USER_ID`

**"API key invalid" errors**
- Verify your Claude API key at https://platform.claude.com/settings/keys
- Make sure there are no extra spaces or newlines in the `.env` value
