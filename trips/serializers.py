from rest_framework import serializers


class TripCalculateSerializer(serializers.Serializer):
    current_location = serializers.CharField(max_length=255)
    pickup_location = serializers.CharField(max_length=255)
    dropoff_location = serializers.CharField(max_length=255)
    current_cycle_used = serializers.FloatField(min_value=0, max_value=70)

    def validate_current_location(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Current location is required.")
        return value.strip()

    def validate_pickup_location(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Pickup location is required.")
        return value.strip()

    def validate_dropoff_location(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Dropoff location is required.")
        return value.strip()

    def validate_current_cycle_used(self, value):
        if value < 0:
            raise serializers.ValidationError("Current cycle used cannot be negative.")
        if value > 70:
            raise serializers.ValidationError(
                "Current cycle used cannot exceed 70 hours."
            )
        return value
