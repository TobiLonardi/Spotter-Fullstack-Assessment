from datetime import datetime

from django.test import SimpleTestCase
from zoneinfo import ZoneInfo

from api.services.hos import (
    MIN_10H,
    MIN_11_DRIVE,
    MIN_30_BREAK,
    MIN_34H_RESTART,
    MIN_5H_SB,
    merge_adjacent_events,
    plan_trip_hos,
    simulate_hos,
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
