from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.llm.models import LLMSettings
from apps.llm.services import is_llm_configured

from .app_settings import set_setting
from .defaults import APP_SETTING_DEFAULTS
from .jobs import cancel, retry
from .models import AppSetting, Job
from .permissions import IsAdminRole, ReadAnyWriteAdmin
from .serializers import JobSerializer


class SystemStatusView(APIView):
    """GET /api/system/status — public; drives the LLM-not-configured redirect (specs/03 §4)."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        configured = is_llm_configured()
        return Response(
            {
                "llm_configured": configured,
                "active_provider": LLMSettings.load().active_provider if configured else None,
                "app_version": settings.APP_VERSION,
                "admin_must_change_password": User.objects.filter(
                    role=User.Role.ADMIN, is_active=True, must_change_password=True
                ).exists(),
            }
        )


class JobViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """/api/jobs — users may poll their own jobs; admins see all (specs/10)."""

    serializer_class = JobSerializer

    def get_permissions(self):
        if self.action == "retrieve":
            return [ReadAnyWriteAdmin()]
        return [IsAdminRole()]

    def get_queryset(self):
        qs = Job.objects.all()
        user = self.request.user
        if self.action == "retrieve" and not user.is_admin_role:
            qs = qs.filter(created_by=user)
        params = self.request.query_params
        for field in ("status", "type"):
            if params.get(field):
                qs = qs.filter(**{field: params[field]})
        return qs

    @action(detail=True, methods=["post"])
    def retry(self, request, pk=None):
        job = self.get_object()
        if job.status not in ("FAILED", "CANCELLED"):
            raise ValidationError({"detail": ["실패하거나 취소된 작업만 다시 실행할 수 있습니다."]})
        return Response(JobSerializer(retry(job)).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        job = self.get_object()
        if not cancel(job):
            raise ValidationError({"detail": ["대기 중인 작업만 취소할 수 있습니다."]})
        job.refresh_from_db()
        return Response(JobSerializer(job).data)


class AppSettingsView(APIView):
    """GET grouped settings / PUT {values: {key: value}} (specs/04 §5, specs/10)."""

    permission_classes = [IsAdminRole]

    def get(self, request):
        groups: dict[str, list] = {}
        for setting in AppSetting.objects.order_by("group", "key"):
            seed = APP_SETTING_DEFAULTS.get(setting.key)
            groups.setdefault(setting.group, []).append(
                {
                    "key": setting.key,
                    "value": setting.value,
                    "value_type": setting.value_type,
                    "description": setting.description,
                    "default": seed.value if seed else None,
                    "is_default": bool(seed) and seed.value == setting.value,
                    "has_default": bool(seed),
                    "updated_at": setting.updated_at,
                }
            )
        return Response({"groups": [{"group": g, "settings": rows} for g, rows in groups.items()]})

    def put(self, request):
        values = request.data.get("values")
        if not isinstance(values, dict) or not values:
            raise ValidationError({"values": ["{설정키: 값} 형식이어야 합니다."]})
        errors = {}
        with transaction.atomic():
            for key, value in values.items():
                if not AppSetting.objects.filter(key=key).exists():
                    errors[key] = ["알 수 없는 설정입니다."]
                    continue
                try:
                    set_setting(key, value)
                except DjangoValidationError as exc:
                    errors[key] = exc.messages
            if errors:
                transaction.set_rollback(True)
        if errors:
            raise ValidationError(errors)
        return self.get(request)


class AppSettingResetView(APIView):
    """POST /api/settings/app/{key}/reset"""

    permission_classes = [IsAdminRole]

    def post(self, request, key):
        seed = APP_SETTING_DEFAULTS.get(key)
        if seed is None:
            raise ValidationError({"key": ["기본값이 없는 설정입니다."]})
        setting = set_setting(key, seed.value)
        return Response({"key": setting.key, "value": setting.value})
