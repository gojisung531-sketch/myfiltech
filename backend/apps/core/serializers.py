from rest_framework import serializers

from .models import Job


class JobSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Job
        fields = [
            "id",
            "type",
            "status",
            "status_label",
            "target_type",
            "target_id",
            "payload",
            "progress",
            "message",
            "result",
            "error",
            "attempts",
            "created_by",
            "created_at",
            "started_at",
            "finished_at",
        ]
        read_only_fields = fields
