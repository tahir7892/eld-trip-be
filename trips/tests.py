from datetime import datetime

from django.test import TestCase

from trips.services.hos_service import (
    BREAK_AFTER_DRIVING_HOURS,
    FUEL_INTERVAL_MILES,
    HOSState,
    build_schedule,
)
from trips.services.geocode_service import _format_search_label, search_locations
from trips.services.log_service import generate_daily_logs


class LocationSearchTests(TestCase):
    def test_search_returns_empty_for_short_query(self):
        self.assertEqual(search_locations("a"), [])

    def test_format_search_label_city_state(self):
        result = {
            "name": "Washington",
            "display_name": "Washington, District of Columbia, United States",
            "address": {"city": "Washington", "state": "District of Columbia"},
        }
        self.assertEqual(_format_search_label(result), "Washington, DC")


class HOSStateTests(TestCase):
    def test_shift_resets_after_ten_hour_break(self):
        start = datetime(2026, 6, 11, 8, 0)
        state = HOSState(current_time=start, cycle_used=0)
        state.ensure_on_duty("Test")
        state.add_event(660, "driving", "Route", miles=600)
        self.assertAlmostEqual(state.shift_driving_hours, 11.0)
        state.ten_hour_break("Rest area")
        self.assertEqual(state.shift_driving_hours, 0)
        self.assertFalse(state.on_duty)
        rest_events = [e for e in state.events if e.stop_type == "rest"]
        self.assertEqual(rest_events[0].status, "sleeper_berth")

    def test_sleeper_berth_does_not_count_against_cycle(self):
        start = datetime(2026, 6, 11, 8, 0)
        state = HOSState(current_time=start, cycle_used=10)
        state.add_event(600, "sleeper_berth", "Rest area")
        self.assertEqual(state.cycle_used, 10)

    def test_break_required_after_eight_hours_driving(self):
        start = datetime(2026, 6, 11, 8, 0)
        state = HOSState(current_time=start, cycle_used=0)
        state.ensure_on_duty("Test")
        state.add_event(int(BREAK_AFTER_DRIVING_HOURS * 60), "driving", "Route")
        self.assertTrue(state.needs_break())

    def test_off_duty_does_not_count_against_cycle(self):
        start = datetime(2026, 6, 11, 8, 0)
        state = HOSState(current_time=start, cycle_used=10)
        state.add_event(600, "off_duty", "Rest area")
        self.assertEqual(state.cycle_used, 10)

    def test_on_duty_counts_against_cycle(self):
        start = datetime(2026, 6, 11, 8, 0)
        state = HOSState(current_time=start, cycle_used=0)
        state.ensure_on_duty("Pickup")
        state.add_event(60, "on_duty_not_driving", "Pickup", stop_type="pickup")
        self.assertAlmostEqual(state.cycle_used, 1.0)

    def test_cycle_restart_when_insufficient_hours(self):
        start = datetime(2026, 6, 11, 8, 0)
        state = HOSState(current_time=start, cycle_used=68)
        state.ensure_cycle_capacity(5, "Location")
        restart_events = [e for e in state.events if e.stop_type == "cycle_restart"]
        self.assertEqual(len(restart_events), 1)
        self.assertEqual(state.cycle_used, 0)


class BuildScheduleTests(TestCase):
    def test_short_trip_produces_pickup_and_dropoff(self):
        legs = [
            {"distance_miles": 50, "duration_hours": 1},
            {"distance_miles": 100, "duration_hours": 2},
        ]
        locations = {
            "current": "New York, NY",
            "pickup": "Chicago, IL",
            "dropoff": "Dallas, TX",
        }
        events, _ = build_schedule(legs, 20, locations)
        stop_types = [e.stop_type for e in events if e.stop_type]
        self.assertIn("pickup", stop_types)
        self.assertIn("dropoff", stop_types)

    def test_pickup_dropoff_are_one_hour_on_duty(self):
        legs = [
            {"distance_miles": 50, "duration_hours": 1},
            {"distance_miles": 50, "duration_hours": 1},
        ]
        locations = {"current": "A", "pickup": "B", "dropoff": "C"}
        events, _ = build_schedule(legs, 5, locations)
        pickup = next(e for e in events if e.stop_type == "pickup")
        dropoff = next(e for e in events if e.stop_type == "dropoff")
        self.assertEqual(pickup.duration_minutes, 60)
        self.assertEqual(dropoff.duration_minutes, 60)
        self.assertEqual(pickup.status, "on_duty_not_driving")
        self.assertEqual(dropoff.status, "on_duty_not_driving")

    def test_long_trip_includes_rest_breaks(self):
        legs = [
            {"distance_miles": 500, "duration_hours": 9},
            {"distance_miles": 1200, "duration_hours": 22},
        ]
        locations = {
            "current": "New York, NY",
            "pickup": "Chicago, IL",
            "dropoff": "Dallas, TX",
        }
        events, _ = build_schedule(legs, 20, locations)
        rest_breaks = [e for e in events if e.stop_type == "rest_break"]
        ten_hour_rests = [e for e in events if e.stop_type == "rest"]
        self.assertTrue(len(rest_breaks) > 0 or len(ten_hour_rests) > 0)

    def test_fuel_stop_every_thousand_miles(self):
        legs = [
            {"distance_miles": 100, "duration_hours": 2},
            {"distance_miles": 2500, "duration_hours": 45},
        ]
        locations = {"current": "A", "pickup": "B", "dropoff": "C"}
        events, _ = build_schedule(legs, 10, locations)
        fuel_stops = [e for e in events if e.stop_type == "fuel"]
        self.assertGreaterEqual(len(fuel_stops), 2)
        for stop in fuel_stops:
            self.assertEqual(stop.duration_minutes, 30)
            self.assertEqual(stop.status, "on_duty_not_driving")

    def test_thirty_minute_break_after_eight_hours(self):
        legs = [
            {"distance_miles": 50, "duration_hours": 1},
            {"distance_miles": 600, "duration_hours": 11},
        ]
        locations = {"current": "A", "pickup": "B", "dropoff": "C"}
        events, _ = build_schedule(legs, 10, locations)
        rest_breaks = [e for e in events if e.stop_type == "rest_break"]
        self.assertGreater(len(rest_breaks), 0)
        self.assertEqual(rest_breaks[0].duration_minutes, 30)


class DailyLogTests(TestCase):
    def test_daily_logs_sum_to_twenty_four_hours(self):
        legs = [
            {"distance_miles": 100, "duration_hours": 2},
            {"distance_miles": 200, "duration_hours": 4},
        ]
        locations = {
            "current": "New York, NY",
            "pickup": "Chicago, IL",
            "dropoff": "Dallas, TX",
        }
        events, _ = build_schedule(legs, 10, locations)
        logs = generate_daily_logs(events, events[0].time)
        for log in logs:
            total = sum(log["totals"].values())
            self.assertAlmostEqual(total, 24.0, places=1)

    def test_multiple_logs_for_long_trip(self):
        legs = [
            {"distance_miles": 500, "duration_hours": 9},
            {"distance_miles": 1200, "duration_hours": 22},
        ]
        locations = {"current": "A", "pickup": "B", "dropoff": "C"}
        events, _ = build_schedule(legs, 10, locations)
        logs = generate_daily_logs(events, events[0].time)
        self.assertGreater(len(logs), 1)

    def test_log_has_required_fields(self):
        legs = [
            {"distance_miles": 50, "duration_hours": 1},
            {"distance_miles": 50, "duration_hours": 1},
        ]
        locations = {"current": "A", "pickup": "B", "dropoff": "C"}
        events, _ = build_schedule(legs, 5, locations)
        logs = generate_daily_logs(events, events[0].time)
        log = logs[0]
        for field in (
            "date", "total_miles", "driver_name", "carrier_name",
            "truck_number", "trailer_number", "shipping_document",
            "segments", "remarks", "totals", "day_number", "total_days",
            "day_summary", "formatted_date",
        ):
            self.assertIn(field, log)
        self.assertEqual(log["shipping_document"], "SHIP-001")

    def test_day_one_starts_with_off_duty_then_driving(self):
        legs = [
            {"distance_miles": 100, "duration_hours": 2},
            {"distance_miles": 100, "duration_hours": 2},
        ]
        locations = {"current": "A", "pickup": "B", "dropoff": "C"}
        events, _ = build_schedule(legs, 5, locations)
        logs = generate_daily_logs(events, events[0].time)
        day1 = logs[0]["segments"]
        self.assertEqual(day1[0]["status"], "off_duty")
        self.assertEqual(day1[0]["start"], "00:00")
        self.assertEqual(day1[0]["end"], "08:00")
        driving = [s for s in day1 if s["status"] == "driving"]
        self.assertTrue(len(driving) > 0)
        self.assertEqual(driving[0]["start"], "08:00")

    def test_long_trip_logs_include_sleeper_berth(self):
        legs = [
            {"distance_miles": 500, "duration_hours": 9},
            {"distance_miles": 1200, "duration_hours": 22},
        ]
        locations = {"current": "A", "pickup": "B", "dropoff": "C"}
        events, _ = build_schedule(legs, 10, locations)
        logs = generate_daily_logs(events, events[0].time)
        sleeper_hours = sum(log["totals"]["sleeper_berth"] for log in logs)
        self.assertGreater(sleeper_hours, 0)

    def test_each_day_has_unique_totals(self):
        legs = [
            {"distance_miles": 500, "duration_hours": 9},
            {"distance_miles": 1200, "duration_hours": 22},
        ]
        locations = {"current": "A", "pickup": "B", "dropoff": "C"}
        events, _ = build_schedule(legs, 10, locations)
        logs = generate_daily_logs(events, events[0].time)
        totals_set = {tuple(sorted(log["totals"].items())) for log in logs}
        self.assertGreater(len(totals_set), 1)
