from rest_framework import serializers


class TripPlanRequestSerializer(serializers.Serializer):
    """Matches what the React form posts; locations stay JSONField on purpose."""

    current_location = serializers.JSONField()
    pickup_location = serializers.JSONField()
    dropoff_location = serializers.JSONField()
    current_cycle_used_hours = serializers.FloatField(min_value=0, max_value=70)
    trip_start = serializers.DateTimeField(required=False, allow_null=True)
    timezone = serializers.CharField(required=False, default="America/Chicago")

    def validate_timezone(self, value: str) -> str:
        try:
            from zoneinfo import ZoneInfo

            ZoneInfo(value.strip())
        except Exception as exc:
            raise serializers.ValidationError(f"Invalid IANA timezone: {value}") from exc
        return value.strip()
