from rest_framework.permissions import BasePermission


class IsAdminRole(BasePermission):
    """ADMIN role (or superuser) only (specs/03 §2)."""

    message = "관리자 권한이 필요합니다."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_admin_role)


class IsBidManagerOrAdmin(BasePermission):
    """Any active logged-in user: BID_MANAGER or ADMIN."""

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_active)


class ReadAnyWriteAdmin(BasePermission):
    """Logged-in users may read; only admins may write (specs/03 §2)."""

    message = "관리자 권한이 필요합니다."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated and user.is_active):
            return False
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return True
        return user.is_admin_role
