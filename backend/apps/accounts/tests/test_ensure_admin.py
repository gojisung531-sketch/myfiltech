import pytest
from django.core.management import call_command

from apps.accounts.models import User
from apps.accounts.services import DEFAULT_ADMIN_PASSWORD, ensure_default_admin

pytestmark = pytest.mark.django_db


def test_default_admin_created_by_migrate():
    admin = User.objects.get(username="admin")
    assert admin.role == User.Role.ADMIN
    assert admin.is_staff
    assert admin.must_change_password
    assert admin.check_password(DEFAULT_ADMIN_PASSWORD)


def test_ensure_admin_is_idempotent():
    assert ensure_default_admin() is None
    assert ensure_default_admin() is None
    assert User.objects.filter(role=User.Role.ADMIN).count() == 1


def test_creates_admin_when_no_admin_exists():
    User.objects.filter(role=User.Role.ADMIN).delete()
    admin = ensure_default_admin()
    assert admin is not None and admin.username == "admin"


def test_does_not_overwrite_non_admin_named_admin():
    User.objects.filter(role=User.Role.ADMIN).delete()
    User.objects.create_user(username="admin", password="x" * 12, role=User.Role.BID_MANAGER)
    assert ensure_default_admin() is None
    assert User.objects.get(username="admin").role == User.Role.BID_MANAGER


def test_ensure_admin_command(capsys):
    User.objects.filter(role=User.Role.ADMIN).delete()
    call_command("ensure_admin")
    call_command("ensure_admin")
    out = capsys.readouterr().out
    assert "created" in out
    assert "already exists" in out
    assert User.objects.filter(role=User.Role.ADMIN).count() == 1
