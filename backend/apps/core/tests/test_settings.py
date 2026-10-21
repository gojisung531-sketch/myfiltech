import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from apps.core.app_settings import get_setting, seed_app_settings, set_setting
from apps.core.defaults import APP_SETTING_DEFAULTS
from apps.core.models import AppSetting
from config.env import parse_database_url


def test_custom_user_model_is_active():
    assert settings.AUTH_USER_MODEL == "accounts.User"
    assert get_user_model()._meta.label == "accounts.User"


def test_database_is_postgresql():
    assert settings.DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql"


def test_parse_database_url():
    db = parse_database_url("postgres://u%40x:p%3Aw@127.0.0.1:5432/filtech")
    assert db["USER"] == "u@x"
    assert db["PASSWORD"] == "p:w"
    assert db["HOST"] == "127.0.0.1"
    assert db["PORT"] == "5432"
    assert db["NAME"] == "filtech"


def test_parse_database_url_rejects_other_schemes():
    with pytest.raises(ValueError):
        parse_database_url("sqlite:///db.sqlite3")


@pytest.mark.django_db
def test_user_defaults_to_bid_manager():
    user = get_user_model().objects.create_user(username="kim", password="secret-pass-1")
    assert user.role == "BID_MANAGER"
    assert user.is_admin_role is False
    assert user.created_at is not None


@pytest.mark.django_db
def test_admin_role_and_superuser_are_admin():
    User = get_user_model()
    admin = User.objects.create_user(username="a", password="x" * 10, role=User.Role.ADMIN)
    su = User.objects.create_superuser(username="su", password="x" * 10)
    assert admin.is_admin_role
    assert su.is_admin_role


@pytest.mark.django_db
def test_settings_seeded_after_migrate():
    keys = set(AppSetting.objects.values_list("key", flat=True))
    assert set(APP_SETTING_DEFAULTS) <= keys
    assert AppSetting.objects.get(key="auth.lockout_threshold").group == "auth"


@pytest.mark.django_db
def test_seed_does_not_overwrite_existing_values():
    set_setting("jobs.concurrency", 4)
    assert seed_app_settings() == 0
    assert get_setting("jobs.concurrency") == 4


@pytest.mark.django_db
def test_get_setting_falls_back_to_default_when_row_missing():
    AppSetting.objects.filter(key="evaluation.batch_size").delete()
    assert get_setting("evaluation.batch_size") == 10
    assert get_setting("no.such.key", default="x") == "x"
    with pytest.raises(KeyError):
        get_setting("no.such.key")


@pytest.mark.django_db
def test_set_setting_validates_type():
    with pytest.raises(ValidationError):
        set_setting("jobs.concurrency", "two")
    with pytest.raises(ValidationError):
        set_setting("jobs.run_inline", 1)
    set_setting("company.standard_lead_time_days", None)
    assert get_setting("company.standard_lead_time_days") is None


@pytest.mark.django_db
def test_set_setting_rejects_unknown_key():
    with pytest.raises(KeyError):
        set_setting("unknown.key", 1)
