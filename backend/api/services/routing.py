"""Directions via OpenRouteService (driving-hgv)."""

from __future__ import annotations

import logging
import os
from typing import Any

import requests

logger = logging.getLogger(__name__)

ORS_DEFAULT = "https://api.openrouteservice.org/v2/directions/driving-hgv/geojson"


def get_directions(
    coordinates_lonlat: list[list[float]],
    api_key: str | None = None,
    base_url: str | None = None,
) -> dict[str, Any]:
    """
    Call ORS directions. coordinates_lonlat: [[lon, lat], ...] in order.
    Returns dict with keys: coordinates (list [lon, lat] for LineString), distance_m, duration_s, segments (list of per-leg summaries).
    """
    key = api_key or os.environ.get("ORS_API_KEY", "").strip()
    if not key:
        raise ValueError(
            "Missing ORS_API_KEY. Add it to the project root .env file."
        )
    url = (base_url or os.environ.get("ORS_BASE_URL") or ORS_DEFAULT).strip()
    headers = {
        "Authorization": key,
        "Content-Type": "application/json",
    }
    body = {"coordinates": coordinates_lonlat}
    r = requests.post(url, json=body, headers=headers, timeout=60)
    if not r.ok:
        logger.warning("ORS error %s: %s", r.status_code, r.text[:500])
        r.raise_for_status()
    data = r.json()
    features = data.get("features") or []
    if not features:
        raise ValueError("No route returned from ORS.")
    geom = features[0].get("geometry") or {}
    coords = geom.get("coordinates") or []
    props = features[0].get("properties") or {}
    summary = props.get("summary") or {}
    distance_m = float(summary.get("distance", 0))
    duration_s = float(summary.get("duration", 0))
    segs = props.get("segments") or []
    segments_out: list[dict[str, Any]] = []
    for s in segs:
        segments_out.append(
            {
                "distance_m": float(s.get("distance", 0)),
                "duration_s": float(s.get("duration", 0)),
                "steps": s.get("steps") or [],
            }
        )
    return {
        "coordinates": coords,
        "distance_m": distance_m,
        "duration_s": duration_s,
        "segments": segments_out,
    }


def meters_to_miles(m: float) -> float:
    return m * 0.000621371
