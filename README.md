# Personal AI Assistant

A self-hosted, privacy-first personal AI assistant accessible via iMessage (with Telegram as a secondary channel). Built on [OpenClaw](https://github.com/openclaw/openclaw).

## Current deployment phase

Everything runs on one machine — the MacBook used for development — for now. The OpenClaw Gateway and its iMessage bridge (`imsg`) run together on it. Once the build is stable, both migrate to a dedicated always-on Mac mini so the assistant runs 24/7 independent of the MacBook.

## What it does

- **Chat via iMessage** — text your assistant like a friend, get intelligent responses powered by Claude
- **Web search** — ask anything, get answers with current information
- **Memory** — remembers your preferences, habits, and past conversations across sessions
- **Proactive notifications** — daily morning briefing (weather, calendar, tasks, email), plus one-off "remind me" requests
- **Calendar + email + tasks** — reads/searches Gmail and drafts replies (no send capability — see `mcp/google/README.md`), views/creates Calendar events, manages Google Tasks and due dates
- **Image + voice understanding** — send photos or voice notes, get text responses
- **Smart home control** — manage Alexa/Google Home devices via text (through Home Assistant)
- **Flight search + price tracking** — find fares and get pinged when a watched route drops (custom Ignav MCP server)
- **Secondary channel** — Telegram runs on the same Gateway as a backup surface for channel-level iMessage failures

## Architecture

```
You (iMessage / Telegram)
        │
   imsg (child process) / Telegram Bot
        │
   OpenClaw Gateway (localhost only)
        │
    Claude API
        │
   ┌────┼────────┬──────────┐
Google    Gmail    Home       Cron
Calendar          Assistant   Scheduler
```

## Privacy model

- All conversation data, memory, and integrations stored locally (OpenClaw's built-in `MEMORY.md` + daily notes, SQLite-backed)
- Gateway binds to localhost — no ports exposed to the internet
- API keys stored in `.env` and OpenClaw's local config, restricted to owner-only file permissions (not Keychain-encrypted)
- Claude API used for all reasoning (Anthropic does not train on API inputs, though data does transit their servers per request)

## Setup

See [docs/SETUP.md](docs/SETUP.md) for step-by-step installation instructions.

## Configuration

Copy `.env.example` to `.env` and fill in your API keys. See the example file for all required variables.

## Build phases

| Phase | Status | What |
|---|---|---|
| 1 | 🔨 | OpenClaw + Telegram + Claude API |
| 2 | ⬜ | Memory (OpenClaw's built-in MEMORY.md + daily notes) |
| 3 | ⬜ | iMessage via `imsg` (Basic tier, dedicated Apple ID) |
| 4 | 🔨 | Gmail + Calendar + Tasks (custom MCP server) |
| 5 | 🔨 | Proactivity engine (morning briefing + reminders) |
| 6 | ⬜ | Image understanding + voice transcription (Whisper) |
| 7 | ⬜ | Home Assistant + smart home |
| 8 | ⬜ | Always-on hardening (Mac mini migration) |
| Optional | 🔨 | Flight search + price tracking (Ignav MCP server) |
