from datetime import datetime

from django.test import SimpleTestCase
from zoneinfo import ZoneInfo

from api.services.hos import (
    MIN_10H,
    MIN_11_DRIVE,
    MIN_30_BREAK,
    MIN_34H_RESTART,
    MIN_5H_SB,
    build_work_items,
    merge_adjacent_events,
    plan_trip_hos,
    simulate_hos,
    slice_eld_days,
    split_leg_by_fuel,
)


class FuelSplitTests(SimpleTestCase):
    def test_splits_at_1000_mile_marks(self):
        chunks = split_leg_by_fuel(200.0, 2500.0, 2500.0)
        miles = [c[0] for c in chunks]
        self.assertEqual(len(chunks), 3)
        self.assertAlmostEqual(sum(miles), 2500.0, places=3)
        self.assertAlmostEqual(miles[0], 800.0, places=3)


class HosSimulationTests(SimpleTestCase):
    def test_11_hour_limit_triggers_10h_rest(self):
        items = [("drive", MIN_11_DRIVE + 60, "long drive")]
        events = merge_adjacent_events(
            simulate_hos(
                items,
                datetime(2026, 1, 1, 6, 0, tzinfo=ZoneInfo("UTC")),
                0.0,
            )
        )
        statuses = [e["status"] for e in events]
        self.assertIn("D", statuses)
        self.assertIn("SB", statuses)
        total_drive = sum(
            (e["end"] - e["start"]).total_seconds() / 60.0
            for e in events
            if e["status"] == "D"
        )
        self.assertAlmostEqual(total_drive, MIN_11_DRIVE + 60, delta=1.0)
        sb_long = max(
            (e["end"] - e["start"]).total_seconds() / 60.0
            for e in events
            if e["status"] == "SB"
        )
        self.assertGreaterEqual(sb_long, MIN_10H - 1)

    def test_8_hour_drive_requires_30_min_break_before_more(self):
        items = [("drive", 8 * 60 + 60, "drive past 8h")]
        events = merge_adjacent_events(
            simulate_hos(
                items,
                datetime(2026, 1, 1, 6, 0, tzinfo=ZoneInfo("UTC")),
                0.0,
            )
        )
        off_blocks = [e for e in events if e["status"] == "OFF"]
        self.assertTrue(any((e["end"] - e["start"]).total_seconds() >= 29 * 60 for e in off_blocks))
        self.assertTrue(
            all(
                (e["end"] - e["start"]).total_seconds() / 60.0 < MIN_5H_SB
                for e in off_blocks
            )
        )

    def test_rest_five_hours_or_more_is_sleeper_berth(self):
        items = [("drive", MIN_11_DRIVE + 30, "long drive")]
        events = merge_adjacent_events(
            simulate_hos(
                items,
                datetime(2026, 1, 1, 6, 0, tzinfo=ZoneInfo("UTC")),
                0.0,
            )
        )
        for e in events:
            mins = (e["end"] - e["start"]).total_seconds() / 60.0
            if e["status"] == "SB":
                self.assertGreaterEqual(mins, MIN_5H_SB)
            elif e["status"] == "OFF":
                if "34-hour" in (e.get("label") or ""):
                    continue
                self.assertLess(mins, MIN_5H_SB)

    def test_34_hour_cycle_restart_is_off_duty_not_sleeper(self):
        events = merge_adjacent_events(
            simulate_hos(
                [("on", 60, "work after restart")],
                datetime(2026, 1, 1, 6, 0, tzinfo=ZoneInfo("UTC")),
                70.0,
            )
        )
        restart = [e for e in events if "34-hour" in (e.get("label") or "")]
        self.assertTrue(restart)
        self.assertEqual(restart[0]["status"], "OFF")
        self.assertAlmostEqual(
            (restart[0]["end"] - restart[0]["start"]).total_seconds() / 60.0,
            MIN_34H_RESTART,
            delta=1.0,
        )

    def test_on_duty_with_near_full_cycle_does_not_hang(self):
        """If cycle has <1 min left, int(chunk) must not spin forever (emit_on guard)."""
        items = [("on", 120, "Pickup (on duty, not driving)")]
        events = merge_adjacent_events(
            simulate_hos(
                items,
                datetime(2026, 1, 1, 6, 0, tzinfo=ZoneInfo("UTC")),
                69.99,
            )
        )
        self.assertTrue(events)
        on_minutes = sum(
            (e["end"] - e["start"]).total_seconds() / 60.0
            for e in events
            if e["status"] == "ON"
        )
        self.assertAlmostEqual(on_minutes, 120.0, delta=1.0)

    def test_plan_trip_hos_returns_eld_days(self):
        legs, eld_days, _ = plan_trip_hos(
            0.0,
            0.0,
            160934.0,
            8 * 3600.0,
            datetime(2026, 1, 1, 6, 0, tzinfo=ZoneInfo("America/Chicago")),
            "America/Chicago",
            0.0,
        )
        self.assertTrue(len(legs) > 0)
        self.assertTrue(len(eld_days) > 0)
        self.assertIn("segments", eld_days[0])

    def test_fourteen_hour_window_counts_elapsed_including_breaks(self):
        """30-minute break advances the 14-hour clock; only 630 min drive fits before 10h reset."""
        items = [("on", 3 * 60, "yard"), ("drive", 8 * 60 + 180, "linehaul")]
        events = merge_adjacent_events(
            simulate_hos(
                items,
                datetime(2026, 1, 1, 6, 0, tzinfo=ZoneInfo("UTC")),
                0.0,
            )
        )
        drive_before_first_10h = 0.0
        for e in events:
            if "10-hour off-duty reset" in (e.get("label") or ""):
                break
            if e["status"] == "D":
                drive_before_first_10h += (e["end"] - e["start"]).total_seconds() / 60.0
        self.assertAlmostEqual(drive_before_first_10h, 630.0, delta=2.0)
        total_drive = sum(
            (e["end"] - e["start"]).total_seconds() / 60.0
            for e in events
            if e["status"] == "D"
        )
        self.assertAlmostEqual(total_drive, 660.0, delta=2.0)

    def test_event_ending_at_local_midnight_fills_grid_to_end_of_day(self):
        tz = ZoneInfo("America/Chicago")
        start = datetime(2026, 1, 1, 18, 0, tzinfo=tz)
        end = datetime(2026, 1, 2, 0, 0, tzinfo=tz)
        merged = merge_adjacent_events(
            [{"status": "D", "start": start, "end": end, "label": "to midnight"}]
        )
        days = slice_eld_days(merged, "America/Chicago")
        day1 = next(d for d in days if d["date"] == "2026-01-01")
        last = max(day1["segments"], key=lambda s: s["end_minute"])
        self.assertEqual(last["end_minute"], 24 * 60)

    def test_long_drive_to_pickup_is_split_for_fuel(self):
        pu_chunks = split_leg_by_fuel(0.0, 2500.0, 2500.0)
        items = build_work_items(pu_chunks, [(100.0, 120.0)])
        drive_labels = [x[2] for x in items if x[0] == "drive"]
        self.assertGreater(len(drive_labels), 2)
        self.assertTrue(any("segment" in lab for lab in drive_labels))
        fuel_count = sum(1 for x in items if x[2] == "Fuel (on duty, not driving)")
        self.assertGreaterEqual(fuel_count, 2)
