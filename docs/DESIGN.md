# Personal AI assistant — design document

## Overview

A self-hosted, privacy-first personal AI assistant accessible primarily via iMessage (with Telegram as a backup channel). The assistant can hold conversations, search the web, understand images and voice notes, remember context across sessions, integrate with external apps, take actions on your behalf, and proactively notify you on a schedule. It runs entirely on your own hardware behind a private network. Single user only — responds exclusively to one Apple ID.

**Stack:** Claude API (via OpenClaw) for all reasoning. No local/self-hosted LLM (Ollama removed from scope — see "Resolved decisions" below).

**Current deployment phase:** Everything (OpenClaw Gateway + the iMessage bridge) runs on one machine — your MacBook — for development and testing. This is temporary. Once the build is stable, the Gateway + iMessage bridge migrate to a dedicated always-on Mac mini so the assistant runs 24/7 without depending on the MacBook staying awake. See "Always-on considerations" and "Version control and deployment" below for that migration path.

> **iMessage transport note:** OpenClaw removed BlueBubbles support. iMessage now runs through OpenClaw's bundled iMessage channel backed by the [`imsg`](https://github.com/steipete/imsg) CLI — the Gateway spawns `imsg` as a child process and talks JSON-RPC over stdin/stdout. There is no separate server, port, or webhook. This changed the design throughout; earlier BlueBubbles references have been updated.

---

## Core principles

- **Privacy-conscious, cloud-reasoning.** All conversation data, memory, and integrations run on your own hardware. The Claude API handles all reasoning — Anthropic does not train on API inputs, but data does transit to and get processed on Anthropic's servers for each request.
- **Confirm before acting.** High-stakes actions (sending emails, booking reservations) require your explicit confirmation. Low-stakes actions (setting a reminder, looking something up) proceed automatically.
- **One machine for now, dedicated hardware later.** Development and initial testing run entirely on your MacBook (Gateway + `imsg` together). Once stable, migrate the Gateway + `imsg` to a dedicated Mac mini for true 24/7 uptime — the MacBook then becomes just a dev machine again.

---

## Architecture

### Layer 1 — messaging channel

| Component | Role |
|---|---|
| `imsg` CLI (on macOS — currently your MacBook, later a dedicated Mac mini) | Bridges iMessage to the Gateway. The Gateway spawns it as a child process and speaks JSON-RPC over stdin/stdout. Reads inbound messages from the Messages database (`chat.db`) and sends via Messages.app. No server, port, or webhook. |
| Telegram bot (secondary channel) | A second messaging surface on the same Gateway. Stays available as a backup for proactive notifications and chat. See "Channel roles and failover" below for what it can and can't cover. |
| OpenClaw Gateway | Single Node.js process; receives normalized messages from all channels, routes them to the agent, returns responses |

The Gateway binds to localhost only. Remote access, if ever needed, goes through Tailscale — never port-forwarded.

**Access control:** The assistant responds only to one Apple ID (yours) on iMessage and one Telegram account. All other inbound messages are ignored. Configured via the iMessage channel's `allowFrom` (by handle — phone number or email) and the Telegram bot allowlist.

**Assistant identity — dedicated Apple ID (recommended):** The Mac running `imsg` should sign Messages into a *dedicated* Apple ID that belongs to the assistant, not your primary personal Apple ID. You then text the assistant from your own iPhone/primary Apple ID — it's simply a separate contact, and `allowFrom` is set to your primary handle so it only answers you. This keeps your primary iCloud identity (photos, backups, Find My, payment) off the assistant's machine entirely, which sharply limits the blast radius if that machine is ever compromised — and it matters more once Private API mode (below) is on the table, since that involves weakening the machine's OS protections.

**Channel roles and failover:** iMessage is the primary channel; Telegram is a secondary surface on the same Gateway. Note an architectural limit that the old BlueBubbles design glossed over: because `imsg` and the Gateway run on the *same* machine, if that machine is off or asleep the whole Gateway is down — there is nothing left running to fail *over* to. Telegram-as-backup therefore only helps for iMessage-*channel*-level failures while the Gateway is still up (e.g. `imsg` crashed, Messages signed out, an iMessage outage), not for whole-host outages. The old "Gateway pings a BlueBubbles REST server every 30s" mechanism no longer exists (there is no server to ping); health here is the `imsg` subprocess/probe state. The exact detection-and-route-switch behavior is a Phase 3 detail to wire up and verify, not something to treat as free.

**iMessage capability tiers (`imsg`):** the bundled channel has two levels, and which one we target is a deliberate security decision:

| Tier | What works | Requirement |
|---|---|---|
| **Basic** (current target) | Send/receive text, images, voice notes; message history; reply-to | Full Disk Access + Automation permissions. **SIP stays on.** |
| **Private API** (deferred) | Everything in Basic, plus tapbacks/reactions, typing indicators, read receipts, threaded replies, effects, polls, group management | `imsg launch` with **System Integrity Protection (SIP) disabled** on the Messages Mac |

**Decision:** target **Basic** for now. What Basic loses is cosmetic (the assistant can't send reactions or a native typing indicator — the short "on it" ack message covers the "I'm working on it" signal instead). Disabling SIP is a system-wide weakening of a core macOS protection, which cuts against this project's security posture, so it is not worth it on the MacBook for typing indicators. **Private API is revisited as a deliberate Mac-mini-phase decision** — on a dedicated single-purpose appliance signed into a *dedicated* Apple ID (see above), behind a private network, the realistic threat SIP defends against is small and the cost of turning it off is far more contained than on a daily-driver laptop. Deferred, not ruled out.

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

**Image understanding:** Claude API supports vision natively. When you send an image via iMessage, `imsg` surfaces the attachment from the Messages database, and the Gateway includes it in the Claude API call as an image content block. (Attachment forwarding is gated by the channel's `includeAttachments` setting, with a `mediaMaxMb` cap.)

**Voice note transcription:** When you send a voice note via iMessage, `imsg` exposes the audio attachment from the Messages database. The Gateway runs it through a standalone Whisper installation (lightweight, runs on CPU) to produce a text transcript, then processes the transcript as a normal text message.

### Layer 3 — memory

Uses OpenClaw's built-in memory system rather than a custom-built store. It already provides most of what a from-scratch SQLite + vector DB build would — curation, truncation-awareness, consolidation — without the extra engineering.

| Component | Role |
|---|---|
| `MEMORY.md` | Curated long-term facts and preferences, loaded into context at the start of every session |
| `memory/YYYY-MM-DD.md` | Raw daily notes — what happened, day by day |
| SQLite (OpenClaw-managed) | Backing store for the above, plus reminders and scheduled tasks |

**How memory works:**

1. **Daily notes.** Relevant events and context get written to that day's file as they happen — the raw record.
2. **Consolidation.** OpenClaw periodically distills daily notes into `MEMORY.md` (its "dreaming" pass), keeping the curated file small and current.
3. **Session start.** `MEMORY.md` loads into context at the start of every session — this is how the assistant remembers you without you re-explaining yourself each time.
4. **No vector/semantic search, for now.** `MEMORY.md` + daily notes cover "remembers key things about me" well. Digging up a specific buried detail from months back isn't supported yet — deferred until it's an actual problem in practice, not built preemptively.

**If semantic search is needed later:** OpenClaw supports it (`memory_search`, hybrid vector + keyword), but its default embedding provider is OpenAI — a second cloud provider this project avoids (see "Local model (Ollama)" in Resolved decisions). The plan, if this becomes necessary, is a locally-run embedding-only model (e.g. via Ollama) rather than any cloud embeddings API — a much lighter workload than the full local chat model this design already cut (embedding models are 10-100x smaller, one fast forward pass instead of token-by-token generation), and one that should run fine even on older hardware like a 2018 Intel Mac mini.

### Layer 4 — integrations and tools

Each integration is implemented as an MCP server or OpenClaw skill that the agent can call.

| Integration | Protocol | What it enables |
|---|---|---|
| Google Workspace (Gmail, Calendar, Tasks) | Custom MCP server (`mcp/google/`, Python) | Gmail: search/read inbox, create/list/delete drafts — no send tool exists, so the assistant cannot send mail through this integration (see `mcp/google/README.md`). Calendar: view + create events. Tasks: view, create, and update tasks including due dates. |
| Home Assistant | MCP server or REST API | Control smart devices (Alexa/Google Home devices bridged through HA). Requires setting up Home Assistant as a hub — not yet in place, Phase 9. |
| Bill reminders | User profile + cron | You tell the assistant your credit card due dates once. It stores them and reminds you X days before each. No bank connection needed. |
| Plaid (optional, future) | REST API | Only needed if you later want live balance amounts in reminders. Not required for due-date-only reminders. |
| Flight search (Ignav) | Custom MCP server (`mcp/flights/`, Python) | Search one-way/round-trip fares, get booking links; combined with cron + memory, track a route's price and alert on drops. First custom-built tool server in this project — the template for future ones. |
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
| Morning briefing | Daily, 9:00 AM | Weather, today's calendar, tasks due/overdue, overnight email highlights — built, tested, live |
| Bill/payment reminders | Folded into the morning briefing | No separate system — bills are just Google Tasks with due dates, so "tasks due/overdue" already covers them |
| Custom reminders | User-defined, one-off ("remind me at 3pm to...") | The assistant creates these itself via the `cron` tool when you ask — tested, works |
| Email digest | Folded into the morning briefing | No separate scheduled scan — "overnight email highlights" covers this |

**How proactive notifications actually work (built, not the original plan):**

A cron job with `sessionTarget: main` and `wakeMode: now` wakes the real agent directly — not a separate cheap pre-fetch step. The agent gets an instruction (e.g. "it's 9am, check weather/calendar/tasks/email and brief Elijah"), and since it's a normal turn on the main session, it has its usual tool access and just calls what it needs (`web_search`, `calendar_list_events`, `tasks_list`, `gmail_search`), then composes and sends a reply the same way it would in live chat. One LLM turn, real tool calls, no separate non-LLM gathering stage.

This depends on `agents.defaults.heartbeat.every` being non-zero (see "Resolved decisions" — `"0m"` silently breaks this delivery path entirely, not just periodic check-ins).

---

## Infrastructure

### Network and security

| Concern | Approach |
|---|---|
| Network exposure | Gateway binds to localhost only. No ports exposed to the internet. |
| Remote access (if needed) | Tailscale mesh VPN — encrypted, zero-config, no port forwarding |
| API keys and tokens | Stored in `.env` and OpenClaw's local config, restricted to owner-only file permissions (`600`/`700`). At-rest protection comes from FileVault (full-disk encryption), which is on. |
| iMessage bridge (`imsg`) | Local child process, no network surface (no server/port/webhook). Requires Full Disk Access (to read `chat.db`) and Automation permission (to send via Messages.app), granted interactively in macOS System Settings — not scriptable, and re-granted per machine. |
| macOS SIP | Left **enabled** (Basic tier). Disabling it for Private API features is deferred to the Mac-mini phase, and only on a dedicated single-purpose appliance signed into a dedicated Apple ID. |

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
- **Later (if needed):** Move the Gateway + `imsg` to a cheap used Mac mini (even an older Intel model is sufficient, since there's no local model inference to run) that stays plugged in 24/7. The MacBook becomes just a dev machine. Note: unlike the Gateway's own state (which copies over as files), the iMessage bridge's macOS permissions (Full Disk Access, Automation) must be re-granted interactively on the mini, and Messages must be re-signed into the assistant's dedicated Apple ID there — see "Deploying to Mac mini."

---

## Data flow examples

### You text: "What's the weather tomorrow?"

1. iMessage → imsg → Gateway
2. Gateway sends to Claude API
3. Claude uses built-in web search tool → gets forecast
4. Response → Gateway → imsg → iMessage

### You text: "When is my TD Visa due?"

1. iMessage → imsg → Gateway
2. Gateway sends to Claude API
3. Claude checks user profile → finds stored due date ("TD Visa: around the 22nd each month, remind 4 days before")
4. Response: "Your TD Visa is usually due around the 22nd. That's in 5 days — want me to remind you on the 18th?"
5. Response → Gateway → imsg → iMessage

### You text: "Email Sarah to reschedule our lunch to Thursday"

1. iMessage → imsg → Gateway
2. Gateway sends to Claude API
3. Claude checks calendar for Thursday availability, drafts email
4. **Confirmation:** "I'll send Sarah this: 'Hi Sarah, could we move lunch to Thursday at 12:30? Let me know if that works.' — Send it?"
5. You reply "yes"
6. Claude sends via Gmail MCP → confirms sent

### 9:00 AM daily briefing (no message from you)

1. Cron fires → gathers weather API, calendar API, Gmail API data + checks user profile for upcoming bill due dates
2. Passes bundle to Claude: "Compose a morning briefing for the user"
3. Claude drafts: "Good morning — it's 18°C and sunny. You have a dentist appointment at 2pm and a call with Mike at 4. Your TD Visa is due in 3 days. Two emails overnight, one from your landlord about maintenance on the 15th."
4. Sends via imsg → appears in iMessage

---

## Estimated running costs (monthly, excluding hardware)

| Component | Cost |
|---|---|
| Claude API (Sonnet 4.6, light-moderate use) | ~$10-25 depending on message volume |
| OpenClaw + `imsg` | Free (open source) |
| Gmail + Calendar + Tasks APIs | $0 (no billing account required; not metered/pay-per-call) |
| Flight data (Ignav API) | $0 (free tier: 1,000 requests, billed only on success) |
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
| Multi-user | Single user only. Assistant answers exactly one handle (`allowFrom` = your primary Apple ID / one Telegram account). All other messages ignored. |
| iMessage transport | OpenClaw's bundled iMessage channel via the `imsg` CLI (BlueBubbles was removed from OpenClaw). Gateway spawns `imsg` as a child process, JSON-RPC over stdio — no server/port/webhook. |
| iMessage capability tier | **Basic** (send/receive text, media, history; SIP stays on). Private API tier (tapbacks, typing indicators, threaded replies, effects, polls) needs SIP disabled and is deferred to the Mac-mini phase — cosmetic features not worth weakening OS security on the MacBook. |
| Assistant Apple ID | Dedicated Apple ID for the assistant, signed into Messages on the bridge machine — *not* your primary Apple ID. You text it as a separate contact. Keeps your primary iCloud identity off that machine and contains the blast radius (especially relevant if SIP is ever disabled for Private API). |
| Fallback channel | Telegram is a secondary channel on the same Gateway, not a true auto-failover for outages. Since `imsg` and the Gateway share a host, a whole-host outage takes both down — Telegram only helps for iMessage-channel-level failures while the Gateway is still running. Detection/route-switch behavior is a Phase 3 detail to build and verify. |
| Voice notes | Yes. Transcribed via a standalone Whisper installation, then processed as text. |
| Local model (Ollama) | Removed from the design. All reasoning goes through Claude API for simplicity — no model routing logic, no local hardware requirement, no second model to maintain. Trade-off: financial/personal data now transits Anthropic's API (not used for training) rather than staying strictly on-device. |
| Memory system | OpenClaw's built-in `MEMORY.md` + daily notes (SQLite-backed) instead of a custom-built store — already handles curation, truncation-awareness, and consolidation. No vector/semantic search for now: its default embedding provider is OpenAI, a second cloud provider this project avoids. If needed later, self-hosted via a local embedding-only model (e.g. Ollama), not a cloud API. |
| Flight data source | Ignav API, wrapped in our own Python MCP server (`mcp/flights/`). Google Flights has no public API (killed in 2018); Amadeus's free tier is ending; Ignav has a real free tier (1,000 requests) and does the hard part — fare *search + pricing*, not just status.
| Gmail/Calendar/Tasks integration | Custom Python MCP server (`mcp/google/`) on Google's stable REST APIs, not Google's own remote MCP servers (`gmailmcp.googleapis.com` etc.) — those are Developer Preview, not GA, and don't cover Tasks at all. OAuth scopes are deliberately narrow: `gmail.readonly` + `gmail.compose` (Google bundles send into `compose`, no draft-only scope exists — the real "can't send" boundary is that the server implements no send tool, not the OAuth grant itself), `calendar.events` (events only, not calendar management), `tasks` (Google's only write-capable Tasks scope). |
| Heartbeat interval | `"24h"`, not `"0m"`. Fully disabling heartbeat (Phase 1, for cost reasons) turned out to also silently break any cron job that delivers into the live chat session — one-off reminders and the morning briefing both route through the same heartbeat call to wake the agent and send. A job would fire, get gated by the disabled check, and vanish with no message and no visible error. `"24h"` unblocks that delivery path while keeping periodic cost far below the 30m default. | 

## Remaining considerations

- **Home Assistant setup.** You'll need to install HA on the same MacBook (or a Raspberry Pi) and add your Alexa/Google Home devices as integrations. This is a well-documented but non-trivial setup — worth its own planning session when you reach Phase 8.
- **Google OAuth — done, but re-run per machine.** Gmail/Calendar/Tasks are live via `mcp/google/`. The interactive consent step (`authorize.py`) can't be scripted — Google requires a real human in a browser — so it has to be re-run once on the Mac mini after migration too; see `mcp/google/README.md`.
- **Plaid (optional, future).** If you later want live credit card balances in your reminders (not just due dates), Plaid supports all major Canadian banks (RBC, TD, BMO, CIBC, Scotiabank, Tangerine) with a free trial tier. This would go through Claude API like everything else in this design.

---

## Version control and deployment

### GitHub setup

Public repo — safe for portfolio visibility as long as secrets are excluded. Include a good README explaining what the project does, the architecture, and how to set it up.

**`.gitignore` must exclude:**
- `.env` (API keys: Claude, Telegram bot token, Google OAuth client secret)
- `*.db` / `*.sqlite` (in case any personal data ever lands inside the repo directly)
- Any config files containing your Apple ID, phone number, or Telegram user ID
- `node_modules/`

Note: OpenClaw's actual runtime state — config, workspace/personality files, `MEMORY.md`, daily notes, sessions — lives entirely under `~/.openclaw`, outside this repo. It's never a git-tracked concern here; see "Deploying to Mac mini" below for how that state moves separately.

**Include in the repo:**
- `.env.example` with placeholder values showing what variables are needed
- All source code, skills, scripts, cron configs
- The design doc
- A `README.md` explaining setup steps

### Deploying to Mac mini (Phase 9)

Once a Mac mini is ready, migration is:

1. Install Node.js on the Mac mini
2. Sign Messages into the assistant's **dedicated Apple ID** on the mini, then install `imsg` in the same user context that runs the Gateway (`brew install steipete/tap/imsg`)
3. Grant `imsg` its macOS permissions **interactively** in System Settings — Full Disk Access (read `chat.db`) and Automation (send via Messages.app). This can't be scripted and doesn't transfer from the MacBook; it must be re-approved on the mini.
4. `git clone` the repo
5. Copy `.env` to the Mac mini (and update `channels.imessage.cliPath` / any host-specific paths for the mini)
6. Copy `~/.openclaw` wholesale (config, workspace/personality files, memory, sessions — everything OpenClaw needs lives here, only a few MB) via `scp`, AirDrop, or an external drive
7. `npm install`
8. Start the Gateway, then verify iMessage with `openclaw channels status --probe` before retiring the MacBook as the live host

After initial deployment, pushing updates from MacBook to Mac mini:

1. Develop and test on MacBook
2. `git push` from MacBook
3. SSH into Mac mini → `git pull` → restart Gateway

This keeps the MacBook as the dev machine and the Mac mini as the stable production server. Both always share the exact same codebase.

### Development workflow after migration

You keep developing on the MacBook — the mini is only the always-on host, not a dev machine. What flows over git (code, skills, scripts, cron definitions, config-as-code) is the bulk of development.

One caveat comes from the iMessage transport: `imsg` only actually runs where Messages is signed into the assistant's Apple ID *and* has the macOS permissions granted — which, after migration, is the mini. So a true end-to-end iMessage send/receive can't be tested on the MacBook. It rarely needs to be:

- **Use Telegram as the MacBook dev/test channel.** The agent logic (memory, integrations, prompts, tool behavior) is channel-agnostic, so Telegram exercises the same agent and runs anywhere. iMessage-*specific* behavior gets its final check on the mini (`openclaw channels status --probe` + a real text).
- **Dev and prod state stay separate automatically.** Each machine has its own `~/.openclaw` (config, memory, sessions), which lives outside the repo (gitignored) — so MacBook dev work never clobbers the mini's real memory. Don't manually copy dev memory over prod.
- **Optionally use the `--dev` profile.** `openclaw --dev gateway` runs an isolated instance under `~/.openclaw-dev` on a separate port (19001), so you can experiment on the MacBook without touching your main local setup.

---

## Build order

A suggested sequence, each phase is independently useful:

| Phase | What | Outcome |
|---|---|---|
| 1 | Install OpenClaw + Telegram bot + Claude API key | Working chatbot you can text, with web search |
| 2 | Wire up memory (OpenClaw's built-in `MEMORY.md` + daily notes) | Assistant remembers you across sessions |
| 3 | Add iMessage channel via `imsg` (Basic tier, SIP on; dedicated Apple ID) | Same assistant, now reachable over iMessage; Telegram stays as a secondary channel |
| 4 | Add Gmail + Calendar + Tasks integrations (custom MCP server, `mcp/google/`) | Can search/draft email, view/add calendar events, manage tasks and due dates |
| 5 | Add proactivity engine (morning briefing cron + custom reminders) | Morning summaries (weather/calendar/tasks/email), one-off "remind me" requests |
| 6 | Add image understanding + voice note transcription (Whisper) | Send photos/screenshots/voice notes, get responses |
| 7 | Set up Home Assistant + bridge Alexa/Google Home devices | Smart home control via text |
| 8 | Harden for always-on (Mac mini migration if needed) | Reliable 24/7 operation |
| Optional | Add flight search + price tracking (Ignav MCP server, `mcp/flights/`) | Ask it to find flights and watch a route, get pinged on price drops |
| Optional | Add Plaid for live credit card balances | Reminders include actual dollar amounts, not just due dates |
