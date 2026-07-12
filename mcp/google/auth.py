"""Shared OAuth handling for the Google MCP server.

One-time interactive consent (run `python3 authorize.py` once) writes a local
token.json that this module then loads and silently refreshes on every
subsequent run. Never printed, never committed (see .gitignore).
"""
from __future__ import annotations

import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

HERE = os.path.dirname(os.path.abspath(__file__))
CLIENT_SECRET_PATH = os.path.join(HERE, "client_secret.json")
TOKEN_PATH = os.path.join(HERE, "token.json")

# Narrow, deliberately. Gmail: gmail.compose is the least-broad scope that
# still allows draft creation — Google bundles send capability into it (no
# separate draft-only scope exists), so the real "no send" boundary is that
# server.py implements no send tool, not the scope itself. Calendar:
# events-only (no calendar management). Tasks: full access (Google offers no
# narrower write scope). See docs/DESIGN.md "Resolved decisions".
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/tasks",
]


def get_credentials() -> Credentials:
    """Load cached credentials and refresh if needed. Raises if no token yet —
    run `python3 authorize.py` once first to create it interactively."""
    if not os.path.exists(TOKEN_PATH):
        raise RuntimeError(
            "No token.json found. Run `python3 authorize.py` once from "
            "mcp/google/ to complete the interactive Google sign-in."
        )
    creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())
    if not creds or not creds.valid:
        raise RuntimeError(
            "Stored Google credentials are invalid and could not be refreshed. "
            "Re-run `python3 authorize.py` from mcp/google/."
        )
    return creds


def run_interactive_authorization() -> None:
    """One-time setup: opens a browser for Google sign-in/consent, then saves
    token.json. Only ever run manually by a human, never by the MCP server
    itself (the agent should never trigger a browser OAuth flow)."""
    if not os.path.exists(CLIENT_SECRET_PATH):
        raise RuntimeError(
            f"Missing {CLIENT_SECRET_PATH}. Download it from Google Cloud "
            "Console (OAuth client, Desktop app type) and save it there first."
        )
    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_PATH, SCOPES)
    creds = flow.run_local_server(port=0)
    with open(TOKEN_PATH, "w") as f:
        f.write(creds.to_json())
    print(f"Saved credentials to {TOKEN_PATH}")
