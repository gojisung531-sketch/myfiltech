import pytest

from apps.accounts.models import User
from apps.conftest import PASSWORD

pytestmark = pytest.mark.django_db


def test_user_admin_requires_admin_role(api_client, manager_client):
    assert api_client.get("/api/users").status_code == 401
    res = manager_client.get("/api/users")
    assert res.status_code == 403
    assert res.data["detail"] == "관리자 권한이 필요합니다."


def test_list_and_filter_users(admin_client, manager_user):
    res = admin_client.get("/api/users")
    assert res.status_code == 200
    assert {"count", "next", "previous", "results"} <= res.data.keys()
    res = admin_client.get("/api/users?role=BID_MANAGER")
    assert [u["username"] for u in res.data["results"]] == ["manager"]


def test_create_bid_manager(admin_client):
    payload = {
        "username": "lee",
        "password": "Another-pass-9",
        "display_name": "이담당",
        "department": "영업",
    }
    res = admin_client.post("/api/users", payload, format="json")
    assert res.status_code == 201
    assert res.data["role"] == "BID_MANAGER"
    assert "password" not in res.data
    assert User.objects.get(username="lee").check_password("Another-pass-9")


def test_create_user_rejects_weak_password_and_duplicate(admin_client, manager_user):
    res = admin_client.post("/api/users", {"username": "x1", "password": "123"}, format="json")
    assert res.status_code == 400
    res = admin_client.post(
        "/api/users", {"username": "manager", "password": "Another-pass-9"}, format="json"
    )
    assert res.status_code == 400 and "username" in res.data["errors"]


def test_update_user(admin_client, manager_user):
    res = admin_client.patch(
        f"/api/users/{manager_user.id}", {"display_name": "김담당", "phone": "010"}, format="json"
    )
    assert res.status_code == 200
    assert res.data["display_name"] == "김담당"


def test_last_active_admin_is_protected(admin_client, admin_user):
    default_admin = User.objects.get(username="admin")
    res = admin_client.patch(f"/api/users/{default_admin.id}", {"is_active": False}, format="json")
    assert res.status_code == 200  # admin_user is still active

    res = admin_client.patch(f"/api/users/{admin_user.id}", {"is_active": False}, format="json")
    assert res.status_code == 400
    res = admin_client.patch(f"/api/users/{admin_user.id}", {"role": "BID_MANAGER"}, format="json")
    assert res.status_code == 400
    assert admin_client.delete(f"/api/users/{admin_user.id}").status_code == 400


def test_delete_deactivates_by_default(admin_client, manager_user):
    assert admin_client.delete(f"/api/users/{manager_user.id}").status_code == 204
    manager_user.refresh_from_db()
    assert manager_user.is_active is False


def test_hard_delete_only_without_login_history(admin_client, manager_user, api_client):
    api_client.post("/api/auth/login", {"username": "manager", "password": PASSWORD}, format="json")
    assert admin_client.delete(f"/api/users/{manager_user.id}?hard=true").status_code == 400

    fresh = User.objects.create_user(username="fresh", password=PASSWORD)
    assert admin_client.delete(f"/api/users/{fresh.id}?hard=true").status_code == 204
    assert not User.objects.filter(pk=fresh.id).exists()


def test_reset_password_unlocks_account(admin_client, manager_user, api_client):
    manager_user.failed_login_attempts = 3
    manager_user.save()
    res = admin_client.post(
        f"/api/users/{manager_user.id}/reset-password",
        {"new_password": "Reset-pass-77"},
        format="json",
    )
    assert res.status_code == 200
    manager_user.refresh_from_db()
    assert manager_user.failed_login_attempts == 0
    res = api_client.post(
        "/api/auth/login", {"username": "manager", "password": "Reset-pass-77"}, format="json"
    )
    assert res.status_code == 200
