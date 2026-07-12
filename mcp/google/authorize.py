#!/usr/bin/env python3
"""Run this once, manually, to grant the assistant access: opens a browser
for you to sign into Google and approve the requested scopes, then saves
token.json. Never run this automatically or on the assistant's behalf."""
from auth import run_interactive_authorization

if __name__ == "__main__":
    run_interactive_authorization()
