from rest_framework import serializers

from apps.core.freshness import reader_for

from .models import DraftDocument


def _name(user) -> str | None:
    return (user.display_name or user.username) if user else None


class DraftMetaSerializer(serializers.ModelSerializer):
    freshness = serializers.SerializerMethodField()

    def get_freshness(self, obj):
        return reader_for(self.context).result(obj)

    doc_type_label = serializers.CharField(source="get_doc_type_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    updated_by_name = serializers.SerializerMethodField()

    class Meta:
        model = DraftDocument
        fields = [
            "id",
            "doc_type",
            "doc_type_label",
            "title",
            "status",
            "status_label",
            "version",
            "generated_by",
            "is_modified",
            "used_llm",
            "updated_by_name",
            "created_at",
            "updated_at",
            "freshness",
        ]

    def get_updated_by_name(self, obj) -> str | None:
        return _name(obj.updated_by)


class DraftSerializer(DraftMetaSerializer):
    class Meta(DraftMetaSerializer.Meta):
        fields = [*DraftMetaSerializer.Meta.fields, "content"]


class DraftSaveSerializer(serializers.Serializer):
    version = serializers.IntegerField(required=False)
    content = serializers.JSONField(required=False)
    status = serializers.ChoiceField(choices=DraftDocument.Status.choices, required=False)
    title = serializers.CharField(required=False, max_length=300)
