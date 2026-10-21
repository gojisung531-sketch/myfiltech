from django.db import transaction
from django.db.models import Count, Sum
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsAdminRole

from .defaults import prompt_fields
from .models import (
    LLMCallLog,
    LLMModelOption,
    LLMProviderConfig,
    LLMSettings,
    PromptTemplate,
    Provider,
)
from .prompt_defaults import PROMPTS_BY_KEY
from .prompts import check_syntax
from .providers import LLMError
from .serializers import (
    LLMCallLogListSerializer,
    LLMCallLogSerializer,
    LLMSettingsSerializer,
    ModelOptionSerializer,
    PromptTemplateSerializer,
    PromptVersionCreateSerializer,
    ProviderConfigSerializer,
    ProviderConfigUpdateSerializer,
)
from .services import ensure_llm_configured, is_llm_configured, run_task, verify_provider


def _settings_payload() -> dict:
    return {
        "llm_configured": is_llm_configured(),
        "settings": LLMSettingsSerializer(LLMSettings.load()).data,
        "providers": ProviderConfigSerializer(LLMProviderConfig.objects.all(), many=True).data,
        "models": ModelOptionSerializer(LLMModelOption.objects.all(), many=True).data,
    }


def _get_config(provider: str) -> LLMProviderConfig:
    if provider not in Provider.values:
        raise ValidationError({"provider": [f"알 수 없는 제공자입니다: {provider}"]})
    config, _ = LLMProviderConfig.objects.get_or_create(provider=provider)
    return config


class LLMSettingsView(APIView):
    """GET/PUT /api/settings/llm"""

    permission_classes = [IsAdminRole]

    def get(self, request):
        return Response(_settings_payload())

    def put(self, request):
        serializer = LLMSettingsSerializer(LLMSettings.load(), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(_settings_payload())


class ProviderConfigView(APIView):
    """PUT /api/settings/llm/providers/{provider} — saving a new key also runs a connection test.

    The key is stored even if the test fails (specs/04 §4).
    """

    permission_classes = [IsAdminRole]

    def put(self, request, provider):
        config = _get_config(provider)
        serializer = ProviderConfigUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        new_key = data.get("api_key") or ""
        if new_key:
            config.set_api_key(new_key)
            if "is_enabled" not in data:
                config.is_enabled = True
        if "base_url" in data:
            config.base_url = data["base_url"]
        if "is_enabled" in data:
            config.is_enabled = data["is_enabled"]
        config.save()

        verify = None
        if new_key:
            result = verify_provider(config)
            verify = {"ok": result.ok, "message": result.message, "model_id": result.model_id}
            config.refresh_from_db()

        return Response(
            {
                "provider": ProviderConfigSerializer(config).data,
                "verify": verify,
                "llm_configured": is_llm_configured(),
            }
        )


class ProviderVerifyView(APIView):
    """POST /api/settings/llm/providers/{provider}/verify {model_id?}"""

    permission_classes = [IsAdminRole]

    def post(self, request, provider):
        config = _get_config(provider)
        result = verify_provider(config, request.data.get("model_id") or None)
        config.refresh_from_db()
        return Response(
            {
                "ok": result.ok,
                "message": result.message,
                "model_id": result.model_id,
                "provider": ProviderConfigSerializer(config).data,
            }
        )


class ModelOptionViewSet(viewsets.ModelViewSet):
    """CRUD /api/settings/llm/models"""

    permission_classes = [IsAdminRole]
    serializer_class = ModelOptionSerializer
    pagination_class = None
    http_method_names = ["get", "post", "patch", "delete"]

    def get_queryset(self):
        qs = LLMModelOption.objects.all()
        provider = self.request.query_params.get("provider")
        return qs.filter(provider=provider) if provider else qs

    def perform_update(self, serializer):
        model = serializer.instance
        if serializer.validated_data.get("is_active") is False and self._is_active_model(model):
            raise ValidationError({"is_active": ["현재 사용 중인 모델은 비활성화할 수 없습니다."]})
        serializer.save()

    def perform_destroy(self, instance):
        if self._is_active_model(instance):
            raise ValidationError({"detail": ["현재 사용 중인 모델은 삭제할 수 없습니다."]})
        instance.delete()

    @staticmethod
    def _is_active_model(model: LLMModelOption) -> bool:
        return LLMSettings.load().active_model_id == model.pk


# ---- prompts (specs/04 §5, specs/10) -------------------------------------------------


def _prompt_meta(key: str) -> dict:
    default = PROMPTS_BY_KEY.get(key, {})
    return {
        "variables": default.get("variables", []),
        "dynamic_schema": key == "document.extract_metadata",
        "has_default": bool(default),
    }


class PromptListView(APIView):
    """GET /api/settings/prompts — active version per key."""

    permission_classes = [IsAdminRole]

    def get(self, request):
        counts = dict(
            PromptTemplate.objects.values_list("key")
            .annotate(n=Count("id"))
            .values_list("key", "n")
        )
        rows = []
        for template in PromptTemplate.objects.filter(is_active=True).order_by("key"):
            data = PromptTemplateSerializer(template).data
            rows.append(
                {**data, **_prompt_meta(template.key), "version_count": counts[template.key]}
            )
        return Response(rows)


def _get_active_or_404(key: str) -> PromptTemplate:
    template = PromptTemplate.active(key)
    if template is None:
        raise NotFound(f"프롬프트를 찾을 수 없습니다: {key}")
    return template


class PromptDetailView(APIView):
    """GET versions / POST a new version (which becomes active)."""

    permission_classes = [IsAdminRole]

    def get(self, request, key):
        active = _get_active_or_404(key)
        versions = PromptTemplate.objects.filter(key=key).order_by("-version")
        return Response(
            {
                "active": PromptTemplateSerializer(active).data,
                "versions": PromptTemplateSerializer(versions, many=True).data,
                **_prompt_meta(key),
            }
        )

    def post(self, request, key):
        active = _get_active_or_404(key)
        serializer = PromptVersionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if key == "document.extract_metadata":
            data["output_schema"] = None  # generated from category fields at runtime
        template = _new_version(
            active,
            system_prompt=data["system_prompt"],
            user_prompt_template=data["user_prompt_template"],
            output_schema=data.get("output_schema", active.output_schema),
            notes=data.get("notes", ""),
            user=request.user,
        )
        return Response(PromptTemplateSerializer(template).data, status=201)


def _new_version(active: PromptTemplate, *, user, **fields) -> PromptTemplate:
    with transaction.atomic():
        latest = (
            PromptTemplate.objects.select_for_update()
            .filter(key=active.key)
            .order_by("-version")
            .first()
        )
        template = PromptTemplate.objects.create(
            key=active.key,
            name=fields.pop("name", active.name),
            description=fields.pop("description", active.description),
            version=latest.version + 1,
            updated_by=user,
            **fields,
        )
        template.activate()
    return template


class PromptActivateView(APIView):
    """POST /api/settings/prompts/{key}/activate {version} — roll back/forward."""

    permission_classes = [IsAdminRole]

    def post(self, request, key):
        version = request.data.get("version")
        template = PromptTemplate.objects.filter(key=key, version=version).first()
        if template is None:
            raise NotFound("해당 버전을 찾을 수 없습니다.")
        template.activate()
        return Response(PromptTemplateSerializer(template).data)


class PromptResetView(APIView):
    """POST /api/settings/prompts/{key}/reset — new version from the seed default."""

    permission_classes = [IsAdminRole]

    def post(self, request, key):
        default = PROMPTS_BY_KEY.get(key)
        if default is None:
            raise NotFound("기본값이 없는 프롬프트입니다.")
        active = _get_active_or_404(key)
        template = _new_version(
            active, user=request.user, notes="기본값으로 복원", **prompt_fields(default)
        )
        return Response(PromptTemplateSerializer(template).data, status=201)


class PromptTestView(APIView):
    """POST /api/settings/prompts/{key}/test — run an (unsaved) prompt; nothing is saved
    except the call log entry `test:<key>`."""

    permission_classes = [IsAdminRole]

    def post(self, request, key):
        from apps.documents.llm_steps import test_inputs
        from apps.documents.models import Document

        ensure_llm_configured()
        active = _get_active_or_404(key)
        body = request.data
        draft = PromptTemplate(
            key=key,
            name=active.name,
            version=active.version,
            system_prompt=body.get("system_prompt", active.system_prompt),
            user_prompt_template=body.get("user_prompt_template", active.user_prompt_template),
            output_schema=body.get("output_schema", active.output_schema),
        )
        for name in ("system_prompt", "user_prompt_template"):
            problem = check_syntax(getattr(draft, name))
            if problem:
                raise ValidationError({name: [f"템플릿 문법 오류: {problem}"]})

        files, schema = [], None
        if body.get("document_id"):
            document = Document.objects.filter(pk=body["document_id"]).first()
            if document is None:
                raise ValidationError({"document_id": ["문서를 찾을 수 없습니다."]})
            try:
                variables, files, schema = test_inputs(key, document)
            except ValueError as exc:
                raise ValidationError({"document_id": [str(exc)]}) from exc
        else:
            variables = body.get("variables")
            if not isinstance(variables, dict):
                raise ValidationError({"variables": ["변수는 JSON 객체여야 합니다."]})

        try:
            result = run_task(
                key,
                variables,
                files=files,
                output_schema=schema,
                template=draft,
                log_key=f"test:{key}",
            )
        except LLMError as exc:
            last = LLMCallLog.objects.filter(task_key=f"test:{key}").order_by("-id").first()
            return Response(
                {"ok": False, "error": str(exc), "raw_text": last.response_text if last else ""}
            )
        return Response(
            {
                "ok": True,
                "system": result.system,
                "user": result.user,
                "raw_text": result.raw_text,
                "parsed": result.data,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "latency_ms": result.latency_ms,
            }
        )


class LLMCallLogViewSet(viewsets.ReadOnlyModelViewSet):
    """GET /api/llm-logs — admin only, with today/month token totals (specs/07 §5)."""

    permission_classes = [IsAdminRole]
    serializer_class = LLMCallLogSerializer

    def get_serializer_class(self):
        return LLMCallLogListSerializer if self.action == "list" else LLMCallLogSerializer

    def get_queryset(self):
        qs = LLMCallLog.objects.all()
        params = self.request.query_params
        if params.get("task_key"):
            qs = qs.filter(task_key__icontains=params["task_key"])
        for name in ("status", "provider"):
            if params.get(name):
                qs = qs.filter(**{name: params[name]})
        if params.get("date_from"):
            qs = qs.filter(created_at__date__gte=params["date_from"])
        if params.get("date_to"):
            qs = qs.filter(created_at__date__lte=params["date_to"])
        return qs

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        today = timezone.localdate()

        def totals(qs):
            agg = qs.aggregate(
                calls=Count("id"),
                input_tokens=Sum("request_tokens"),
                output_tokens=Sum("response_tokens"),
            )
            return {k: v or 0 for k, v in agg.items()}

        response.data["summary"] = {
            "today": totals(LLMCallLog.objects.filter(created_at__date=today)),
            "month": totals(
                LLMCallLog.objects.filter(
                    created_at__year=today.year, created_at__month=today.month
                )
            ),
        }
        return response
