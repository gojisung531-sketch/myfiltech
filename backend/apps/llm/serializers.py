from rest_framework import serializers

from .models import (
    LLMCallLog,
    LLMModelOption,
    LLMProviderConfig,
    LLMSettings,
    PromptTemplate,
    Provider,
)
from .prompts import check_syntax
from .schemas import schema_error


class ProviderConfigSerializer(serializers.ModelSerializer):
    """Never exposes the API key — only whether one is stored and its masked tail."""

    label = serializers.CharField(source="get_provider_display", read_only=True)
    has_api_key = serializers.BooleanField(read_only=True)
    api_key_masked = serializers.CharField(read_only=True)

    class Meta:
        model = LLMProviderConfig
        fields = [
            "provider",
            "label",
            "has_api_key",
            "api_key_masked",
            "base_url",
            "is_enabled",
            "last_verified_at",
            "last_verify_ok",
            "last_verify_error",
        ]
        read_only_fields = fields


class ProviderConfigUpdateSerializer(serializers.Serializer):
    api_key = serializers.CharField(required=False, allow_blank=True, trim_whitespace=True)
    base_url = serializers.CharField(required=False, allow_blank=True, max_length=255)
    is_enabled = serializers.BooleanField(required=False)

    def validate_base_url(self, value):
        if value and not value.startswith(("http://", "https://")):
            raise serializers.ValidationError("http:// 또는 https:// 로 시작해야 합니다.")
        return value


class ModelOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = LLMModelOption
        fields = [
            "id",
            "provider",
            "model_id",
            "display_name",
            "supports_pdf_input",
            "max_output_tokens",
            "is_default",
            "is_active",
            "order",
        ]


class LLMSettingsSerializer(serializers.ModelSerializer):
    active_model_id = serializers.PrimaryKeyRelatedField(
        source="active_model",
        queryset=LLMModelOption.objects.all(),
        allow_null=True,
        required=False,
    )
    active_provider = serializers.ChoiceField(choices=Provider.choices, required=False)
    temperature = serializers.FloatField(min_value=0, max_value=2, required=False)
    max_output_tokens = serializers.IntegerField(min_value=1, required=False)
    timeout_sec = serializers.IntegerField(min_value=5, max_value=3600, required=False)
    max_retries = serializers.IntegerField(min_value=0, max_value=10, required=False)

    class Meta:
        model = LLMSettings
        fields = [
            "active_provider",
            "active_model_id",
            "temperature",
            "max_output_tokens",
            "timeout_sec",
            "max_retries",
            "json_mode",
            "per_task_overrides",
        ]

    def validate_per_task_overrides(self, value):
        if not isinstance(value, dict) or not all(isinstance(v, dict) for v in value.values()):
            raise serializers.ValidationError(
                '{"작업키": {"temperature": 0.0, ...}} 형식의 JSON 객체여야 합니다.'
            )
        return value

    def validate(self, attrs):
        instance = self.instance
        provider = attrs.get("active_provider", instance.active_provider if instance else None)
        model = attrs.get("active_model", instance.active_model if instance else None)
        provider_changed = instance is not None and provider != instance.active_provider
        if provider_changed and "active_model" not in attrs:
            model = (
                LLMModelOption.objects.filter(provider=provider, is_active=True)
                .order_by("-is_default", "order")
                .first()
            )
            attrs["active_model"] = model
        if model is not None:
            if model.provider != provider:
                raise serializers.ValidationError(
                    {"active_model_id": ["선택한 모델이 활성 제공자의 모델이 아닙니다."]}
                )
            if not model.is_active:
                raise serializers.ValidationError(
                    {"active_model_id": ["비활성화된 모델은 선택할 수 없습니다."]}
                )
        return attrs


class PromptTemplateSerializer(serializers.ModelSerializer):
    updated_by_name = serializers.SerializerMethodField()

    class Meta:
        model = PromptTemplate
        fields = [
            "id",
            "key",
            "name",
            "description",
            "system_prompt",
            "user_prompt_template",
            "output_schema",
            "version",
            "is_active",
            "notes",
            "updated_by_name",
            "created_at",
        ]
        read_only_fields = fields

    def get_updated_by_name(self, obj) -> str | None:
        return str(obj.updated_by) if obj.updated_by_id else None


class PromptVersionCreateSerializer(serializers.Serializer):
    system_prompt = serializers.CharField(trim_whitespace=False)
    user_prompt_template = serializers.CharField(trim_whitespace=False)
    output_schema = serializers.JSONField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        errors = {}
        for name in ("system_prompt", "user_prompt_template"):
            problem = check_syntax(attrs[name])
            if problem:
                errors[name] = [f"템플릿 문법 오류: {problem}"]
        problem = schema_error(attrs.get("output_schema"))
        if problem:
            errors["output_schema"] = [f"JSON Schema 오류: {problem}"]
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class LLMCallLogSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = LLMCallLog
        fields = [
            "id",
            "task_key",
            "provider",
            "model_id",
            "prompt_version",
            "request_tokens",
            "response_tokens",
            "latency_ms",
            "status",
            "status_label",
            "error",
            "request_excerpt",
            "response_text",
            "job",
            "created_at",
        ]
        read_only_fields = fields


class LLMCallLogListSerializer(LLMCallLogSerializer):
    """List rows without the (large) prompt/response text — fetched per row on demand."""

    class Meta(LLMCallLogSerializer.Meta):
        fields = [
            f
            for f in LLMCallLogSerializer.Meta.fields
            if f not in ("request_excerpt", "response_text")
        ]
        read_only_fields = fields
