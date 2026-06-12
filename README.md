# ELD Trip Planner — Backend

Django REST API for the ELD Trip Planner. Accepts trip inputs (current, pickup, and dropoff locations), geocodes them, calculates driving routes, builds an FMCSA Hours of Service (HOS) compliant schedule, and returns daily ELD log data for the frontend.

## Tech Stack

- Python 3.10+
- Django 5.x
- Django REST Framework
- django-cors-headers
- requests (Nominatim geocoding, OSRM routing)

External APIs (free, no API keys):

| Service   | Provider        | Purpose              |
|-----------|-----------------|----------------------|
| Geocoding | Nominatim (OSM) | Location → lat/lng   |
| Routing   | OSRM            | Driving route & legs |

## Project Structure

```
eld-trip-backend/
  config/                  # Django project settings, URLs, WSGI/ASGI
  trips/
    services/
      geocode_service.py   # Nominatim geocoding
      route_service.py     # OSRM routing (current → pickup → dropoff)
      hos_service.py       # HOS schedule engine
      log_service.py       # Daily ELD log sheet generation
    views.py               # TripCalculateView
    serializers.py         # Request validation
    tests.py               # HOS and log unit tests
  manage.py
  requirements.txt
```

## Setup

### Prerequisites

- Python 3.10+
- pip

### Install & Run

```bash
cd eld-trip-backend
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

The API runs at **http://localhost:8000**.

### CORS

The frontend dev server (`http://localhost:3000` and `http://localhost:5173`) is allowed in `config/settings.py`. Add your production frontend origin to `CORS_ALLOWED_ORIGINS` when deploying.

## API

### `POST /api/trips/calculate/`

Calculates a full trip: route, HOS schedule, stops, and daily logs.

**Request body:**

```json
{
  "current_location": "New York, NY",
  "pickup_location": "Chicago, IL",
  "dropoff_location": "Dallas, TX",
  "current_cycle_used": 20
}
```

| Field                | Type   | Description                                      |
|----------------------|--------|--------------------------------------------------|
| `current_location`   | string | Driver's current location (US addresses/cities)  |
| `pickup_location`    | string | Pickup location                                  |
| `dropoff_location`   | string | Final dropoff location                           |
| `current_cycle_used` | float  | Hours already used in the 70/8 cycle (0–70)       |

**Success response (200):**

```json
{
  "summary": {
    "total_distance_miles": 1542.5,
    "estimated_driving_hours": 28.0,
    "total_trip_hours": 72.5,
    "number_of_days": 4,
    "remaining_cycle_hours": 22.0
  },
  "route": {
    "coordinates": [[lng, lat], ...],
    "legs": [
      { "from": "...", "to": "...", "distance_miles": 790.0, "duration_hours": 14.4 }
    ]
  },
  "stops": [
    { "time": "2026-06-11T08:00:00", "type": "pickup", "location": "Chicago, IL", "duration_minutes": 60 }
  ],
  "daily_logs": [
    {
      "date": "2026-06-11",
      "segments": [...],
      "totals": { "off_duty": 10.0, "driving": 8.0, "on_duty_not_driving": 2.0 }
    }
  ],
  "markers": {
    "current": { "lat": 40.71, "lng": -74.01, "label": "New York, NY" },
    "pickup": { "lat": 41.88, "lng": -87.63, "label": "Chicago, IL" },
    "dropoff": { "lat": 32.78, "lng": -96.80, "label": "Dallas, TX" }
  }
}
```

**Errors:**

| Status | Cause                                              |
|--------|----------------------------------------------------|
| 400    | Invalid/missing fields, unknown location, cycle > 70 |
| 502    | OSRM routing failure                               |

### Admin

Django admin is available at **http://localhost:8000/admin/** after creating a superuser:

```bash
python manage.py createsuperuser
```

## HOS Assumptions

Models a **property-carrying CMV driver** under standard FMCSA rules:

| Rule                    | Value                          |
|-------------------------|--------------------------------|
| Cycle                   | 70 hours / 8 days              |
| Max driving per shift   | 11 hours                       |
| Driving window          | 14 hours after coming on duty  |
| Off-duty reset          | 10 consecutive hours           |
| Rest break              | 30 min after 8 driving hours   |
| Cycle restart           | 34 consecutive hours off duty  |
| Pickup / Dropoff        | 1 hour on-duty not driving each|
| Fuel stop               | Every 1,000 miles, 30 min on-duty |
| Average truck speed     | 55 mph (fallback if OSRM duration is unrealistic) |

**Not implemented:** Sleeper berth split, adverse driving conditions, short-haul exceptions.

Trips start at **8:00 AM** on the current day. Time from midnight to trip start is recorded as off-duty.

## Tests

```bash
source venv/bin/activate
python manage.py test trips
```

Tests cover HOS state transitions (shift resets, break rules, cycle restarts), schedule building, and daily log generation.

## Deployment Notes

- Set `DEBUG = False` and configure `SECRET_KEY` and `ALLOWED_HOSTS` via environment variables
- Run with gunicorn or uwsgi behind nginx
- Nominatim rate limit is ~1 request/second — consider caching geocode results in production
- Add retry/backoff for OSRM availability
- Update `CORS_ALLOWED_ORIGINS` with your production frontend domain

## Related

The React frontend lives in `../eld-trip-frontend`. See the root [README](../README.md) for full-stack setup and demo instructions.
