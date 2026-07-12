#!/usr/bin/env python3
"""Google Workspace MCP server: Gmail (read + draft-only), Calendar (view +
add events), and Tasks (view + add/update due dates).

Uses Google's official Python client libraries against the stable REST APIs
(not Google's remote MCP servers, which are Developer Preview and don't cover
Tasks — see docs/DESIGN.md). The OpenClaw Gateway spawns this as a child
process and talks JSON-RPC over stdin/stdout, same pattern as mcp/flights/.

Requires a one-time `python3 authorize.py` run from this directory before use
— see auth.py and README.md.
"""
from __future__ import annotations

import base64
from email.mime.text import MIMEText
from typing import Any

from googleapiclient.discovery import build
from mcp.server.fastmcp import FastMCP

from auth import get_credentials

DEFAULT_MAX_RESULTS = 10
MAX_RESULTS_CEILING = 25

mcp = FastMCP("google-workspace")


def _clamp(n: int) -> int:
    return max(1, min(n, MAX_RESULTS_CEILING))


def _gmail():
    return build("gmail", "v1", credentials=get_credentials())


def _calendar():
    return build("calendar", "v3", credentials=get_credentials())


def _tasks():
    return build("tasks", "v1", credentials=get_credentials())


def _header(headers: list[dict[str, str]], name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


# ---- Gmail ----------------------------------------------------------------


@mcp.tool()
def gmail_search(query: str, max_results: int = DEFAULT_MAX_RESULTS) -> dict[str, Any]:
    """Search Gmail using standard Gmail search syntax.

    query: Gmail search syntax, e.g. "from:sarah is:unread", "subject:invoice
        after:2026/07/01", "newer_than:7d".
    max_results: how many messages to return (default 10, max 25).

    Returns a compact list: id, thread_id, subject, from, date, snippet.
    Use gmail_get_message with an id to read the full body.
    """
    svc = _gmail()
    resp = svc.users().messages().list(
        userId="me", q=query, maxResults=_clamp(max_results)
    ).execute()
    results = []
    for m in resp.get("messages", []):
        full = svc.users().messages().get(
            userId="me", id=m["id"], format="metadata",
            metadataHeaders=["Subject", "From", "Date"],
        ).execute()
        headers = full.get("payload", {}).get("headers", [])
        results.append({
            "id": full["id"],
            "thread_id": full.get("threadId"),
            "subject": _header(headers, "Subject"),
            "from": _header(headers, "From"),
            "date": _header(headers, "Date"),
            "snippet": full.get("snippet", ""),
        })
    return {"query": query, "count": len(results), "messages": results}


@mcp.tool()
def gmail_get_message(message_id: str) -> dict[str, Any]:
    """Get the full content of a Gmail message (from a gmail_search result id).

    Returns subject, from, to, date, and the plain-text body.
    """
    svc = _gmail()
    msg = svc.users().messages().get(userId="me", id=message_id, format="full").execute()
    headers = msg.get("payload", {}).get("headers", [])

    def extract_text(payload: dict[str, Any]) -> str:
        if payload.get("mimeType") == "text/plain" and "data" in payload.get("body", {}):
            return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", "replace")
        for part in payload.get("parts", []) or []:
            text = extract_text(part)
            if text:
                return text
        return ""

    return {
        "id": msg["id"],
        "thread_id": msg.get("threadId"),
        "subject": _header(headers, "Subject"),
        "from": _header(headers, "From"),
        "to": _header(headers, "To"),
        "date": _header(headers, "Date"),
        "body": extract_text(msg.get("payload", {}))[:8000],
    }


@mcp.tool()
def gmail_create_draft(
    to: str, subject: str, body: str, cc: str | None = None
) -> dict[str, Any]:
    """Create a Gmail draft. Does NOT send it — this server has no send tool,
    so there is no way to trigger a send through this integration. (Note: the
    underlying gmail.compose OAuth grant technically permits sending too —
    Google doesn't offer a narrower draft-only scope — but no tool here calls
    that capability.) The human sends it manually from Gmail after reviewing.

    to: recipient email address.
    subject: email subject.
    body: plain-text email body.
    cc: optional cc address.
    """
    message = MIMEText(body)
    message["to"] = to
    message["subject"] = subject
    if cc:
        message["cc"] = cc
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    svc = _gmail()
    draft = svc.users().drafts().create(
        userId="me", body={"message": {"raw": raw}}
    ).execute()
    return {
        "draft_id": draft["id"],
        "message_id": draft.get("message", {}).get("id"),
        "note": "Draft created, not sent. Review and send manually from Gmail.",
    }


@mcp.tool()
def gmail_list_drafts(max_results: int = DEFAULT_MAX_RESULTS) -> dict[str, Any]:
    """List existing Gmail drafts (id, subject, to, snippet)."""
    svc = _gmail()
    resp = svc.users().drafts().list(userId="me", maxResults=_clamp(max_results)).execute()
    drafts = []
    for d in resp.get("drafts", []):
        full = svc.users().drafts().get(userId="me", id=d["id"], format="full").execute()
        msg = full.get("message", {})
        headers = msg.get("payload", {}).get("headers", [])
        drafts.append({
            "draft_id": full["id"],
            "subject": _header(headers, "Subject"),
            "to": _header(headers, "To"),
            "snippet": msg.get("snippet", ""),
        })
    return {"count": len(drafts), "drafts": drafts}


@mcp.tool()
def gmail_delete_draft(draft_id: str) -> dict[str, Any]:
    """Permanently delete a Gmail draft (from a gmail_list_drafts result id).
    Only deletes — cannot send, same as the rest of this server."""
    svc = _gmail()
    svc.users().drafts().delete(userId="me", id=draft_id).execute()
    return {"deleted": draft_id}


# ---- Calendar ---------------------------------------------------------------


@mcp.tool()
def calendar_list_events(
    time_min: str | None = None,
    time_max: str | None = None,
    max_results: int = DEFAULT_MAX_RESULTS,
    calendar_id: str = "primary",
) -> dict[str, Any]:
    """List upcoming events on a calendar.

    time_min / time_max: RFC3339 timestamps, e.g. "2026-07-17T00:00:00Z"
        (optional — time_min defaults to now if omitted).
    max_results: how many events to return (default 10, max 25).
    calendar_id: which calendar; "primary" (default) is the main calendar.

    Returns each event's id, summary, start, end, and location.
    """
    svc = _calendar()
    resp = svc.events().list(
        calendarId=calendar_id,
        timeMin=time_min,
        timeMax=time_max,
        maxResults=_clamp(max_results),
        singleEvents=True,
        orderBy="startTime",
    ).execute()
    events = [
        {
            "id": e["id"],
            "summary": e.get("summary", "(no title)"),
            "start": e.get("start", {}).get("dateTime") or e.get("start", {}).get("date"),
            "end": e.get("end", {}).get("dateTime") or e.get("end", {}).get("date"),
            "location": e.get("location", ""),
        }
        for e in resp.get("items", [])
    ]
    return {"count": len(events), "events": events}


@mcp.tool()
def calendar_create_event(
    summary: str,
    start: str,
    end: str,
    description: str | None = None,
    location: str | None = None,
    calendar_id: str = "primary",
) -> dict[str, Any]:
    """Create a calendar event.

    summary: event title.
    start / end: RFC3339 timestamps, e.g. "2026-07-17T18:00:00-04:00", or a
        plain "YYYY-MM-DD" date for an all-day event.
    description / location: optional.
    calendar_id: which calendar; "primary" (default) is the main calendar.
    """
    is_all_day = "T" not in start
    body: dict[str, Any] = {
        "summary": summary,
        "start": {"date": start} if is_all_day else {"dateTime": start},
        "end": {"date": end} if is_all_day else {"dateTime": end},
    }
    if description:
        body["description"] = description
    if location:
        body["location"] = location
    svc = _calendar()
    created = svc.events().insert(calendarId=calendar_id, body=body).execute()
    return {"event_id": created["id"], "html_link": created.get("htmlLink")}


# ---- Tasks ------------------------------------------------------------------


@mcp.tool()
def tasks_list_tasklists() -> dict[str, Any]:
    """List the user's Google Tasks lists (id + title). Most people only have
    one, "My Tasks", but this lets you target a specific list if there are more."""
    svc = _tasks()
    resp = svc.tasklists().list().execute()
    return {
        "tasklists": [
            {"id": t["id"], "title": t["title"]} for t in resp.get("items", [])
        ]
    }


@mcp.tool()
def tasks_list(
    tasklist_id: str = "@default",
    show_completed: bool = False,
    max_results: int = DEFAULT_MAX_RESULTS,
) -> dict[str, Any]:
    """List tasks in a task list.

    tasklist_id: "@default" (the user's default list) or an id from
        tasks_list_tasklists.
    show_completed: include completed tasks (default False).
    max_results: how many tasks to return (default 10, max 25).

    Returns each task's id, title, notes, due date, and status.
    """
    svc = _tasks()
    resp = svc.tasks().list(
        tasklist=tasklist_id,
        showCompleted=show_completed,
        maxResults=_clamp(max_results),
    ).execute()
    tasks = [
        {
            "id": t["id"],
            "title": t.get("title", ""),
            "notes": t.get("notes", ""),
            "due": t.get("due"),
            "status": t.get("status"),
        }
        for t in resp.get("items", [])
    ]
    return {"count": len(tasks), "tasks": tasks}


@mcp.tool()
def tasks_create(
    title: str,
    due: str | None = None,
    notes: str | None = None,
    tasklist_id: str = "@default",
) -> dict[str, Any]:
    """Create a task, optionally with a due date.

    title: task title.
    due: RFC3339 date/time, e.g. "2026-07-20T00:00:00Z" (optional).
    notes: optional free-text notes.
    tasklist_id: "@default" (the user's default list) or an id from
        tasks_list_tasklists.
    """
    body: dict[str, Any] = {"title": title}
    if due:
        body["due"] = due
    if notes:
        body["notes"] = notes
    svc = _tasks()
    created = svc.tasks().insert(tasklist=tasklist_id, body=body).execute()
    return {"task_id": created["id"], "title": created.get("title")}


@mcp.tool()
def tasks_update(
    task_id: str,
    title: str | None = None,
    due: str | None = None,
    notes: str | None = None,
    status: str | None = None,
    tasklist_id: str = "@default",
) -> dict[str, Any]:
    """Update a task — e.g. change its due date, or mark it complete.

    task_id: id from tasks_list.
    title / due / notes: only the fields you pass are changed.
    status: "needsAction" or "completed" (optional).
    tasklist_id: "@default" (the user's default list) or an id from
        tasks_list_tasklists.
    """
    svc = _tasks()
    patch: dict[str, Any] = {}
    if title is not None:
        patch["title"] = title
    if due is not None:
        patch["due"] = due
    if notes is not None:
        patch["notes"] = notes
    if status is not None:
        patch["status"] = status
    updated = svc.tasks().patch(tasklist=tasklist_id, task=task_id, body=patch).execute()
    return {
        "task_id": updated["id"],
        "title": updated.get("title"),
        "due": updated.get("due"),
        "status": updated.get("status"),
    }


if __name__ == "__main__":
    mcp.run()
