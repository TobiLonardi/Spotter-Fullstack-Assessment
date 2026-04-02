"""Geocode addresses via Nominatim (OSM)."""

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


def resolve_location(
    value: str | dict[str, Any],
) -> tuple[float, float]:
    """
    Return (lat, lon) for a free-text query or {"lat": x, "lon": y} / {"lat", "lng"}.
    """
    if isinstance(value, dict):
        lat = value.get("lat")
        lon = value.get("lon")
        if lon is None:
            lon = value.get("lng")
        if lat is None or lon is None:
            raise ValueError("Object location requires lat and lon (or lng).")
        return float(lat), float(lon)
    q = (value or "").strip()
    if not q:
        raise ValueError("Empty address.")
    coords = _search_cached(q)
    if coords is None:
        raise ValueError(f"Could not geocode: {q!r}")
    return coords
