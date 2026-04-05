"""
HOS planner for property-carrying — educational only, not certified.

Core limits: 11 drive / 10 off, 14h elapsed from go-on-duty, 30m after 8h driving,
70h on-duty in a rolling 8-day window, 34h off clears the cycle (simplified vs real restart rules).

Grid labels: ≥7h consecutive rest → SB (§395.1(g) long leg of split); 10h reset drawn as 7h SB + 3h OFF;
34h restart as all OFF. Math does not care about SB vs OFF except for display.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections import defaultdict
from datetime import datetime, time, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

MIN_10H = 600
MIN_11_DRIVE = 660
MIN_14_WINDOW = 840
MIN_8_DRIVE = 480
MIN_30_BREAK = 30
MIN_7H_SB = 7 * 60  # §395.1(g): long segment of split berth must be ≥7h consecutive in sleeper
MIN_10H_SB_PART = MIN_7H_SB
MIN_10H_OFF_PART = MIN_10H - MIN_7H_SB  # 3h — pairs with 7h SB for 10h consecutive rest
MIN_34H_RESTART = 34 * 60
FUEL_ON_MIN = 30
PICKUP_ON_MIN = 60
DROPOFF_ON_MIN = 60
GRID_MIN = 15
CYCLE_WINDOW = timedelta(days=8)
CYCLE_MAX_ON_DUTY_MIN = 70.0 * 60.0

Status = Literal["OFF", "SB", "ON", "D"]


def _interval_overlap_minutes(
    seg_start: datetime, seg_end: datetime, ws: datetime, we: datetime
) -> float:
    lo = max(seg_start, ws)
    hi = min(seg_end, we)
    if hi <= lo:
        return 0.0
    return (hi - lo).total_seconds() / 60.0


def _on_duty_minutes_in_window(
    intervals: list[tuple[datetime, datetime]],
    window_end: datetime,
) -> float:
    """Rolling 8-day on-duty (D+ON) total ending at `window_end`."""
    ws = window_end - CYCLE_WINDOW
    total = 0.0
    for a, b in intervals:
        total += _interval_overlap_minutes(a, b, ws, window_end)
    return total


def _total_on_duty_after_block(
    intervals: list[tuple[datetime, datetime]],
    block_start: datetime,
    block_end: datetime,
) -> float:
    """What the 70h/8d tally would be if we tack on one more on-duty block."""
    we = block_end
    ws = we - CYCLE_WINDOW
    total = _on_duty_minutes_in_window(intervals, we)
    total += _interval_overlap_minutes(block_start, block_end, ws, we)
    return total


def _max_feasible_on_duty_chunk(
    intervals: list[tuple[datetime, datetime]],
    t: datetime,
    hi_minutes: int,
) -> int:
    """Binary search: longest on-duty stretch from `t` that still fits under 70/8."""
    if hi_minutes <= 0:
        return 0
    lo_b, hi_b = 0, hi_minutes
    best = 0
    while lo_b <= hi_b:
        mid = (lo_b + hi_b) // 2
        te = t + timedelta(minutes=mid)
        used = _total_on_duty_after_block(intervals, t, te)
        if used <= CYCLE_MAX_ON_DUTY_MIN + 1e-6:
            best = mid
            lo_b = mid + 1
        else:
            hi_b = mid - 1
    return best


def next_fuel_threshold_mile(odometer: float) -> float:
    """Planning rule: stop every 1000 mi → next whole thousand ahead of `odometer`."""
    return (int(odometer) // 1000 + 1) * 1000


def split_leg_by_fuel(
    odometer_start: float,
    miles_total: float,
    minutes_total: float,
) -> list[tuple[float, float]]:
    """Chop a drive into pre-threshold + post-threshold chunks so we can insert fuel ON."""
    if miles_total <= 0:
        return []
    chunks: list[tuple[float, float]] = []
    odo = odometer_start
    m_rem = miles_total
    min_rem = minutes_total

    while m_rem > 1e-6:
        target = next_fuel_threshold_mile(odo)
        miles_to_threshold = max(0.0, target - odo)
        if miles_to_threshold <= 1e-6:
            target = odo + 1000.0
            miles_to_threshold = 1000.0
        use_m = min(miles_to_threshold, m_rem)
        use_min = min_rem * (use_m / m_rem) if m_rem > 0 else 0.0
        chunks.append((use_m, use_min))
        odo += use_m
        m_rem -= use_m
        min_rem -= use_min
    return chunks


@dataclass
class HosState:
    consecutive_off: int = 0
    driving_since_reset: int = 0
    # Elapsed minutes since start of current duty period (after 10h reset): ON + D + short
    # off-duty/SB; matches FMCSA 14-hour *consecutive* window (breaks do not pause the clock).
    on_duty_since_reset: int = 0
    driving_since_30break: int = 0

    def apply_10h_reset(self) -> None:
        self.consecutive_off = 0
        self.driving_since_reset = 0
        self.on_duty_since_reset = 0
        self.driving_since_30break = 0

    def apply_30break_reset(self) -> None:
        self.driving_since_30break = 0


def _max_drive_minutes(state: HosState) -> int:
    if state.driving_since_30break >= MIN_8_DRIVE:
        return 0
    a = MIN_11_DRIVE - state.driving_since_reset
    b = MIN_14_WINDOW - state.on_duty_since_reset
    c = MIN_8_DRIVE - state.driving_since_30break
    return max(0, min(a, b, c))


def _append_event(
    events: list[dict[str, Any]],
    start: datetime,
    end: datetime,
    status: Status,
    label: str,
) -> None:
    if end <= start:
        return
    events.append(
        {
            "status": status,
            "start": start,
            "end": end,
            "label": label,
        }
    )


def _finish_off_period(off_streak: int, state: HosState) -> None:
    """Apply HOS resets after a contiguous off-duty block ends."""
    if off_streak <= 0:
        return
    # ≥10h consecutive off resets the 11/14h clocks; longer rests (e.g. 34h cycle restart) satisfy this too.
    if off_streak >= MIN_10H:
        state.apply_10h_reset()
    elif off_streak >= MIN_30_BREAK:
        state.apply_30break_reset()


def simulate_hos(
    work_items: list[tuple[str, int, str]],
    start: datetime,
    initial_cycle_used_hours: float,
) -> list[dict[str, Any]]:
    """Walk `work_items` ("drive"|"on", minutes, label); D and ON both feed the 70h/8d window."""
    state = HosState()
    events: list[dict[str, Any]] = []
    t = start
    off_streak = 0
    cycle_intervals: list[tuple[datetime, datetime]] = []
    ih = max(0.0, float(initial_cycle_used_hours))
    if ih > 0:
        ghost_start = start - timedelta(hours=ih)
        cycle_intervals.append((ghost_start, start))

    def clear_cycle_after_restart() -> None:
        cycle_intervals.clear()

    def emit_off(mins: int, label: str, *, sb_if_long: bool = True) -> None:
        nonlocal t, off_streak
        if mins <= 0:
            return
        # Model full 10h daily reset as 7h sleeper + 3h off duty (§395.3(a)(1) combined rest).
        if (
            mins == MIN_10H
            and sb_if_long
            and label == "10-hour off-duty reset"
        ):
            emit_off(
                MIN_10H_SB_PART,
                "10-hour off-duty reset — 7h sleeper berth",
                sb_if_long=True,
            )
            emit_off(
                MIN_10H_OFF_PART,
                "10-hour off-duty reset — 3h off duty",
                sb_if_long=False,
            )
            return
        end = t + timedelta(minutes=mins)
        use_sb = sb_if_long and mins >= MIN_7H_SB
        rest_status: Status = "SB" if use_sb else "OFF"
        _append_event(events, t, end, rest_status, label)
        off_streak += mins
        t = end
        state.on_duty_since_reset += mins

    def start_on_or_drive() -> None:
        nonlocal off_streak
        if off_streak > 0:
            _finish_off_period(off_streak, state)
            off_streak = 0

    def emit_on(mins: int, label: str) -> None:
        nonlocal t, off_streak
        start_on_or_drive()
        remaining = mins
        while remaining > 0:
            cap = _max_feasible_on_duty_chunk(cycle_intervals, t, remaining)
            if cap <= 0:
                emit_off(MIN_34H_RESTART, "34-hour cycle restart", sb_if_long=False)
                clear_cycle_after_restart()
                _finish_off_period(off_streak, state)
                off_streak = 0
                continue
            chunk = cap
            end = t + timedelta(minutes=chunk)
            _append_event(events, t, end, "ON", label)
            state.on_duty_since_reset += chunk
            cycle_intervals.append((t, end))
            t = end
            remaining -= chunk

    def emit_drive(mins_total: int, label: str) -> None:
        nonlocal t, off_streak
        start_on_or_drive()
        remaining = mins_total
        while remaining > 0:
            if state.driving_since_30break >= MIN_8_DRIVE:
                emit_off(MIN_30_BREAK, "30-minute break")
                _finish_off_period(off_streak, state)
                off_streak = 0
                continue

            md = _max_drive_minutes(state)
            if md == 0:
                if (
                    state.driving_since_reset >= MIN_11_DRIVE
                    or state.on_duty_since_reset >= MIN_14_WINDOW
                ):
                    emit_off(MIN_10H, "10-hour off-duty reset")
                else:
                    emit_off(MIN_30_BREAK, "30-minute break")
                _finish_off_period(off_streak, state)
                off_streak = 0
                continue

            cap = _max_feasible_on_duty_chunk(cycle_intervals, t, min(md, remaining))
            step = int(min(md, remaining, cap))
            if step <= 0:
                emit_off(MIN_34H_RESTART, "34-hour cycle restart", sb_if_long=False)
                clear_cycle_after_restart()
                _finish_off_period(off_streak, state)
                off_streak = 0
                continue

            end = t + timedelta(minutes=step)
            _append_event(events, t, end, "D", label)
            state.driving_since_reset += step
            state.on_duty_since_reset += step
            state.driving_since_30break += step
            cycle_intervals.append((t, end))
            t = end
            remaining -= step

    for kind, minutes, lbl in work_items:
        if minutes <= 0:
            continue
        if kind == "on":
            emit_on(minutes, lbl)
        else:
            emit_drive(minutes, lbl)

    return events


def build_work_items(
    drive_to_pickup_legs: list[tuple[float, float]],
    pickup_dropoff_legs: list[tuple[float, float]],
) -> list[tuple[str, int, str]]:
    """Interleave drive chunks with short ON for fuel, plus fixed pickup/dropoff ON."""
    items: list[tuple[str, int, str]] = []
    n_pu = len(drive_to_pickup_legs)
    for i, (_mi, ti) in enumerate(drive_to_pickup_legs):
        label = (
            "Drive to pickup"
            if n_pu == 1
            else f"Drive to pickup segment {i + 1}"
        )
        items.append(("drive", max(0, int(round(ti))), label))
        if i < n_pu - 1:
            items.append(("on", FUEL_ON_MIN, "Fuel (on duty, not driving)"))
    items.append(("on", PICKUP_ON_MIN, "Pickup (on duty, not driving)"))
    for i, (mi, ti) in enumerate(pickup_dropoff_legs):
        items.append(("drive", max(0, int(round(ti))), f"Haul segment {i + 1}"))
        if i < len(pickup_dropoff_legs) - 1:
            items.append(("on", FUEL_ON_MIN, "Fuel (on duty, not driving)"))
    items.append(("on", DROPOFF_ON_MIN, "Dropoff (on duty, not driving)"))
    return items


def merge_adjacent_events(
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not events:
        return []
    out = [events[0].copy()]
    for e in events[1:]:
        last = out[-1]
        if last["status"] == e["status"] and last["end"] == e["start"]:
            last["end"] = e["end"]
            if e["label"] != last["label"]:
                last["label"] = f"{last['label']}; {e['label']}"
        else:
            out.append(e.copy())
    return out


def events_to_legs(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    legs: list[dict[str, Any]] = []
    for e in events:
        dur = (e["end"] - e["start"]).total_seconds() / 60.0
        kind = (
            "rest"
            if e["status"] in ("OFF", "SB")
            else ("driving" if e["status"] == "D" else "on_duty")
        )
        legs.append(
            {
                "type": kind,
                "status": e["status"],
                "label": e["label"],
                "start": e["start"].isoformat(),
                "end": e["end"].isoformat(),
                "duration_minutes": round(dur, 1),
            }
        )
    return legs


def snap_minute_grid(m: float) -> int:
    return max(0, min(24 * 60, int(round(m / GRID_MIN) * GRID_MIN)))


def _local_minutes_from_midnight(dt: datetime, tz: ZoneInfo) -> float:
    """Minutes on the driver's wall clock since midnight — avoids DST timedelta bugs."""
    loc = dt.astimezone(tz)
    return (
        loc.hour * 60
        + loc.minute
        + loc.second / 60.0
        + loc.microsecond / 60_000_000.0
    )


def slice_eld_days(
    events: list[dict[str, Any]],
    tz_name: str,
) -> list[dict[str, Any]]:
    """Cut events on local midnights, then snap to the 15-minute ELD-style grid."""
    tz = ZoneInfo(tz_name)
    per_day: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for e in events:
        status: Status = e["status"]
        cur = e["start"]
        end_t = e["end"]
        if cur.tzinfo is None:
            cur = cur.replace(tzinfo=tz)
        if end_t.tzinfo is None:
            end_t = end_t.replace(tzinfo=tz)

        while cur < end_t:
            loc = cur.astimezone(tz)
            day_key = loc.date().isoformat()
            # Next calendar midnight in this zone (avoids timedelta across DST offset changes).
            next_mid = datetime.combine(
                loc.date() + timedelta(days=1), time.min, tzinfo=tz
            )
            chunk_end = min(end_t, next_mid)

            start_min = _local_minutes_from_midnight(cur, tz)
            if chunk_end >= end_t:
                # Event ends exactly at local midnight: end_t is on the *next* calendar day, so
                # minutes-from-midnight is 0; for the slice ending this day use end-of-day.
                if chunk_end == next_mid == end_t:
                    end_min = 24 * 60
                else:
                    end_min = _local_minutes_from_midnight(end_t, tz)
            else:
                end_min = 24 * 60

            sm = snap_minute_grid(start_min)
            em = snap_minute_grid(end_min)
            if em < sm:
                em = min(24 * 60, sm + GRID_MIN)
            if em > sm:
                per_day[day_key].append(
                    {
                        "status": status,
                        "start_minute": sm,
                        "end_minute": em,
                        "label": e.get("label", ""),
                    }
                )

            cur = chunk_end

    result: list[dict[str, Any]] = []
    for d in sorted(per_day.keys()):
        segs = sorted(per_day[d], key=lambda s: s["start_minute"])
        result.append({"date": d, "segments": segs})
    return result


def plan_trip_hos(
    distance_m_to_pickup: float,
    duration_s_to_pickup: float,
    distance_m_pickup_to_dropoff: float,
    duration_s_pickup_to_dropoff: float,
    trip_start: datetime,
    timezone: str,
    initial_cycle_used_hours: float,
    avg_mph: float = 55.0,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """(timeline legs, per-day grid, merged events). Odo starts at 0; fuel splits use miles."""
    from .routing import meters_to_miles

    miles_to_pu = meters_to_miles(distance_m_to_pickup)
    miles_pd = meters_to_miles(distance_m_pickup_to_dropoff)
    min_to_pu = max(0, int(round(duration_s_to_pickup / 60.0)))
    if min_to_pu == 0 and miles_to_pu > 0.5:
        min_to_pu = max(1, int(round((miles_to_pu / avg_mph) * 60)))
    min_pd = max(0, int(round(duration_s_pickup_to_dropoff / 60.0)))
    if min_pd == 0 and miles_pd > 0.5:
        min_pd = max(1, int(round((miles_pd / avg_mph) * 60)))

    if miles_to_pu > 0:
        drive_to_pu_chunks = split_leg_by_fuel(0.0, miles_to_pu, float(min_to_pu))
    else:
        drive_to_pu_chunks = []
    if not drive_to_pu_chunks and min_to_pu > 0:
        drive_to_pu_chunks = [(max(miles_to_pu, 0.0), float(min_to_pu))]

    odo_after_pu_leg = miles_to_pu
    fuel_chunks = split_leg_by_fuel(odo_after_pu_leg, miles_pd, float(min_pd))
    work = build_work_items(drive_to_pu_chunks, fuel_chunks)
    start_aware = trip_start
    if start_aware.tzinfo is None:
        start_aware = start_aware.replace(tzinfo=ZoneInfo(timezone))
    events = simulate_hos(work, start_aware, initial_cycle_used_hours)
    merged = merge_adjacent_events(events)
    legs = events_to_legs(merged)
    eld_days = slice_eld_days(merged, timezone)
    return legs, eld_days, merged


def trip_plan_hos_model() -> dict[str, Any]:
    """Shipped with every plan so the UI can show scope without hiding assumptions."""
    return {
        "summary": "Simplified property-carrying HOS planner.",
        "implemented_rules": [
            "11-hour driving limit per duty period after qualifying rest",
            "14-hour consecutive on-duty window from duty start (short OFF/SB counts; break does not pause)",
            "30-minute break from driving after 8 cumulative driving hours",
            "10+ consecutive hours off duty / sleeper resets 11-hour and 14-hour clocks",
            (
                "70 hours on duty (driving + on-duty not driving) in any rolling 8-day window "
                "ending at the current time; 34+ consecutive hours off clears the cycle in this planner"
            ),
            "Fuel stops every ~1,000 driven miles (planning assumption)",
        ],
        "grid_display_conventions": [
            "10-hour daily reset drawn as 7h sleeper berth + 3h off duty (valid §395.3(a)(1) pattern)",
            "Rest segments ≥7 consecutive hours shown as sleeper berth; shorter as off duty",
            "34-hour cycle restart shown entirely as off duty",
        ],
    }
