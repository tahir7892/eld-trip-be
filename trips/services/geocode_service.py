import requests

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "ELDTripPlanner/1.0 (fcsm-driver-assessment)"


class GeocodeError(Exception):
    pass


US_STATE_ABBREV = {
    "Alabama": "AL",
    "Alaska": "AK",
    "Arizona": "AZ",
    "Arkansas": "AR",
    "California": "CA",
    "Colorado": "CO",
    "Connecticut": "CT",
    "Delaware": "DE",
    "District of Columbia": "DC",
    "Florida": "FL",
    "Georgia": "GA",
    "Hawaii": "HI",
    "Idaho": "ID",
    "Illinois": "IL",
    "Indiana": "IN",
    "Iowa": "IA",
    "Kansas": "KS",
    "Kentucky": "KY",
    "Louisiana": "LA",
    "Maine": "ME",
    "Maryland": "MD",
    "Massachusetts": "MA",
    "Michigan": "MI",
    "Minnesota": "MN",
    "Mississippi": "MS",
    "Missouri": "MO",
    "Montana": "MT",
    "Nebraska": "NE",
    "Nevada": "NV",
    "New Hampshire": "NH",
    "New Jersey": "NJ",
    "New Mexico": "NM",
    "New York": "NY",
    "North Carolina": "NC",
    "North Dakota": "ND",
    "Ohio": "OH",
    "Oklahoma": "OK",
    "Oregon": "OR",
    "Pennsylvania": "PA",
    "Rhode Island": "RI",
    "South Carolina": "SC",
    "South Dakota": "SD",
    "Tennessee": "TN",
    "Texas": "TX",
    "Utah": "UT",
    "Vermont": "VT",
    "Virginia": "VA",
    "Washington": "WA",
    "West Virginia": "WV",
    "Wisconsin": "WI",
    "Wyoming": "WY",
}


def _format_search_label(result: dict) -> str:
    address = result.get("address") or {}
    place = (
        address.get("city")
        or address.get("town")
        or address.get("village")
        or address.get("hamlet")
        or address.get("municipality")
        or address.get("county")
        or result.get("name")
    )
    state = address.get("state", "")
    state_code = US_STATE_ABBREV.get(state, state)
    if place and state_code:
        return f"{place}, {state_code}"
    display = result.get("display_name", "")
    parts = [part.strip() for part in display.split(",") if part.strip()]
    if len(parts) >= 2:
        return f"{parts[0]}, {parts[1]}"
    return display or place or "Unknown location"


def search_locations(query: str, limit: int = 6) -> list[dict]:
    """Return US location suggestions for autocomplete."""
    if not query or len(query.strip()) < 2:
        return []

    params = {
        "q": query.strip(),
        "format": "json",
        "limit": limit,
        "countrycodes": "us",
        "addressdetails": 1,
    }
    headers = {"User-Agent": USER_AGENT}

    try:
        response = requests.get(
            NOMINATIM_URL, params=params, headers=headers, timeout=10
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise GeocodeError(f"Location search unavailable: {exc}") from exc

    results = response.json()
    suggestions = []
    seen_labels = set()

    for result in results:
        label = _format_search_label(result)
        key = label.lower()
        if key in seen_labels:
            continue
        seen_labels.add(key)
        suggestions.append(
            {
                "label": label,
                "display_name": result.get("display_name", label),
                "lat": float(result["lat"]),
                "lng": float(result["lon"]),
            }
        )

    return suggestions


def geocode(location: str) -> dict:
    """Geocode a location string using Nominatim OpenStreetMap."""
    if not location or not location.strip():
        raise GeocodeError("Location cannot be empty.")

    params = {
        "q": location.strip(),
        "format": "json",
        "limit": 1,
        "countrycodes": "us",
    }
    headers = {"User-Agent": USER_AGENT}

    try:
        response = requests.get(
            NOMINATIM_URL, params=params, headers=headers, timeout=15
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise GeocodeError(f"Geocoding service unavailable: {exc}") from exc

    results = response.json()
    if not results:
        raise GeocodeError(f"Could not find location: {location}")

    result = results[0]
    return {
        "name": location.strip(),
        "lat": float(result["lat"]),
        "lng": float(result["lon"]),
        "display_name": result.get("display_name", location),
    }
