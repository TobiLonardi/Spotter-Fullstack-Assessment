"""Nominatim search for free-text; structured lat/lon passes through unchanged."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any
from urllib.parse import urlencode

import requests

logger = logging.getLogger(__name__)

NOMINATIM_SEARCH = "https://nominatim.openstreetmap.org/search"
DEFAULT_UA = "SpotterTripPlanner/1.0 (assessment; contact: dev@localhost)"


@lru_cache(maxsize=256)
def _search_cached(query: str) -> tuple[float, float] | None:
    # Cache repeated queries — keeps us polite with Nominatim and speeds replans.
    params = urlencode(
        {
            "q": query,
            "format": "json",
            "limit": 1,
        }
    )
    url = f"{NOMINATIM_SEARCH}?{params}"
    headers = {"User-Agent": DEFAULT_UA}
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    data = r.json()
    if not data:
        return None
    item = data[0]
    return float(item["lat"]), float(item["lon"])


def resolve_location(value: Any) -> tuple[float, float]:
    """Normalize to (lat, lon): string → Nominatim, or dict/list the UI might send."""
    if isinstance(value, dict):
        lat = value.get("lat")
        lon = value.get("lon")
        if lon is None:
            lon = value.get("lng")
        if lat is None or lon is None:
            raise ValueError("Object location requires lat and lon (or lng).")
        return float(lat), float(lon)
    if isinstance(value, (list, tuple)):
        if len(value) < 2:
            raise ValueError("Coordinate array must have at least two numbers [lat, lon].")
        return float(value[0]), float(value[1])
    if isinstance(value, str):
        q = value.strip()
        if not q:
            raise ValueError("Empty address.")
        coords = _search_cached(q)
        if coords is None:
            raise ValueError(f"Could not geocode: {q!r}")
        return coords
    raise ValueError(
        "Location must be a non-empty string, an object with lat/lon (or lng), or [lat, lon]."
    )
