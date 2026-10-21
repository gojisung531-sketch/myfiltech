import re

from rest_framework import serializers

from .models import Document, DocumentMetadata, MetadataSchema

FIELD_TYPES = ["str", "int", "float", "date", "bool", "list", "dimension", "grade", "json"]


class FieldDefSerializer(serializers.Serializer):
    key = serializers.RegexField(r"^[a-z][a-z0-9_]*$", max_length=100)
    label = serializers.CharField(max_length=100)
    type = serializers.ChoiceField(choices=FIELD_TYPES, default="str")
    unit = serializers.CharField(max_length=20, required=False, allow_blank=True)
    required = serializers.BooleanField(default=False)
    description = serializers.CharField(required=False, allow_blank=True)
    example = serializers.CharField(required=False, allow_blank=True)


class MetadataSchemaSerializer(serializers.ModelSerializer):
    document_count = serializers.IntegerField(source="documents.count", read_only=True)

    class Meta:
        model = MetadataSchema
        fields = [
            "id",
            "code",
            "name",
            "owner_type",
            "description",
            "filename_patterns",
            "fields",
            "target_model",
            "priority",
            "is_active",
            "document_count",
        ]

    def get_fields(self):
        # A declared attribute named `fields` would shadow Serializer.fields.
        fields = super().get_fields()
        fields["fields"] = FieldDefSerializer(many=True, required=False)
        return fields

    def validate_filename_patterns(self, value):
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise serializers.ValidationError("정규식 문자열 목록이어야 합니다.")
        for pattern in value:
            try:
                re.compile(pattern)
            except re.error as exc:
                raise serializers.ValidationError(f"잘못된 정규식 '{pattern}': {exc}") from exc
        return value

    def validate_fields(self, value):
        keys = [f["key"] for f in value]
        if len(keys) != len(set(keys)):
            raise serializers.ValidationError("필드 키가 중복되었습니다.")
        return value


class DocumentSerializer(serializers.ModelSerializer):
    display_name = serializers.CharField(read_only=True)
    category_code = serializers.CharField(source="category.code", read_only=True, default=None)
    category_name = serializers.CharField(source="category.name", read_only=True, default=None)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    has_file = serializers.SerializerMethodField()
    metadata_count = serializers.IntegerField(source="metadata.count", read_only=True)

    class Meta:
        model = Document
        fields = [
            "id",
            "title",
            "display_name",
            "original_filename",
            "file_format",
            "file_size",
            "has_file",
            "owner_type",
            "category",
            "category_code",
            "category_name",
            "category_confidence",
            "category_source",
            "status",
            "status_label",
            "error_message",
            "page_count",
            "metadata_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [f for f in fields if f not in ("title", "category")]

    def get_has_file(self, obj) -> bool:
        return bool(obj.file)


class DocumentUpdateSerializer(serializers.ModelSerializer):
    reextract = serializers.BooleanField(write_only=True, required=False, default=False)

    class Meta:
        model = Document
        fields = ["title", "category", "reextract"]

    def validate_category(self, value):
        if value is not None and value.owner_type != self.instance.owner_type:
            raise serializers.ValidationError(
                "문서 종류(회사 자료/입찰 첨부)에 맞지 않는 분류입니다."
            )
        return value


class TextDocumentSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255)
    source_text = serializers.CharField()
    owner_type = serializers.ChoiceField(choices=["COMPANY", "BID"])
    category = serializers.PrimaryKeyRelatedField(
        queryset=MetadataSchema.objects.all(), required=False, allow_null=True
    )


class DocumentMetadataSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentMetadata
        fields = [
            "id",
            "key",
            "label",
            "value",
            "raw_value",
            "unit",
            "source",
            "confidence",
            "evidence_page",
            "evidence_quote",
            "is_locked",
            "updated_at",
        ]
        read_only_fields = ["id", "source", "confidence", "updated_at"]
        extra_kwargs = {"key": {"required": True}}

    def validate_key(self, value):
        document = self.context["document"]
        clash = document.metadata.filter(key=value)
        if self.instance is not None:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError("같은 키의 메타데이터가 이미 있습니다.")
        return value
