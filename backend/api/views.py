from datetime import datetime

from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from zoneinfo import ZoneInfo

from .serializers import TripPlanRequestSerializer
from .services.geocode import resolve_location
from .services.hos import plan_trip_hos, trip_plan_hos_model
from .services.routing import get_directions, meters_to_miles


class HealthView(APIView):
    """Simple JSON endpoint to verify the API and CORS."""

    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response(
            {
                "status": "ok",
                "message": "Django API is running.",
            }
        )


@method_decorator(csrf_exempt, name='dispatch')
class TripPlanView(APIView):
    """
    Geocode locations, compute route (ORS), simulate HOS, return map + ELD-style days.
    Planning aid only — not certified for regulatory compliance.
    """

    authentication_classes = []
    permission_classes = []

    def post(self, request):
        ser = TripPlanRequestSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
        data = ser.validated_data
        tz_name = data["timezone"]

        try:
            cur = resolve_location(data["current_location"])
            pu = resolve_location(data["pickup_location"])
            do = resolve_location(data["dropoff_location"])
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response(
                {"detail": f"Geocoding failed: {e!s}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        lonlat = [
            [cur[1], cur[0]],
            [pu[1], pu[0]],
            [do[1], do[0]],
        ]
        try:
            route = get_directions(lonlat)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response(
                {"detail": f"Routing failed: {e!s}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        segs = route.get("segments") or []
        if len(segs) >= 2:
            d0_m = float(segs[0].get("distance_m", 0))
            t0_s = float(segs[0].get("duration_s", 0))
            d1_m = float(segs[1].get("distance_m", 0))
            t1_s = float(segs[1].get("duration_s", 0))
        elif len(segs) == 1:
            d0_m, t0_s = 0.0, 0.0
            d1_m = float(segs[0].get("distance_m", route["distance_m"]))
            t1_s = float(segs[0].get("duration_s", route["duration_s"]))
        else:
            d0_m, t0_s = 0.0, 0.0
            d1_m = float(route["distance_m"])
            t1_s = float(route["duration_s"])

        trip_start = data.get("trip_start")
        if trip_start is None:
            trip_start = datetime.now(tz=ZoneInfo(tz_name))
        elif trip_start.tzinfo is None:
            trip_start = trip_start.replace(tzinfo=ZoneInfo(tz_name))

        legs, eld_days, _merged = plan_trip_hos(
            d0_m,
            t0_s,
            d1_m,
            t1_s,
            trip_start,
            tz_name,
            data["current_cycle_used_hours"],
        )

        coords = route["coordinates"]
        line_latlng = [[c[1], c[0]] for c in coords]

        total_mi = meters_to_miles(float(route["distance_m"]))
        stops = [
            {"id": "current", "label": "Current", "lat": cur[0], "lng": cur[1]},
            {"id": "pickup", "label": "Pickup", "lat": pu[0], "lng": pu[1]},
            {"id": "dropoff", "label": "Dropoff", "lat": do[0], "lng": do[1]},
        ]

        return Response(
            {
                "disclaimer": "This output is a planning aid only and is not an FMCSA-certified ELD.",
                "hos_model": trip_plan_hos_model(),
                "route": {
                    "type": "LineString",
                    "coordinates_latlng": line_latlng,
                    "distance_miles": round(total_mi, 1),
                    "duration_minutes": int(round(float(route["duration_s"]) / 60.0)),
                },
                "stops": stops,
                "legs": legs,
                "eld_days": eld_days,
            }
        )
