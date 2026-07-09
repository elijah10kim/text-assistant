# Personal AI assistant — design document

## Overview

A self-hosted, privacy-first personal AI assistant accessible primarily via iMessage (with Telegram as a backup channel). The assistant can hold conversations, search the web, understand images and voice notes, remember context across sessions, integrate with external apps, take actions on your behalf, and proactively notify you on a schedule. It runs entirely on your own hardware behind a private network. Single user only — responds exclusively to one Apple ID.

**Stack:** Claude API (via OpenClaw) for all reasoning. No local/self-hosted LLM (Ollama removed from scope — see "Resolved decisions" below).

**Current deployment phase:** Everything (OpenClaw Gateway + BlueBubbles) runs on one machine — your MacBook — for development and testing. This is temporary. Once the build is stable, BlueBubbles + Gateway migrate to a dedicated always-on Mac mini so the assistant runs 24/7 without depending on the MacBook staying awake. See "Always-on considerations" and "Version control and deployment" below for that migration path.

---

## Core principles

- **Privacy-conscious, cloud-reasoning.** All conversation data, memory, and integrations run on your own hardware. The Claude API handles all reasoning — Anthropic does not train on API inputs, but data does transit to and get processed on Anthropic's servers for each request.
- **Confirm before acting.** High-stakes actions (sending emails, booking reservations) require your explicit confirmation. Low-stakes actions (setting a reminder, looking something up) proceed automatically.
- **One machine for now, dedicated hardware later.** Development and initial testing run entirely on your MacBook (BlueBubbles + Gateway together). Once stable, migrate BlueBubbles + Gateway to a dedicated Mac mini for true 24/7 uptime — the MacBook then becomes just a dev machine again.

---

## Architecture

### Layer 1 — messaging channel

| Component | Role |
|---|---|
| BlueBubbles (on macOS — currently your MacBook, later a dedicated Mac mini) | Bridges iMessage to the Gateway via REST API / webhooks |
| Telegram bot (auto-failover) | Dormant unless BlueBubbles is unreachable. Gateway health-checks BlueBubbles; if it fails, proactive notifications route to Telegram and you can chat there until iMessage recovers. |
| OpenClaw Gateway | Single Node.js process; receives normalized messages from all channels, routes them to the agent, returns responses |

The Gateway binds to localhost only. Remote access, if ever needed, goes through Tailscale — never port-forwarded.

**Access control:** The assistant responds only to one Apple ID (yours) on iMessage and one Telegram account. All other inbound messages are ignored. Configured via BlueBubbles `allowFrom` and Telegram bot allowlist.

**Auto-failover logic:** The Gateway pings BlueBubbles on a heartbeat (every 30s). If BlueBubbles is healthy, all outbound messages go through iMessage and inbound Telegram messages are ignored. If BlueBubbles fails the heartbeat, the Gateway switches to Telegram for both proactive notifications and interactive conversation. When BlueBubbles recovers, it switches back automatically.

**iMessage capabilities to support:**
- Inbound/outbound text messages
- Inbound images and screenshots (for image understanding)
- Inbound voice notes (transcribed via Whisper, then processed as text)
- Outbound rich text (links, formatting where iMessage supports it)

### Layer 2 — agent brain

| Component | Role |
|---|---|
| Claude API (claude-sonnet-4-6 or latest) | Sole reasoning model — handles all conversation, web search, intent parsing, drafting, decision-making, including financial reminders |

**Web search:** Claude API supports web search as a built-in tool. The agent can search the web and cite sources in response to any query. No separate search API needed.

**Image understanding:** Claude API supports vision natively. When you send an image via iMessage, BlueBubbles forwards it as base64, and the Gateway includes it in the Claude API call as an image content block.

**Voice note transcription:** When you send a voice note via iMessage, BlueBubbles captures the audio file. The Gateway runs it through a standalone Whisper installation (lightweight, runs on CPU) to produce a text transcript, then processes the transcript as a normal text message.

### Layer 3 — memory

| Component | Role |
|---|---|
| SQLite | Conversation log, user profile (key facts, preferences, habits), reminders, scheduled tasks |
| Chroma (or similar vector DB) | Semantic search over past conversations — "what did I say about X last month" |

**How memory works:**

1. **Conversation log.** Every message (yours and the assistant's) is stored with a timestamp. This is the raw record.
2. **User profile.** A structured store of facts the assistant has learned about you: name, location, workplace, preferences, habits, important dates, etc. Updated incrementally as new facts surface in conversation.
3. **Auto-compaction.** When the conversation context approaches the model's token limit, the system summarizes older messages into a compressed form and stores the summary. Recent messages stay verbatim; older ones are replaced by their summary. The assistant can always search the full conversation log via the vector DB if it needs to recall something specific from further back.
4. **Semantic recall.** Before responding, the agent queries the vector DB with the current message to pull in relevant past context. This is how it "remembers" things you said weeks ago without keeping the entire history in the prompt.

### Layer 4 — integrations and tools

Each integration is implemented as an MCP server or OpenClaw skill that the agent can call.

| Integration | Protocol | What it enables |
|---|---|---|
| Google Calendar | MCP server, self-hosted | Read/write calendar events, check availability, schedule meetings |
| Gmail | MCP server, self-hosted | Read inbox, draft replies, send emails (with confirmation for important ones) |
| Home Assistant | MCP server or REST API | Control smart devices (Alexa/Google Home devices bridged through HA). Requires setting up Home Assistant as a hub — not yet in place, Phase 9. |
| Bill reminders | User profile + cron | You tell the assistant your credit card due dates once. It stores them and reminds you X days before each. No bank connection needed. |
| Plaid (optional, future) | REST API | Only needed if you later want live balance amounts in reminders. Not required for due-date-only reminders. |
| Web search | Built into Claude API | Answer general knowledge questions with current information |
| Whisper | Standalone, local | Voice note transcription — audio in, text out |
| Reminders/scheduler | Built into the Gateway (cron) | Trigger notifications, daily briefings, recurring checks |

**Action confirmation tiers:**

| Tier | Examples | Behavior |
|---|---|---|
| Auto-execute | Set a reminder, look something up, check calendar, read email, turn on lights | Just does it, reports result |
| Confirm first | Send an email, book a reservation, modify a calendar event, make a purchase, change thermostat schedule | Shows you a preview, waits for "yes" |
| Never auto-execute | Anything involving money transfer, deleting data, sharing access | Always asks, shows full details |

### Layer 5 — proactivity engine

A scheduler (cron-based) that wakes the agent at configured intervals to check for things worth telling you about, without you asking.

**Scheduled routines:**

| Routine | Default schedule | What it does |
|---|---|---|
| Morning briefing | Daily, 9:00 AM | Weather, today's calendar, pending reminders, overnight email summary, any bills due soon |
| Bill/payment reminders | Daily check, notify when due dates approach | Checks user profile for stored due dates, alerts you X days before each |
| Custom reminders | User-defined (e.g. every 6 hours, every Monday) | Whatever you've asked it to remind you about |
| Email digest | Every N hours (configurable) | Scans inbox, surfaces anything that looks important or needs a reply |

**How proactive notifications work:**

1. Cron fires at the scheduled time.
2. The system gathers fresh context (new emails, calendar for today, stored bill due dates, etc.) using cheap API calls — no LLM involved yet.
3. Raw context is passed to Claude with the prompt: "Based on this context and what you know about the user, is there anything worth notifying them about right now? If not, stay silent."
4. If Claude decides yes, it composes a message and sends it via BlueBubbles to your iMessage.
5. If Claude decides no, nothing happens — no cost, no noise.

---

## Infrastructure

### Network and security

| Concern | Approach |
|---|---|
| Network exposure | Gateway binds to localhost only. No ports exposed to the internet. |
| Remote access (if needed) | Tailscale mesh VPN — encrypted, zero-config, no port forwarding |
| API keys and tokens | Stored encrypted at rest (age/sops or macOS Keychain). Never in plaintext config files. |
| BlueBubbles auth | Local connection only (same machine), token-based |

### Hardware requirements (MacBook, Apple Silicon)

| Resource | Minimum | Recommended |
|---|---|---|
| RAM | 8 GB | 16 GB+ |
| Storage | 5 GB free (DB + dependencies, no local model weights needed) | 20 GB+ |
| macOS | Ventura 13+ | Sonoma 14+ or Sequoia 15+ |
| Node.js | 22 LTS | 24 |

No GPU or large RAM requirement since there's no local model to run — the Gateway just needs to run a lightweight Node.js process and make API calls.

### Always-on considerations

A MacBook is fine for development and light use, but sleeps when the lid closes. Options:

- **For now:** Use Amphetamine or `caffeinate -di` to prevent sleep while plugged in and on your desk. Accept the assistant goes quiet when you're traveling with the laptop.
- **Later (if needed):** Move the Gateway + BlueBubbles to a cheap used Mac mini (even an older Intel model is sufficient, since there's no local model inference to run) that stays plugged in 24/7. The MacBook becomes just a dev machine.

---

## Data flow examples

### You text: "What's the weather tomorrow?"

1. iMessage → BlueBubbles → Gateway
2. Gateway sends to Claude API
3. Claude uses built-in web search tool → gets forecast
4. Response → Gateway → BlueBubbles → iMessage

### You text: "When is my TD Visa due?"

1. iMessage → BlueBubbles → Gateway
2. Gateway sends to Claude API
3. Claude checks user profile → finds stored due date ("TD Visa: around the 22nd each month, remind 4 days before")
4. Response: "Your TD Visa is usually due around the 22nd. That's in 5 days — want me to remind you on the 18th?"
5. Response → Gateway → BlueBubbles → iMessage

### You text: "Email Sarah to reschedule our lunch to Thursday"

1. iMessage → BlueBubbles → Gateway
2. Gateway sends to Claude API
3. Claude checks calendar for Thursday availability, drafts email
4. **Confirmation:** "I'll send Sarah this: 'Hi Sarah, could we move lunch to Thursday at 12:30? Let me know if that works.' — Send it?"
5. You reply "yes"
6. Claude sends via Gmail MCP → confirms sent

### 9:00 AM daily briefing (no message from you)

1. Cron fires → gathers weather API, calendar API, Gmail API data + checks user profile for upcoming bill due dates
2. Passes bundle to Claude: "Compose a morning briefing for the user"
3. Claude drafts: "Good morning — it's 18°C and sunny. You have a dentist appointment at 2pm and a call with Mike at 4. Your TD Visa is due in 3 days. Two emails overnight, one from your landlord about maintenance on the 15th."
4. Sends via BlueBubbles → appears in iMessage

---

## Estimated running costs (monthly, excluding hardware)

| Component | Cost |
|---|---|
| Claude API (Sonnet 4.6, light-moderate use) | ~$10-25 depending on message volume |
| OpenClaw + BlueBubbles | Free (open source) |
| Google Calendar + Gmail APIs | $0 (free tier) |
| Telegram bot | $0 (free) |
| Bill reminders | $0 (stored in user profile, no external API) |
| Whisper (voice transcription) | Free (runs locally) |

**Total estimated: $10-25/month** for typical personal use. Comparable to Poke Pro at $9.99/month, but with no message limits, no frequency caps on proactive checks, and unlimited customization. Claude API costs can be reduced by routing simple tasks to Haiku 4.5 ($1/$5 per million tokens) instead of Sonnet 4.6 ($3/$15).

**If Claude API credits run out:** All requests fail until credits are topped up (or auto-reload kicks in, if configured). Set a spending limit and auto-reload threshold in the Anthropic Console to avoid unexpected outages. Since there's no local fallback model in this design, the assistant goes fully silent until credits are restored — worth keeping an eye on usage, especially once proactive routines are running daily.

---

## Resolved decisions

| Question | Decision |
|---|---|
| Calendar | Google Calendar — well-supported MCP servers exist |
| Email | Gmail — well-supported MCP servers exist |
| Smart home | Alexa/Google Home devices exist but no Home Assistant yet. HA will need to be set up as a bridge hub (Phase 7). |
| Financial tracking | Credit card due date reminders only, stored in user profile. You tell the assistant your due dates once, it reminds you X days before. No Plaid or bank connection needed. Plaid is an optional future add-on if you want live balance amounts — would go through Claude API like everything else. |
| Multi-user | Single user only. One Apple ID on iMessage, one Telegram account. All other messages ignored. |
| Fallback channel | Telegram as auto-failover only. Gateway health-checks BlueBubbles every 30s; if down, routes to Telegram automatically. Switches back when iMessage recovers. Telegram is dormant during normal operation. |
| Voice notes | Yes. Transcribed via a standalone Whisper installation, then processed as text. |
| Local model (Ollama) | Removed from the design. All reasoning goes through Claude API for simplicity — no model routing logic, no local hardware requirement, no second model to maintain. Trade-off: financial/personal data now transits Anthropic's API (not used for training) rather than staying strictly on-device. |

## Remaining considerations

- **Home Assistant setup.** You'll need to install HA on the same MacBook (or a Raspberry Pi) and add your Alexa/Google Home devices as integrations. This is a well-documented but non-trivial setup — worth its own planning session when you reach Phase 8.
- **Google OAuth.** Both the Calendar and Gmail MCP servers require OAuth credentials. You'll need to create a Google Cloud project and configure OAuth consent. This is a one-time setup but has a few steps.
- **Plaid (optional, future).** If you later want live credit card balances in your reminders (not just due dates), Plaid supports all major Canadian banks (RBC, TD, BMO, CIBC, Scotiabank, Tangerine) with a free trial tier. This would go through Claude API like everything else in this design.

---

## Version control and deployment

### GitHub setup

Public repo — safe for portfolio visibility as long as secrets are excluded. Include a good README explaining what the project does, the architecture, and how to set it up.

**`.gitignore` must exclude:**
- `.env` (API keys: Claude, Telegram bot token, Google OAuth client secret)
- `*.db` / `*.sqlite` (conversation logs, user profile — your personal data)
- `chroma/` or any vector DB directory (your memory/embeddings)
- Any config files containing your Apple ID, phone number, or Telegram user ID
- `node_modules/`

**Include in the repo:**
- `.env.example` with placeholder values showing what variables are needed
- All source code, skills, scripts, cron configs
- The design doc
- A `README.md` explaining setup steps

### Deploying to Mac mini (Phase 9)

Once a Mac mini is ready, migration is:

1. Install Node.js and BlueBubbles on the Mac mini
2. `git clone` the repo
3. Copy `.env` and database files from MacBook to Mac mini (via `scp` or AirDrop)
4. `npm install`
5. Start the Gateway

After initial deployment, pushing updates from MacBook to Mac mini:

1. Develop and test on MacBook
2. `git push` from MacBook
3. SSH into Mac mini → `git pull` → restart Gateway

This keeps the MacBook as the dev machine and the Mac mini as the stable production server. Both always share the exact same codebase.

---

## Build order

A suggested sequence, each phase is independently useful:

| Phase | What | Outcome |
|---|---|---|
| 1 | Install OpenClaw + Telegram bot + Claude API key | Working chatbot you can text, with web search |
| 2 | Add memory layer (SQLite + Chroma + auto-compaction) | Assistant remembers you across sessions |
| 3 | Add BlueBubbles + iMessage channel (Telegram becomes auto-failover) | Same assistant, now in iMessage with automatic Telegram fallback |
| 4 | Add Google Calendar + Gmail integrations (OAuth setup) | Can read/write your schedule and inbox |
| 5 | Add proactivity engine (cron + daily briefing + bill reminders) | Morning summaries, CC due date reminders, email digests |
| 6 | Add image understanding + voice note transcription (Whisper) | Send photos/screenshots/voice notes, get responses |
| 7 | Set up Home Assistant + bridge Alexa/Google Home devices | Smart home control via text |
| 8 | Harden for always-on (Mac mini migration if needed) | Reliable 24/7 operation |
| Optional | Add Plaid for live credit card balances | Reminders include actual dollar amounts, not just due dates |
