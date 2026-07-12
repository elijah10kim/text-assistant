# Google Workspace MCP server

A [MCP](https://modelcontextprotocol.io) server giving the assistant Gmail, Google
Calendar, and Google Tasks access, built on Google's official Python client libraries
against the stable REST APIs. The OpenClaw Gateway spawns it as a child process and
talks to it over stdio — same pattern as `mcp/flights/`.

We deliberately did **not** use Google's own remote MCP servers (`gmailmcp.googleapis.com`
etc.) — they're Developer Preview (not GA) and don't cover Tasks at all. See
`docs/DESIGN.md` "Resolved decisions" for the full reasoning.

## Tools it exposes

| Tool | What it does |
|---|---|
| `gmail_search` | Search inbox with Gmail query syntax |
| `gmail_get_message` | Read a full message body |
| `gmail_create_draft` | Create a draft (see "About the send scope" below) |
| `gmail_list_drafts` | List existing drafts |
| `gmail_delete_draft` | Delete a draft |
| `calendar_list_events` | List upcoming events |
| `calendar_create_event` | Create an event |
| `tasks_list_tasklists` | List task lists |
| `tasks_list` | List tasks in a list |
| `tasks_create` | Create a task, optionally with a due date |
| `tasks_update` | Update a task (due date, title, notes, mark complete) |

## About the send scope

There's no Gmail scope that allows creating drafts without also technically permitting
send — `gmail.compose` bundles both, and Google doesn't offer a narrower draft-only
tier. The real boundary here isn't the OAuth scope, it's that **this server implements
no send tool** — `gmail_send` doesn't exist, so there's no way for the agent to trigger
a send through this integration, regardless of what the underlying credential could
technically do if used directly. `token.json` should be protected accordingly (it is,
by `.gitignore` + the same file-permission hardening as everything else in this repo).

## Scopes requested

- `gmail.readonly` + `gmail.compose` (read + draft, see above)
- `calendar.events` (view + manage events only, not calendar settings/list management)
- `tasks` (full read/write — Google doesn't offer a narrower write-capable Tasks scope)

## One-time setup

### 1. Google Cloud Console

- Create a project, enable **Gmail API**, **Google Calendar API**, **Google Tasks API**
  (the plain APIs — not "Gmail MCP API" / "Calendar MCP API" / "Workspace MCP API",
  which are a different, Developer Preview product we're not using)
- OAuth consent screen: External, Testing is fine for personal use, add yourself as a
  test user, add scopes:
  - `https://www.googleapis.com/auth/gmail.readonly`
  - `https://www.googleapis.com/auth/gmail.compose`
  - `https://www.googleapis.com/auth/calendar.events`
  - `https://www.googleapis.com/auth/tasks`
- Create an OAuth client ID, application type **Desktop app**, download the JSON

### 2. Save the credentials file

Save the downloaded file as `mcp/google/client_secret.json` (gitignored — never commit
it). Nothing else reads or needs its contents except this server.

### 3. Install and authorize

```bash
cd mcp/google
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 authorize.py
```

`authorize.py` opens your browser for a real Google sign-in/consent — only ever run
this yourself, never automated, never triggered by the agent. It saves `token.json`
(also gitignored) which the server then reads and silently refreshes on its own.

## Register with the OpenClaw Gateway

```bash
openclaw mcp set google-workspace '{
  "command": "'"$PWD"'/.venv/bin/python",
  "args": ["'"$PWD"'/server.py"]
}'
```

(Absolute paths — the Gateway may spawn from a different working directory.) Unlike
the flights server, no secret needs injecting into this config — `server.py` reads
`client_secret.json`/`token.json` directly from disk. Verify, then restart:

```bash
openclaw mcp list
npm start   # from repo root
```

`scripts/setup.sh` reproduces the venv + registration steps automatically if
`client_secret.json` is present, but the interactive `authorize.py` step can't be
scripted (Google requires a real human in a browser) — it always has to be run by hand
once, on each new machine (including the eventual Mac mini migration).
