from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import User
from .services import is_last_active_admin


class CurrentUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "display_name", "role", "must_change_password"]


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "display_name",
            "role",
            "department",
            "email",
            "phone",
            "is_active",
            "must_change_password",
            "last_login",
            "date_joined",
        ]
        read_only_fields = ["id", "username", "must_change_password", "last_login", "date_joined"]

    def validate(self, attrs):
        user = self.instance
        if user is not None and is_last_active_admin(user):
            if attrs.get("role", user.role) != User.Role.ADMIN or attrs.get("is_active") is False:
                raise serializers.ValidationError(
                    "마지막 관리자는 비활성화하거나 역할을 변경할 수 없습니다."
                )
        return attrs


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "password",
            "display_name",
            "role",
            "department",
            "email",
            "phone",
        ]

    def validate(self, attrs):
        validate_password(attrs["password"], User(username=attrs.get("username", "")))
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        return User.objects.create_user(password=password, **validated_data)


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(trim_whitespace=False)


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(trim_whitespace=False)
    new_password = serializers.CharField(trim_whitespace=False)

    def validate_old_password(self, value):
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("현재 비밀번호가 올바르지 않습니다.")
        return value

    def validate_new_password(self, value):
        validate_password(value, self.context["request"].user)
        return value


class ResetPasswordSerializer(serializers.Serializer):
    new_password = serializers.CharField(trim_whitespace=False)

    def validate_new_password(self, value):
        validate_password(value, self.context.get("user"))
        return value
