from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.permissions import IsAdminRole, IsBidManagerOrAdmin

from .models import User
from .serializers import (
    ChangePasswordSerializer,
    CurrentUserSerializer,
    LoginSerializer,
    LogoutSerializer,
    ResetPasswordSerializer,
    UserCreateSerializer,
    UserSerializer,
)
from .services import (
    is_last_active_admin,
    is_locked,
    register_failed_login,
    register_successful_login,
)


class InvalidCredentials(APIException):
    # Not AuthenticationFailed: DRF turns that into 403 on views without authenticators.
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = "아이디 또는 비밀번호가 올바르지 않습니다."
    default_code = "invalid_credentials"


class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        username = serializer.validated_data["username"]
        password = serializer.validated_data["password"]

        user = User.objects.filter(username=username).first()
        if user is None or not user.is_active:
            raise InvalidCredentials()
        if is_locked(user):
            minutes = max(1, int((user.locked_until - timezone.now()).total_seconds() // 60) + 1)
            raise PermissionDenied(
                f"로그인 실패가 반복되어 계정이 잠겼습니다. 약 {minutes}분 후 다시 시도하세요.",
                code="account_locked",
            )
        if not user.check_password(password):
            register_failed_login(user)
            raise InvalidCredentials()

        register_successful_login(user)
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": CurrentUserSerializer(user).data,
            }
        )


class LogoutView(APIView):
    permission_classes = [IsBidManagerOrAdmin]

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            RefreshToken(serializer.validated_data["refresh"]).blacklist()
        except TokenError as exc:
            raise ValidationError({"refresh": ["유효하지 않은 토큰입니다."]}) from exc
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [IsBidManagerOrAdmin]

    def get(self, request):
        return Response(CurrentUserSerializer(request.user).data)


class ChangePasswordView(APIView):
    permission_classes = [IsBidManagerOrAdmin]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = request.user
        user.set_password(serializer.validated_data["new_password"])
        user.must_change_password = False
        user.save(update_fields=["password", "must_change_password"])
        return Response(CurrentUserSerializer(user).data)


class UserViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """User management for admins (specs/03 §5). DELETE deactivates; see destroy()."""

    permission_classes = [IsAdminRole]
    queryset = User.objects.all()
    http_method_names = ["get", "post", "patch", "delete"]

    def get_serializer_class(self):
        return UserCreateSerializer if self.action == "create" else UserSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        role = self.request.query_params.get("role")
        if role:
            qs = qs.filter(role=role)
        is_active = self.request.query_params.get("is_active")
        if is_active in ("true", "false"):
            qs = qs.filter(is_active=is_active == "true")
        return qs

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        """Deactivate. `?hard=true` physically deletes a user who has never logged in."""
        user = self.get_object()
        if is_last_active_admin(user):
            raise ValidationError({"detail": ["마지막 관리자는 삭제할 수 없습니다."]})
        if request.query_params.get("hard") == "true":
            if user.last_login is not None:
                raise ValidationError(
                    {"detail": ["로그인 이력이 있는 사용자는 비활성화만 가능합니다."]}
                )
            user.delete()
        else:
            user.is_active = False
            user.save(update_fields=["is_active"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="reset-password")
    def reset_password(self, request, pk=None):
        user = self.get_object()
        serializer = ResetPasswordSerializer(data=request.data, context={"user": user})
        serializer.is_valid(raise_exception=True)
        user.set_password(serializer.validated_data["new_password"])
        user.failed_login_attempts = 0
        user.locked_until = None
        user.save(update_fields=["password", "failed_login_attempts", "locked_until"])
        return Response(UserSerializer(user).data)
