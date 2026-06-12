from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

AVG_TRUCK_SPEED_MPH = 55
MAX_DRIVING_HOURS = 11
MAX_WINDOW_HOURS = 14
OFF_DUTY_RESET_HOURS = 10
BREAK_AFTER_DRIVING_HOURS = 8
BREAK_MINUTES = 30
FUEL_INTERVAL_MILES = 1000
FUEL_STOP_MINUTES = 30
PICKUP_MINUTES = 60
DROPOFF_MINUTES = 60
CYCLE_MAX_HOURS = 70
CYCLE_RESTART_HOURS = 34


@dataclass
class ScheduleEvent:
    time: datetime
    duration_minutes: int
    status: str
    location: str
    note: str = ""
    miles: float = 0
    stop_type: Optional[str] = None


@dataclass
class HOSState:
    current_time: datetime
    cycle_used: float
    shift_start: Optional[datetime] = None
    shift_driving_hours: float = 0
    driving_since_break: float = 0
    trip_miles: float = 0
    next_fuel_at: float = FUEL_INTERVAL_MILES
    on_duty: bool = False
    events: list = field(default_factory=list)

    def add_event(
        self,
        duration_minutes: int,
        status: str,
        location: str,
        note: str = "",
        miles: float = 0,
        stop_type: Optional[str] = None,
    ):
        if duration_minutes <= 0:
            return
        self.events.append(
            ScheduleEvent(
                time=self.current_time,
                duration_minutes=duration_minutes,
                status=status,
                location=location,
                note=note,
                miles=miles,
                stop_type=stop_type,
            )
        )
        hours = duration_minutes / 60
        if status in ("driving", "on_duty_not_driving"):
            if not self.on_duty:
                self.shift_start = self.current_time
                self.on_duty = True
            if status == "driving":
                self.shift_driving_hours += hours
                self.driving_since_break += hours
                self.trip_miles += miles
            if status in ("driving", "on_duty_not_driving"):
                self.cycle_used += hours
        elif status in ("off_duty", "sleeper_berth") and hours >= OFF_DUTY_RESET_HOURS:
            self._reset_shift()
        self.current_time += timedelta(minutes=duration_minutes)

    def _reset_shift(self):
        self.shift_start = None
        self.shift_driving_hours = 0
        self.driving_since_break = 0
        self.on_duty = False

    def cycle_restart(self, location: str):
        self.add_event(
            int(CYCLE_RESTART_HOURS * 60),
            "sleeper_berth",
            location,
            "34-hour sleeper berth cycle restart",
            stop_type="cycle_restart",
        )
        self.cycle_used = 0

    def ten_hour_break(self, location: str):
        self.add_event(
            int(OFF_DUTY_RESET_HOURS * 60),
            "sleeper_berth",
            location,
            "10-hour sleeper berth rest",
            stop_type="rest",
        )

    def thirty_min_break(self, location: str):
        self.add_event(
            BREAK_MINUTES,
            "off_duty",
            location,
            "30-minute rest break (required after 8 hours driving)",
            stop_type="rest_break",
        )
        self.driving_since_break = 0

    def fuel_stop(self, location: str):
        self.add_event(
            FUEL_STOP_MINUTES,
            "on_duty_not_driving",
            location,
            "Fuel stop",
            stop_type="fuel",
        )
        self.next_fuel_at += FUEL_INTERVAL_MILES

    def remaining_drive_hours(self) -> float:
        return max(0, MAX_DRIVING_HOURS - self.shift_driving_hours)

    def remaining_window_hours(self) -> float:
        if not self.on_duty or not self.shift_start:
            return MAX_WINDOW_HOURS
        elapsed = (self.current_time - self.shift_start).total_seconds() / 3600
        return max(0, MAX_WINDOW_HOURS - elapsed)

    def max_drive_chunk_hours(self) -> float:
        return min(self.remaining_drive_hours(), self.remaining_window_hours())

    def needs_break(self) -> bool:
        return self.driving_since_break >= BREAK_AFTER_DRIVING_HOURS

    def needs_fuel(self) -> bool:
        return self.trip_miles >= self.next_fuel_at

    def ensure_cycle_capacity(self, needed_hours: float, location: str):
        remaining = CYCLE_MAX_HOURS - self.cycle_used
        if needed_hours > remaining:
            self.cycle_restart(location)

    def ensure_on_duty(self, location: str):
        if not self.on_duty:
            self.shift_start = self.current_time
            self.on_duty = True


def _trip_start_time() -> datetime:
    now = datetime.now().replace(second=0, microsecond=0)
    return now.replace(hour=8, minute=0)


def _drive_leg(
    state: HOSState,
    distance_miles: float,
    duration_hours: float,
    location_label: str,
) -> float:
    """Drive a route leg respecting HOS rules. Returns miles driven."""
    miles_remaining = distance_miles
    hours_remaining = duration_hours
    miles_per_hour = (
        distance_miles / duration_hours if duration_hours > 0 else AVG_TRUCK_SPEED_MPH
    )

    while miles_remaining > 0.01 and hours_remaining > 0.001:
        if state.needs_break():
            state.thirty_min_break(location_label)

        if state.needs_fuel():
            state.fuel_stop(location_label)

        if state.max_drive_chunk_hours() <= 0.01:
            state.ten_hour_break(location_label)
            continue

        chunk_hours = min(
            state.max_drive_chunk_hours(),
            hours_remaining,
            miles_remaining / miles_per_hour,
        )

        if state.driving_since_break + chunk_hours > BREAK_AFTER_DRIVING_HOURS:
            chunk_hours = max(
                0, BREAK_AFTER_DRIVING_HOURS - state.driving_since_break
            )
            if chunk_hours < 0.01:
                state.thirty_min_break(location_label)
                continue

        chunk_miles = chunk_hours * miles_per_hour
        state.ensure_cycle_capacity(chunk_hours, location_label)

        state.add_event(
            int(round(chunk_hours * 60)),
            "driving",
            location_label,
            "Driving",
            miles=round(chunk_miles, 2),
        )
        miles_remaining -= chunk_miles
        hours_remaining -= chunk_hours

    return distance_miles - miles_remaining


def build_schedule(
    legs: list[dict],
    current_cycle_used: float,
    locations: dict,
) -> tuple[list[ScheduleEvent], float]:
    """
    Build HOS-compliant schedule for full trip.
    Returns (events, total_trip_hours).
    """
    start = _trip_start_time()
    midnight = start.replace(hour=0, minute=0, second=0, microsecond=0)
    state = HOSState(current_time=midnight, cycle_used=current_cycle_used)

    if start > midnight:
        state.add_event(
            int((start - midnight).total_seconds() / 60),
            "off_duty",
            locations["current"],
            "Off duty before trip start",
        )

    leg1, leg2 = legs[0], legs[1]

    _drive_leg(
        state,
        leg1["distance_miles"],
        leg1["duration_hours"],
        f"En route: {locations['current']} to {locations['pickup']}",
    )

    state.ensure_on_duty(locations["pickup"])
    state.ensure_cycle_capacity(PICKUP_MINUTES / 60, locations["pickup"])
    state.add_event(
        PICKUP_MINUTES,
        "on_duty_not_driving",
        locations["pickup"],
        "Pickup / loading",
        stop_type="pickup",
    )

    _drive_leg(
        state,
        leg2["distance_miles"],
        leg2["duration_hours"],
        f"En route: {locations['pickup']} to {locations['dropoff']}",
    )

    state.ensure_on_duty(locations["dropoff"])
    state.ensure_cycle_capacity(DROPOFF_MINUTES / 60, locations["dropoff"])
    state.add_event(
        DROPOFF_MINUTES,
        "on_duty_not_driving",
        locations["dropoff"],
        "Dropoff / unloading",
        stop_type="dropoff",
    )

    end_of_day = state.current_time.replace(
        hour=23, minute=59, second=59, microsecond=0
    )
    if state.current_time.date() == end_of_day.date():
        remaining = (
            state.current_time.replace(hour=23, minute=59) - state.current_time
        ).total_seconds() / 60
        if remaining > 0:
            state.add_event(
                int(remaining),
                "sleeper_berth",
                locations["dropoff"],
                "Sleeper berth — end of day",
            )

    total_hours = (state.current_time - midnight).total_seconds() / 3600
    return state.events, total_hours


def events_to_stops(events: list[ScheduleEvent]) -> list[dict]:
    """Convert schedule events to API stops format."""
    stops = []
    for event in events:
        if event.stop_type or event.status == "driving":
            stop = {
                "type": event.stop_type or "driving",
                "location": event.location,
                "time": event.time.isoformat(),
                "duration_minutes": event.duration_minutes,
                "duty_status": event.status,
            }
            if event.note:
                stop["note"] = event.note
            stops.append(stop)
    return stops
