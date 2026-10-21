import logging
from datetime import timedelta

from django.utils import timezone

from apps.core.app_settings import get_setting

from .models import User

logger = logging.getLogger(__name__)

DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "admin1234!"


def ensure_default_admin() -> User | None:
    """Create admin / admin1234! when no ADMIN exists. Idempotent (specs/03 §3)."""
    if User.objects.filter(role=User.Role.ADMIN).exists():
        return None
    existing = User.objects.filter(username=DEFAULT_ADMIN_USERNAME).first()
    if existing is not None:
        logger.warning(
            "No ADMIN user exists, but username '%s' is taken by a %s user; not overwriting.",
            DEFAULT_ADMIN_USERNAME,
            existing.role,
        )
        return None
    admin = User.objects.create_user(
        username=DEFAULT_ADMIN_USERNAME,
        password=DEFAULT_ADMIN_PASSWORD,
        role=User.Role.ADMIN,
        is_staff=True,
        display_name="관리자",
        must_change_password=True,
    )
    logger.info("Default admin account '%s' created.", DEFAULT_ADMIN_USERNAME)
    return admin


def is_locked(user: User) -> bool:
    return user.locked_until is not None and user.locked_until > timezone.now()


def register_failed_login(user: User) -> None:
    threshold = get_setting("auth.lockout_threshold")
    minutes = get_setting("auth.lockout_minutes")
    user.failed_login_attempts += 1
    if threshold and user.failed_login_attempts >= threshold:
        user.locked_until = timezone.now() + timedelta(minutes=minutes)
        user.failed_login_attempts = 0
    user.save(update_fields=["failed_login_attempts", "locked_until"])


def register_successful_login(user: User) -> None:
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login = timezone.now()
    user.save(update_fields=["failed_login_attempts", "locked_until", "last_login"])


def is_last_active_admin(user: User) -> bool:
    if user.role != User.Role.ADMIN or not user.is_active:
        return False
    return (
        not User.objects.filter(role=User.Role.ADMIN, is_active=True).exclude(pk=user.pk).exists()
    )
