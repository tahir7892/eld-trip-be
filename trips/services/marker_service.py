"""Interpolate fuel/rest stop positions along the route polyline."""


def interpolate_along_route(
    coordinates: list[list[float]], fraction: float
) -> list[float] | None:
    if not coordinates:
        return None
    fraction = max(0.0, min(1.0, fraction))
    if fraction <= 0:
        return coordinates[0]
    if fraction >= 1:
        return coordinates[-1]

    idx = fraction * (len(coordinates) - 1)
    i = int(idx)
    t = idx - i
    if i >= len(coordinates) - 1:
        return coordinates[-1]

    lat = coordinates[i][0] + t * (coordinates[i + 1][0] - coordinates[i][0])
    lng = coordinates[i][1] + t * (coordinates[i + 1][1] - coordinates[i][1])
    return [round(lat, 6), round(lng, 6)]


def build_stop_markers(events, coordinates: list, total_distance_miles: float) -> list[dict]:
    """Place fuel and rest stops along the route based on cumulative driving miles."""
    markers = []
    cumulative_miles = 0.0

    for event in events:
        if event.status == "driving":
            cumulative_miles += event.miles

        if event.stop_type in ("fuel", "rest", "rest_break", "cycle_restart"):
            fraction = (
                cumulative_miles / total_distance_miles
                if total_distance_miles > 0
                else 0.5
            )
            pos = interpolate_along_route(coordinates, min(0.98, fraction))
            if pos:
                markers.append(
                    {
                        "type": event.stop_type,
                        "lat": pos[0],
                        "lng": pos[1],
                        "label": event.note or event.stop_type,
                        "location": event.location,
                        "time": event.time.isoformat(),
                    }
                )

    return markers
