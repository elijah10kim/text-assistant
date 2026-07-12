#!/usr/bin/env python3
"""Ignav flight-search MCP server.

Exposes flight fare search and booking-link tools backed by the Ignav API
(https://ignav.com). The OpenClaw Gateway spawns this as a child process and
talks to it over stdio — the same MCP transport every other tool server uses.

Requires IGNAV_API_KEY in the environment the server runs in.
"""
from __future__ import annotations

import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

IGNAV_BASE_URL = "https://ignav.com/api"
API_KEY_ENV = "IGNAV_API_KEY"
REQUEST_TIMEOUT_SECONDS = 30
# The Ignav API has no result-limit parameter, so we cap client-side. Default a
# small number (large JSON blobs just burn context tokens) with a hard ceiling
# so the model can't ask for an unreasonable dump.
DEFAULT_MAX_RESULTS = 5
MAX_RESULTS_CEILING = 10

mcp = FastMCP("flights")


def _api_key() -> str:
    key = os.environ.get(API_KEY_ENV, "").strip()
    if not key:
        raise RuntimeError(
            f"{API_KEY_ENV} is not set in the MCP server's environment."
        )
    return key


def _post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    """POST to the Ignav API, returning parsed JSON or raising a clear error."""
    url = f"{IGNAV_BASE_URL}{path}"
    headers = {"X-Api-Key": _api_key(), "Content-Type": "application/json"}
    try:
        resp = httpx.post(
            url, json=payload, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS
        )
    except httpx.RequestError as exc:
        raise RuntimeError(f"Could not reach Ignav ({exc}).") from exc
    if resp.status_code == 401:
        raise RuntimeError("Ignav rejected the API key (401). Check IGNAV_API_KEY.")
    if resp.status_code >= 400:
        raise RuntimeError(f"Ignav returned {resp.status_code}: {resp.text[:300]}")
    return resp.json()


def _cheapest_first(data: dict[str, Any], max_results: int) -> dict[str, Any]:
    """Sort itineraries by price and cap the count so responses stay compact."""
    limit = max(1, min(max_results, MAX_RESULTS_CEILING))
    itineraries = data.get("itineraries") or []

    def price_of(it: dict[str, Any]) -> float:
        amount = (it.get("price") or {}).get("amount")
        return float(amount) if isinstance(amount, (int, float)) else float("inf")

    trimmed = sorted(itineraries, key=price_of)[:limit]
    return {**{k: v for k, v in data.items() if k != "itineraries"}, "itineraries": trimmed}


def _time_range(after_hour: int | None, before_hour: int | None) -> dict[str, int] | None:
    """Build an Ignav time-range object from earliest/latest departure hours."""
    rng: dict[str, int] = {}
    if after_hour is not None:
        rng["earliest_hour"] = after_hour
    if before_hour is not None:
        rng["latest_hour"] = before_hour
    return rng or None


def _apply_filters(
    payload: dict[str, Any],
    *,
    cabin_class: str | None,
    max_stops: int | None,
    airlines_include: list[str] | None,
    airlines_exclude: list[str] | None,
    depart_after_hour: int | None,
    depart_before_hour: int | None,
    max_price: int | None,
    market: str | None,
) -> dict[str, Any]:
    """Attach the optional filters shared by one-way and round-trip searches."""
    if cabin_class:
        payload["cabin_class"] = cabin_class
    if max_stops is not None:
        payload["max_stops"] = max_stops
    if airlines_include:
        payload["airlines_include"] = [c.upper() for c in airlines_include]
    if airlines_exclude:
        payload["airlines_exclude"] = [c.upper() for c in airlines_exclude]
    departure_range = _time_range(depart_after_hour, depart_before_hour)
    if departure_range:
        payload["departure_time_range"] = departure_range
    if max_price is not None:
        payload["max_price"] = max_price
    if market:
        payload["market"] = market
    return payload


@mcp.tool()
def search_one_way(
    origin: str,
    destination: str,
    departure_date: str,
    cabin_class: str | None = None,
    max_stops: int | None = None,
    airlines_include: list[str] | None = None,
    airlines_exclude: list[str] | None = None,
    depart_after_hour: int | None = None,
    depart_before_hour: int | None = None,
    max_price: int | None = None,
    market: str = "CA",
    max_results: int = DEFAULT_MAX_RESULTS,
) -> dict[str, Any]:
    """Search one-way flight fares for a route and date.

    origin / destination: IATA airport codes (e.g. "YYZ", "LGA").
    departure_date: "YYYY-MM-DD".
    cabin_class: e.g. "economy", "business" (optional).
    max_stops: 0 for nonstop only (optional).
    airlines_include / airlines_exclude: lists of 2-letter IATA airline codes,
        e.g. ["AC"] for Air Canada only, or ["F9"] to exclude Frontier (optional).
    depart_after_hour / depart_before_hour: 0-23 in the departure airport's local
        time. Whole-hour granularity only (no minutes), so "after 5:30pm" means
        depart_after_hour=18. (optional)
    max_price: strict maximum in the market's currency (optional).
    market: 2-letter country code for locale/currency. Defaults to "CA" (Canadian
        dollars); pass another code, e.g. "US", for a different currency.
    max_results: how many of the cheapest itineraries to return (default 5, max 10).

    Returns itineraries cheapest-first, each with price (amount + currency), the
    outbound leg, cabin_class, and an ignav_id you can pass to get_booking_links.
    """
    payload = _apply_filters(
        {
            "origin": origin.upper(),
            "destination": destination.upper(),
            "departure_date": departure_date,
        },
        cabin_class=cabin_class,
        max_stops=max_stops,
        airlines_include=airlines_include,
        airlines_exclude=airlines_exclude,
        depart_after_hour=depart_after_hour,
        depart_before_hour=depart_before_hour,
        max_price=max_price,
        market=market,
    )
    return _cheapest_first(_post("/fares/one-way", payload), max_results)


@mcp.tool()
def search_round_trip(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str,
    cabin_class: str | None = None,
    max_stops: int | None = None,
    airlines_include: list[str] | None = None,
    airlines_exclude: list[str] | None = None,
    depart_after_hour: int | None = None,
    depart_before_hour: int | None = None,
    return_after_hour: int | None = None,
    return_before_hour: int | None = None,
    max_price: int | None = None,
    market: str = "CA",
    max_results: int = DEFAULT_MAX_RESULTS,
) -> dict[str, Any]:
    """Search round-trip flight fares for a route and date pair.

    origin / destination: IATA airport codes (e.g. "YYZ", "LGA").
    departure_date / return_date: "YYYY-MM-DD"; return must be on or after departure.
    depart_after_hour / depart_before_hour: filter the OUTBOUND leg by local hour (0-23).
    return_after_hour / return_before_hour: filter the RETURN leg by local hour (0-23).
        All time filters are whole-hour granularity (no minutes).
    cabin_class, max_stops, airlines_include, airlines_exclude, max_price, market,
        max_results: same as search_one_way (all optional).

    Returns itineraries cheapest-first, each with price, outbound and inbound legs,
    cabin_class, and an ignav_id for get_booking_links.
    """
    payload = _apply_filters(
        {
            "origin": origin.upper(),
            "destination": destination.upper(),
            "departure_date": departure_date,
            "return_date": return_date,
        },
        cabin_class=cabin_class,
        max_stops=max_stops,
        airlines_include=airlines_include,
        airlines_exclude=airlines_exclude,
        depart_after_hour=depart_after_hour,
        depart_before_hour=depart_before_hour,
        max_price=max_price,
        market=market,
    )
    return_range = _time_range(return_after_hour, return_before_hour)
    if return_range:
        payload["return_time_range"] = return_range
    return _cheapest_first(_post("/fares/round-trip", payload), max_results)


@mcp.tool()
def get_booking_links(ignav_id: str) -> dict[str, Any]:
    """Get booking/purchase links for a specific itinerary.

    ignav_id: the id from a search_one_way or search_round_trip result.

    Returns booking options, each with provider_name, provider_type
    ("airline" or "third_party"), price, and a direct booking url. May be empty
    if no purchase options are currently available.
    """
    return _post("/fares/booking-links", {"ignav_id": ignav_id})


if __name__ == "__main__":
    # FastMCP.run() defaults to stdio transport, which is how the Gateway spawns us.
    mcp.run()
