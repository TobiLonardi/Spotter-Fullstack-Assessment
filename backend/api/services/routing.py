"""Trip directions via TomTom Routing API (truck; car fallback if truck fails)."""

from __future__ import annotations

import logging
import os
from typing import Any

import requests

logger = logging.getLogger(__name__)

TOMTOM_CALCULATE_ROUTE = "https://api.tomtom.com/routing/1/calculateRoute"


def _locations_path_segment(coordinates_lonlat: list[list[float]]) -> str:
    """TomTom path uses latitude,longitude pairs separated by colons."""
    parts: list[str] = []
    for lon, lat in coordinates_lonlat:
        parts.append(f"{float(lat):.6f},{float(lon):.6f}")
    return ":".join(parts)


def _tomtom_request(
    coordinates_lonlat: list[list[float]],
    api_key: str,
    travel_mode: str,
    vehicle_commercial: bool,
) -> requests.Response:
    loc = _locations_path_segment(coordinates_lonlat)
    url = f"{TOMTOM_CALCULATE_ROUTE}/{loc}/json"
    params = {
        "key": api_key,
        "routeRepresentation": "polyline",
        "travelMode": travel_mode,
        "vehicleCommercial": str(vehicle_commercial).lower(),
        "vehicleEngineType": "combustion",
        "routeType": "fastest",
        "traffic": "false",
    }
    return requests.get(url, params=params, timeout=60)


def _parse_tomtom_route(data: dict[str, Any]) -> dict[str, Any]:
    err = data.get("detailedError")
    if err:
        msg = err.get("message") if isinstance(err, dict) else str(err)
        code = err.get("code", "") if isinstance(err, dict) else ""
        raise ValueError(f"TomTom routing error: {msg}" + (f" ({code})" if code else ""))

    routes = data.get("routes") or []
    if not routes:
        raise ValueError("No route returned from TomTom.")

    route = routes[0]
    summary = route.get("summary") or {}
    distance_m = float(summary.get("lengthInMeters", 0))
    duration_s = float(summary.get("travelTimeInSeconds", 0))

    legs = route.get("legs") or []
    segments_out: list[dict[str, Any]] = []
    coords: list[list[float]] = []

    for li, leg in enumerate(legs):
        ls = leg.get("summary") or {}
        segments_out.append(
            {
                "distance_m": float(ls.get("lengthInMeters", 0)),
                "duration_s": float(ls.get("travelTimeInSeconds", 0)),
                "steps": [],
            }
        )
        points = leg.get("points") or []
        for pi, p in enumerate(points):
            lon = float(p["longitude"])
            lat = float(p["latitude"])
            pair = [lon, lat]
            if li > 0 and pi == 0 and coords and coords[-1][0] == pair[0] and coords[-1][1] == pair[1]:
                continue
            coords.append(pair)

    if not coords and legs:
        raise ValueError("TomTom returned no route points (try routeRepresentation=polyline).")

    return {
        "coordinates": coords,
        "distance_m": distance_m,
        "duration_s": duration_s,
        "segments": segments_out,
    }


def get_directions(
    coordinates_lonlat: list[list[float]],
    api_key: str | None = None,
    base_url: str | None = None,
) -> dict[str, Any]:
    """
    Call TomTom Calculate Route. coordinates_lonlat: [[lon, lat], ...] in visit order.
    Returns dict with keys: coordinates, distance_m, duration_s, segments (per-leg summaries).
    """
    _ = base_url  # reserved for tests/mocks; TomTom uses fixed service URL

    key = api_key or os.environ.get("TOMTOM_API_KEY", "").strip()
    if not key:
        raise ValueError(
            "Missing TOMTOM_API_KEY. Add it to the project root .env file."
        )

    r = _tomtom_request(coordinates_lonlat, key, "truck", True)
    if r.ok:
        try:
            return _parse_tomtom_route(r.json())
        except ValueError as e:
            logger.warning("TomTom truck route rejected: %s", e)
    else:
        logger.warning("TomTom error %s: %s", r.status_code, r.text[:500])

    logger.warning("Retrying TomTom with travelMode=car.")
    r2 = _tomtom_request(coordinates_lonlat, key, "car", False)
    if not r2.ok:
        logger.warning("TomTom error %s: %s", r2.status_code, r2.text[:500])
        r2.raise_for_status()
    return _parse_tomtom_route(r2.json())


def meters_to_miles(m: float) -> float:
    return m * 0.000621371
