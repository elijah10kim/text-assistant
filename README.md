# Personal AI Assistant

A self-hosted, privacy-first personal AI assistant accessible via iMessage (with Telegram auto-failover). Built on [OpenClaw](https://github.com/openclaw/openclaw).

## Current deployment phase

Everything runs on one machine — the MacBook used for development — for now. BlueBubbles and the OpenClaw Gateway run together on it. Once the build is stable, both migrate to a dedicated always-on Mac mini so the assistant runs 24/7 independent of the MacBook.

## What it does

- **Chat via iMessage** — text your assistant like a friend, get intelligent responses powered by Claude
- **Web search** — ask anything, get answers with current information
- **Memory** — remembers your preferences, habits, and past conversations across sessions
- **Proactive notifications** — morning briefings, bill reminders, email digests, custom alerts on a schedule
- **Calendar + email** — reads/writes Google Calendar and Gmail, drafts replies, schedules meetings
- **Image + voice understanding** — send photos or voice notes, get text responses
- **Smart home control** — manage Alexa/Google Home devices via text (through Home Assistant)
- **Auto-failover** — if iMessage goes down, switches to Telegram automatically

## Architecture

```
You (iMessage / Telegram)
        │
   BlueBubbles / Telegram Bot
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

- All conversation data, memory, and integrations stored locally (SQLite + Chroma vector DB)
- Gateway binds to localhost — no ports exposed to the internet
- API keys encrypted at rest via macOS Keychain
- Claude API used for all reasoning (Anthropic does not train on API inputs, though data does transit their servers per request)

## Setup

See [docs/SETUP.md](docs/SETUP.md) for step-by-step installation instructions.

## Configuration

Copy `.env.example` to `.env` and fill in your API keys. See the example file for all required variables.

## Build phases

| Phase | Status | What |
|---|---|---|
| 1 | 🔨 | OpenClaw + Telegram + Claude API |
| 2 | ⬜ | Memory (SQLite + Chroma + auto-compaction) |
| 3 | ⬜ | BlueBubbles + iMessage |
| 4 | ⬜ | Google Calendar + Gmail |
| 5 | ⬜ | Proactivity engine (cron + briefings + reminders) |
| 6 | ⬜ | Image understanding + voice transcription (Whisper) |
| 7 | ⬜ | Home Assistant + smart home |
| 8 | ⬜ | Always-on hardening (Mac mini migration) |

## License

MIT
