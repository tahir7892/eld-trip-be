import requests

OSRM_BASE = "https://router.project-osrm.org/route/v1/driving"
METERS_TO_MILES = 0.000621371
AVG_TRUCK_SPEED_MPH = 55


class RouteError(Exception):
    pass


def _adjust_duration(distance_miles: float, duration_seconds: float) -> float:
    """Use OSRM duration but fall back to 55 mph average if unrealistic."""
    if duration_seconds <= 0:
        return distance_miles / AVG_TRUCK_SPEED_MPH

    osrm_speed = distance_miles / (duration_seconds / 3600) if duration_seconds else 0
    # If OSRM implies speed > 80 mph or < 25 mph for long distances, use truck average
    if osrm_speed > 80 or (distance_miles > 50 and osrm_speed < 25):
        return distance_miles / AVG_TRUCK_SPEED_MPH
    return duration_seconds / 3600


def get_route(from_point: dict, to_point: dict) -> dict:
    """Get driving route between two geocoded points via OSRM."""
    coords = f"{from_point['lng']},{from_point['lat']};{to_point['lng']},{to_point['lat']}"
    url = f"{OSRM_BASE}/{coords}"
    params = {"overview": "full", "geometries": "geojson"}

    try:
        response = requests.get(url, params=params, timeout=20)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        raise RouteError(f"Route service unavailable: {exc}") from exc

    if data.get("code") != "Ok" or not data.get("routes"):
        raise RouteError(
            f"Could not calculate route from {from_point['name']} to {to_point['name']}"
        )

    route = data["routes"][0]
    distance_miles = route["distance"] * METERS_TO_MILES
    duration_hours = _adjust_duration(distance_miles, route["duration"])

    geometry = route["geometry"]["coordinates"]
    coordinates = [[coord[1], coord[0]] for coord in geometry]

    return {
        "from": from_point["name"],
        "to": to_point["name"],
        "distance_miles": round(distance_miles, 2),
        "duration_hours": round(duration_hours, 2),
        "coordinates": coordinates,
    }


def build_full_route(
    current: dict, pickup: dict, dropoff: dict
) -> tuple[list[dict], list[list[float]]]:
    """Build route legs and combined coordinates."""
    leg1 = get_route(current, pickup)
    leg2 = get_route(pickup, dropoff)

    legs = [
        {
            "from": leg1["from"],
            "to": leg1["to"],
            "distance_miles": leg1["distance_miles"],
            "duration_hours": leg1["duration_hours"],
        },
        {
            "from": leg2["from"],
            "to": leg2["to"],
            "distance_miles": leg2["distance_miles"],
            "duration_hours": leg2["duration_hours"],
        },
    ]

    coordinates = leg1["coordinates"] + leg2["coordinates"][1:]
    return legs, coordinates
