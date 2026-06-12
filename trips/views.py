import logging
from datetime import datetime

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import TripCalculateSerializer
from .services.geocode_service import GeocodeError, geocode, search_locations
from .services.hos_service import build_schedule, events_to_stops
from .services.log_service import generate_daily_logs
from .services.marker_service import build_stop_markers
from .services.route_service import RouteError, build_full_route

logger = logging.getLogger(__name__)


class LocationSearchView(APIView):
    def get(self, request):
        query = request.query_params.get("q", "").strip()
        if len(query) < 2:
            return Response({"results": []})

        try:
            results = search_locations(query)
            return Response({"results": results})
        except GeocodeError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class TripCalculateView(APIView):
    def post(self, request):
        serializer = TripCalculateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        current_loc = data["current_location"]
        pickup_loc = data["pickup_location"]
        dropoff_loc = data["dropoff_location"]
        current_cycle_used = data["current_cycle_used"]

        try:
            current = geocode(current_loc)
            pickup = geocode(pickup_loc)
            dropoff = geocode(dropoff_loc)
        except GeocodeError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            legs, coordinates = build_full_route(current, pickup, dropoff)
        except RouteError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        try:
            locations = {
                "current": current["name"],
                "pickup": pickup["name"],
                "dropoff": dropoff["name"],
            }

            events, total_trip_hours = build_schedule(
                legs, current_cycle_used, locations
            )
            stops = events_to_stops(events)
            trip_start = events[0].time if events else datetime.now()
            daily_logs = generate_daily_logs(events, trip_start)

            total_distance = sum(leg["distance_miles"] for leg in legs)
            driving_hours = sum(leg["duration_hours"] for leg in legs)

            on_duty_from_trip = sum(
                e.duration_minutes / 60
                for e in events
                if e.status in ("driving", "on_duty_not_driving")
            )
            remaining_cycle = max(0, 70 - current_cycle_used - on_duty_from_trip)

            stop_markers = build_stop_markers(events, coordinates, total_distance)

            response_data = {
                "summary": {
                    "total_distance_miles": round(total_distance, 2),
                    "estimated_driving_hours": round(driving_hours, 2),
                    "total_trip_hours": round(total_trip_hours, 2),
                    "number_of_days": len(daily_logs),
                    "remaining_cycle_hours": round(remaining_cycle, 2),
                },
                "route": {
                    "coordinates": coordinates,
                    "legs": legs,
                },
                "stops": stops,
                "daily_logs": daily_logs,
                "markers": {
                    "current": {
                        "lat": current["lat"],
                        "lng": current["lng"],
                        "label": current["name"],
                    },
                    "pickup": {
                        "lat": pickup["lat"],
                        "lng": pickup["lng"],
                        "label": pickup["name"],
                    },
                    "dropoff": {
                        "lat": dropoff["lat"],
                        "lng": dropoff["lng"],
                        "label": dropoff["name"],
                    },
                    "stops": stop_markers,
                },
            }

            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as exc:
            logger.exception("Trip calculation failed")
            return Response(
                {"error": f"An unexpected error occurred: {exc}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
