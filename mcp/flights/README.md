# Flights MCP server (Ignav)

A small [MCP](https://modelcontextprotocol.io) server that gives the assistant flight
search + price data via the [Ignav API](https://ignav.com). The OpenClaw Gateway spawns
it as a child process and talks to it over stdio.

This is the project's first custom tool server — the template for future ones.

## Tools it exposes

| Tool | What it does |
|---|---|
| `search_one_way` | Cheapest one-way fares for a route + date |
| `search_round_trip` | Cheapest round-trip fares for a route + date pair |
| `get_booking_links` | Purchase links for an itinerary (via its `ignav_id`) |

Both search tools accept optional filters: `airlines_include` / `airlines_exclude`
(2-letter IATA codes, e.g. `["AC"]` for Air Canada), `cabin_class`, `max_stops`,
`max_price`, `market` (currency locale), and `max_results` (count, default 10, max 25).
Departure/return time filters (`depart_after_hour`, `depart_before_hour`, and for round
trips `return_after_hour` / `return_before_hour`) are 0-23 in local time — **whole-hour
granularity only, no minutes**, so "after 5:30pm" becomes hour 18. The Ignav API has no
result-count parameter, so `max_results` is applied client-side after sorting by price.

## Setup

Requires Python 3.10+ and an Ignav API key (`IGNAV_API_KEY`, already in the project `.env`).

```bash
cd mcp/flights
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Test it works

First confirm the key + endpoint directly (before involving MCP at all):

```bash
curl -s -X POST https://ignav.com/api/fares/one-way \
  -H "X-Api-Key: $IGNAV_API_KEY" -H "Content-Type: application/json" \
  -d '{"origin":"YYZ","destination":"JFK","departure_date":"2026-08-10"}'
```

Then exercise the MCP layer with the Inspector (optional, needs `pip install "mcp[cli]"`):

```bash
IGNAV_API_KEY=... mcp dev server.py
```

## Register with the OpenClaw Gateway

The server reads `IGNAV_API_KEY` from its environment. OpenClaw **sanitizes** the
environment it hands to MCP child processes — the key does *not* inherit from the
Gateway's `.env` (verified: without it, tool calls fail with "missing API key"). So it
must be passed explicitly in the server's config `env`. It lands in `~/.openclaw/openclaw.json`
(owner-only `600`, outside the repo), the same place the Telegram bot token already lives.

Register it without printing the key by reading it from `.env`:

```bash
JSON=$(python3 -c "
import json
key = next((l.split('=',1)[1].strip() for l in open('.env')
            if l.strip().startswith('IGNAV_API_KEY=')), '')
print(json.dumps({
    'command': '$PWD/.venv/bin/python',
    'args': ['$PWD/server.py'],
    'env': {'IGNAV_API_KEY': key},
}))
")
openclaw mcp set flights "$JSON"; unset JSON
```

(Use absolute paths — the Gateway may spawn from a different working directory. `scripts/setup.sh`
runs an equivalent step so this reproduces on a fresh machine.)

Verify, then restart the Gateway:

```bash
openclaw mcp list
npm start   # from repo root
```

## Price-tracking loop

Tracking a price over time isn't a single tool — it's this server plus the pieces already
in place: the assistant uses `search_*` to read the current fare, stores a baseline in
`MEMORY.md`/daily notes, schedules a recurring check with the `cron` tool, and messages
you if the price drops. All of that is driven from a normal chat request.

## Notes

- Free tier is 1,000 requests, billed only on success. A daily check on a few routes uses
  a handful per day, so that lasts a long time — but the assistant can create cron jobs
  itself now, so keep an eye on how many recurring checks it sets up.
- Ignav is a smaller/newer service; treat it as a convenience, not a dependency to build
  anything critical on.
