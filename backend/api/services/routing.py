"""Directions via OpenRouteService (driving-hgv, with driving-car fallback)."""

from __future__ import annotations

import logging
import os
from typing import Any

import requests

logger = logging.getLogger(__name__)

ORS_DIRECTIONS_BASE = "https://api.openrouteservice.org/v2/directions"


def _ors_directions_url(profile: str) -> str:
    p = profile.strip() or "driving-hgv"
    return f"{ORS_DIRECTIONS_BASE}/{p}/geojson"


def _resolve_ors_url() -> str:
    explicit = os.environ.get("ORS_BASE_URL", "").strip()
    if explicit:
        return explicit
    profile = (os.environ.get("ORS_PROFILE") or "driving-hgv").strip() or "driving-hgv"
    return _ors_directions_url(profile)


def _ors_profile_unknown_response(r: requests.Response) -> bool:
    if r.status_code != 400:
        return False
    try:
        data = r.json()
        err = data.get("error") or {}
        if err.get("code") == 2003:
            return True
        msg = (err.get("message") or "").lower()
        return "profile" in msg and "unknown" in msg
    except Exception:
        text = (r.text or "").lower()
        return "profile" in text and "unknown" in text


def _fallback_car_url(url: str) -> str | None:
    normalized = url.replace("\\", "/")
    if "/driving-hgv/" not in normalized:
        return None
    return url.replace("/driving-hgv/", "/driving-car/", 1)


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
    url = (base_url or _resolve_ors_url()).strip()
    headers = {
        "Authorization": key,
        "Content-Type": "application/json",
    }
    body = {"coordinates": coordinates_lonlat}
    r = requests.post(url, json=body, headers=headers, timeout=60)
    if not r.ok:
        logger.warning("ORS error %s: %s", r.status_code, r.text[:500])
        car_url = _fallback_car_url(url)
        if car_url and _ors_profile_unknown_response(r):
            logger.warning("Retrying ORS with driving-car (driving-hgv rejected).")
            r = requests.post(car_url, json=body, headers=headers, timeout=60)
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
