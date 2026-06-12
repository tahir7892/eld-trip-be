from datetime import datetime, timedelta

STATUS_KEYS = {
    "off_duty": "off_duty",
    "sleeper_berth": "sleeper_berth",
    "driving": "driving",
    "on_duty_not_driving": "on_duty_not_driving",
}

STATUS_LABELS = {
    "off_duty": "Off duty",
    "sleeper_berth": "Sleeper berth",
    "driving": "Driving",
    "on_duty_not_driving": "On duty (not driving)",
}

CARRIER_NAME = "Demo Carrier"
DRIVER_NAME = "Demo Driver"
TRUCK_NUMBER = "TRUCK-001"
TRAILER_NUMBER = "TRL-001"
SHIPPING_DOCUMENT = "SHIP-001"


def _minutes_to_time(minutes: int) -> str:
    minutes = minutes % (24 * 60)
    h, m = divmod(minutes, 60)
    return f"{h:02d}:{m:02d}"


def _time_to_minutes(time_str: str) -> int:
    h, m = map(int, time_str.split(":"))
    return h * 60 + m


def _empty_totals() -> dict:
    return {
        "off_duty": 0.0,
        "sleeper_berth": 0.0,
        "driving": 0.0,
        "on_duty_not_driving": 0.0,
    }


def _round_hours(minutes: float) -> float:
    return round(minutes / 60, 2)


def _miles_by_day(events) -> dict[str, float]:
    """Attribute driving miles to each calendar day, including midnight splits."""
    miles_by_day: dict[str, float] = {}
    for event in events:
        if event.miles <= 0:
            continue
        event_end = event.time + timedelta(minutes=event.duration_minutes)
        total_seconds = event.duration_minutes * 60
        if total_seconds <= 0:
            continue
        day = event.time.replace(hour=0, minute=0, second=0, microsecond=0)
        while day < event_end:
            day_end = day + timedelta(days=1)
            overlap_start = max(event.time, day)
            overlap_end = min(event_end, day_end)
            if overlap_start < overlap_end:
                fraction = (overlap_end - overlap_start).total_seconds() / total_seconds
                date_str = day.strftime("%Y-%m-%d")
                miles_by_day[date_str] = miles_by_day.get(date_str, 0) + event.miles * fraction
            day = day_end
    return miles_by_day


def _build_remarks(segments: list[dict]) -> list[dict]:
    """One remark per duty-status change on the log sheet."""
    remarks = []
    prev_status = None
    for seg in segments:
        status = seg["status"]
        if status == prev_status:
            continue
        prev_status = status
        note = seg.get("note") or STATUS_LABELS.get(status, status)
        remarks.append(
            {
                "time": seg["start"],
                "location": seg.get("location") or "—",
                "note": note,
            }
        )
    return remarks


def _day_summary(totals: dict, total_miles: float) -> str:
    driving = totals.get("driving", 0)
    on_duty = totals.get("on_duty_not_driving", 0)
    off = totals.get("off_duty", 0)
    sleeper = totals.get("sleeper_berth", 0)
    if driving >= 10:
        rest = f", {sleeper:.1f}h sleeper" if sleeper >= 4 else ""
        return f"Long haul — {driving:.1f} hrs driving, {total_miles:.0f} mi{rest}"
    if on_duty >= 1 and driving >= 4:
        return f"Mixed duty — pickup/dropoff + {driving:.1f} hrs driving"
    if on_duty >= 1:
        return f"On-duty day — {on_duty:.1f} hrs not driving"
    if driving > 0:
        return f"Driving — {driving:.1f} hrs, {total_miles:.0f} mi"
    if sleeper >= 8:
        return f"Sleeper berth rest — {sleeper:.1f} hrs"
    if off >= 20:
        return "Off-duty rest day"
    return "Light duty day"


def generate_daily_logs(events, trip_start: datetime) -> list[dict]:
    """Split HOS schedule events into daily ELD log sheets."""
    if not events:
        return []

    timeline: list[tuple[datetime, datetime, str, str, str]] = []
    for event in events:
        end = event.time + timedelta(minutes=event.duration_minutes)
        timeline.append(
            (event.time, end, event.status, event.location, event.note or "")
        )

    first_day = timeline[0][0].replace(hour=0, minute=0, second=0, microsecond=0)
    last_end = timeline[-1][1]
    last_day = last_end.replace(hour=0, minute=0, second=0, microsecond=0)
    miles_by_day = _miles_by_day(events)

    daily_logs = []
    day = first_day

    while day <= last_day:
        day_end = day + timedelta(days=1)
        segments = []
        totals_minutes = _empty_totals()

        for start, end, status, location, note in timeline:
            seg_start = max(start, day)
            seg_end = min(end, day_end)
            if seg_start >= seg_end:
                continue

            start_min = int((seg_start - day).total_seconds() / 60)
            end_min = int((seg_end - day).total_seconds() / 60)

            key = STATUS_KEYS.get(status, "off_duty")
            totals_minutes[key] += end_min - start_min

            seg = {
                "start": _minutes_to_time(start_min),
                "end": _minutes_to_time(end_min) if end_min < 24 * 60 else "23:59",
                "status": status,
                "location": location,
            }
            if note:
                seg["note"] = note
            segments.append(seg)

        segments = _fill_gaps(segments, day)
        totals = _reconcile_totals({}, segments)
        date_str = day.strftime("%Y-%m-%d")
        total_miles = round(miles_by_day.get(date_str, 0), 1)
        remarks = _build_remarks(segments)

        daily_logs.append(
            {
                "date": date_str,
                "formatted_date": day.strftime("%A, %B %d, %Y"),
                "total_miles": total_miles,
                "carrier_name": CARRIER_NAME,
                "driver_name": DRIVER_NAME,
                "truck_number": TRUCK_NUMBER,
                "trailer_number": TRAILER_NUMBER,
                "shipping_document": SHIPPING_DOCUMENT,
                "remarks": remarks,
                "segments": segments,
                "totals": totals,
                "day_summary": _day_summary(totals, total_miles),
            }
        )
        day = day_end

    # Drop trailing all-off-duty days with no trip activity
    while daily_logs:
        last = daily_logs[-1]
        if (
            last["total_miles"] == 0
            and last["totals"]["driving"] == 0
            and last["totals"]["on_duty_not_driving"] == 0
        ):
            daily_logs.pop()
        else:
            break

    total_days = len(daily_logs)
    for i, log in enumerate(daily_logs, start=1):
        log["day_number"] = i
        log["total_days"] = total_days

    return daily_logs


def _fill_gaps(segments: list[dict], day: datetime) -> list[dict]:
    """Ensure 24-hour coverage, filling gaps with off-duty."""
    if not segments:
        return [
            {
                "start": "00:00",
                "end": "23:59",
                "status": "off_duty",
                "location": "",
            }
        ]

    segments = sorted(segments, key=lambda s: _time_to_minutes(s["start"]))
    filled = []
    cursor = 0

    for seg in segments:
        seg_start = _time_to_minutes(seg["start"])
        seg_end = _time_to_minutes(seg["end"])
        if seg_end <= seg_start:
            seg_end = 24 * 60

        if seg_start > cursor:
            filled.append(
                {
                    "start": _minutes_to_time(cursor),
                    "end": _minutes_to_time(seg_start),
                    "status": "off_duty",
                    "location": "",
                }
            )
        filled.append(seg)
        cursor = max(cursor, seg_end)

    if cursor < 24 * 60 - 1:
        filled.append(
            {
                "start": _minutes_to_time(cursor),
                "end": "23:59",
                "status": "off_duty",
                "location": "",
            }
        )

    return _merge_adjacent(filled)


def _merge_adjacent(segments: list[dict]) -> list[dict]:
    if not segments:
        return segments
    merged = [segments[0]]
    for seg in segments[1:]:
        prev = merged[-1]
        if (
            prev["status"] == seg["status"]
            and prev.get("location") == seg.get("location")
            and prev["end"] == seg["start"]
        ):
            prev["end"] = seg["end"]
            if seg.get("note") and not prev.get("note"):
                prev["note"] = seg["note"]
        else:
            merged.append(seg)
    return merged


def _reconcile_totals(_totals: dict, segments: list[dict]) -> dict:
    """Recalculate totals from segments to ensure they sum to ~24 hours."""
    recalc = _empty_totals()
    for seg in segments:
        start = _time_to_minutes(seg["start"])
        end = _time_to_minutes(seg["end"])
        if end <= start:
            end = 24 * 60
        key = STATUS_KEYS.get(seg["status"], "off_duty")
        recalc[key] += end - start

    return {k: _round_hours(v) for k, v in recalc.items()}
