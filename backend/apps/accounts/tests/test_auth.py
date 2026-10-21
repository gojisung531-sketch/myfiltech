from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.conftest import PASSWORD
from apps.core.app_settings import set_setting

pytestmark = pytest.mark.django_db


def login(client, username, password):
    return client.post(
        "/api/auth/login", {"username": username, "password": password}, format="json"
    )


def test_login_success_returns_tokens_and_user(api_client, manager_user):
    res = login(api_client, "manager", PASSWORD)
    assert res.status_code == 200
    assert {"access", "refresh", "user"} <= res.data.keys()
    assert res.data["user"] == {
        "id": manager_user.id,
        "username": "manager",
        "display_name": "담당자",
        "role": "BID_MANAGER",
        "must_change_password": False,
    }
    manager_user.refresh_from_db()
    assert manager_user.last_login is not None


@pytest.mark.parametrize("username,password", [("manager", "wrong"), ("nobody", "whatever")])
def test_login_failure_is_generic(api_client, manager_user, username, password):
    res = login(api_client, username, password)
    assert res.status_code == 401
    assert res.data["code"] == "invalid_credentials"
    assert res.data["detail"] == "아이디 또는 비밀번호가 올바르지 않습니다."


def test_inactive_user_cannot_login(api_client, manager_user):
    manager_user.is_active = False
    manager_user.save()
    assert login(api_client, "manager", PASSWORD).status_code == 401


def test_lockout_after_threshold_and_unlock_after_expiry(api_client, manager_user):
    set_setting("auth.lockout_threshold", 3)
    for _ in range(3):
        assert login(api_client, "manager", "wrong").status_code == 401

    res = login(api_client, "manager", PASSWORD)
    assert res.status_code == 403
    assert res.data["code"] == "account_locked"

    manager_user.refresh_from_db()
    manager_user.locked_until = timezone.now() - timedelta(seconds=1)
    manager_user.save()
    assert login(api_client, "manager", PASSWORD).status_code == 200
    manager_user.refresh_from_db()
    assert manager_user.failed_login_attempts == 0
    assert manager_user.locked_until is None


def test_successful_login_resets_failure_count(api_client, manager_user):
    login(api_client, "manager", "wrong")
    login(api_client, "manager", PASSWORD)
    manager_user.refresh_from_db()
    assert manager_user.failed_login_attempts == 0


def test_me_requires_authentication(api_client):
    res = api_client.get("/api/auth/me")
    assert res.status_code == 401
    assert res.data["code"] == "not_authenticated"


def test_me_with_bearer_token(api_client, manager_user):
    access = login(api_client, "manager", PASSWORD).data["access"]
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    res = api_client.get("/api/auth/me")
    assert res.status_code == 200
    assert res.data["username"] == "manager"


def test_refresh_then_logout_blacklists_refresh_token(api_client, manager_user):
    tokens = login(api_client, "manager", PASSWORD).data
    res = api_client.post("/api/auth/refresh", {"refresh": tokens["refresh"]}, format="json")
    assert res.status_code == 200 and "access" in res.data

    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    res = api_client.post("/api/auth/logout", {"refresh": tokens["refresh"]}, format="json")
    assert res.status_code == 204

    res = api_client.post("/api/auth/refresh", {"refresh": tokens["refresh"]}, format="json")
    assert res.status_code == 401


def test_logout_with_invalid_token(manager_client):
    res = manager_client.post("/api/auth/logout", {"refresh": "garbage"}, format="json")
    assert res.status_code == 400
    assert "refresh" in res.data["errors"]


def test_change_password(manager_client, manager_user, api_client):
    manager_user.must_change_password = True
    manager_user.save()

    res = manager_client.post(
        "/api/auth/change-password",
        {"old_password": "wrong", "new_password": "N3w-strong-pass"},
        format="json",
    )
    assert res.status_code == 400 and "old_password" in res.data["errors"]

    res = manager_client.post(
        "/api/auth/change-password",
        {"old_password": PASSWORD, "new_password": "1234"},
        format="json",
    )
    assert res.status_code == 400 and "new_password" in res.data["errors"]

    res = manager_client.post(
        "/api/auth/change-password",
        {"old_password": PASSWORD, "new_password": "N3w-strong-pass"},
        format="json",
    )
    assert res.status_code == 200
    assert res.data["must_change_password"] is False
    assert login(api_client, "manager", "N3w-strong-pass").status_code == 200


def test_default_admin_can_login_and_must_change_password(api_client):
    res = login(api_client, "admin", "admin1234!")
    assert res.status_code == 200
    assert res.data["user"]["role"] == User.Role.ADMIN
    assert res.data["user"]["must_change_password"] is True
