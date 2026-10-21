import json

import pytest
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from apps.llm import services
from apps.llm.models import LLMModelOption, LLMProviderConfig, LLMSettings
from apps.llm.providers import LLMError, LLMProvider

pytestmark = pytest.mark.django_db

RAW_KEY = "sk-ant-api03-SECRETVALUE-9876"


class OkProvider(LLMProvider):
    calls = []

    def verify(self, model):
        OkProvider.calls.append((self.api_key, model))

    def generate(self, request):
        raise NotImplementedError


class FailingProvider(LLMProvider):
    def verify(self, model):
        raise LLMError("API Key가 올바르지 않거나 권한이 없습니다.")

    def generate(self, request):
        raise NotImplementedError


@pytest.fixture
def ok_provider(monkeypatch):
    OkProvider.calls = []
    monkeypatch.setattr(services, "get_provider_class", lambda name: OkProvider)
    return OkProvider


@pytest.fixture
def failing_provider(monkeypatch):
    monkeypatch.setattr(services, "get_provider_class", lambda name: FailingProvider)


def status(client):
    return client.get("/api/system/status").data


def test_status_is_public_and_initially_unconfigured(api_client):
    res = api_client.get("/api/system/status")
    assert res.status_code == 200
    assert res.data == {
        "llm_configured": False,
        "active_provider": None,
        "app_version": "0.1.0",
        "admin_must_change_password": True,
    }


def test_settings_require_admin(api_client, manager_client):
    assert api_client.get("/api/settings/llm").status_code == 401
    assert manager_client.get("/api/settings/llm").status_code == 403
    assert manager_client.put("/api/settings/llm/providers/ANTHROPIC", {}).status_code == 403


def test_get_settings_payload(admin_client):
    res = admin_client.get("/api/settings/llm")
    assert res.status_code == 200
    assert res.data["llm_configured"] is False
    assert res.data["settings"]["active_provider"] == "ANTHROPIC"
    active = LLMModelOption.objects.get(pk=res.data["settings"]["active_model_id"])
    assert active.model_id == "claude-opus-5-5"
    assert {p["provider"] for p in res.data["providers"]} == {"ANTHROPIC", "OPENAI", "GEMINI"}
    assert len(res.data["models"]) == 9


def test_save_key_verifies_and_configures(admin_client, api_client, ok_provider):
    res = admin_client.put(
        "/api/settings/llm/providers/ANTHROPIC", {"api_key": RAW_KEY}, format="json"
    )
    assert res.status_code == 200
    assert res.data["verify"] == {
        "ok": True,
        "message": "연결 성공 (claude-opus-5-5)",
        "model_id": "claude-opus-5-5",
    }
    assert res.data["provider"]["api_key_masked"] == "••••9876"
    assert res.data["provider"]["is_enabled"] is True
    assert res.data["llm_configured"] is True
    assert ok_provider.calls == [(RAW_KEY, "claude-opus-5-5")]

    config = LLMProviderConfig.objects.get(provider="ANTHROPIC")
    assert RAW_KEY not in config.api_key_encrypted
    assert config.get_api_key() == RAW_KEY
    assert config.last_verify_ok is True

    assert status(api_client)["llm_configured"] is True
    assert status(api_client)["active_provider"] == "ANTHROPIC"


def test_api_key_never_returned(admin_client, ok_provider):
    res = admin_client.put(
        "/api/settings/llm/providers/ANTHROPIC", {"api_key": RAW_KEY}, format="json"
    )
    assert "SECRETVALUE" not in json.dumps(res.data, ensure_ascii=False)
    res = admin_client.get("/api/settings/llm")
    assert "SECRETVALUE" not in json.dumps(res.data, ensure_ascii=False)


def test_key_saved_even_if_verification_fails(admin_client, failing_provider):
    res = admin_client.put(
        "/api/settings/llm/providers/ANTHROPIC", {"api_key": RAW_KEY}, format="json"
    )
    assert res.status_code == 200
    assert res.data["verify"]["ok"] is False
    assert res.data["provider"]["has_api_key"] is True
    assert res.data["provider"]["last_verify_error"].startswith("API Key가")


def test_blank_key_keeps_existing_key(admin_client, ok_provider):
    admin_client.put("/api/settings/llm/providers/ANTHROPIC", {"api_key": RAW_KEY}, format="json")
    res = admin_client.put(
        "/api/settings/llm/providers/ANTHROPIC",
        {"api_key": "", "base_url": "https://proxy.example.com"},
        format="json",
    )
    assert res.data["verify"] is None
    config = LLMProviderConfig.objects.get(provider="ANTHROPIC")
    assert config.get_api_key() == RAW_KEY
    assert config.base_url == "https://proxy.example.com"


def test_disabled_provider_is_not_configured(admin_client, api_client, ok_provider):
    admin_client.put("/api/settings/llm/providers/ANTHROPIC", {"api_key": RAW_KEY}, format="json")
    admin_client.put("/api/settings/llm/providers/ANTHROPIC", {"is_enabled": False}, format="json")
    assert status(api_client)["llm_configured"] is False


def test_key_for_inactive_provider_needs_provider_switch(admin_client, api_client, ok_provider):
    admin_client.put("/api/settings/llm/providers/OPENAI", {"api_key": "sk-proj-x1"}, format="json")
    assert ok_provider.calls == [("sk-proj-x1", "gpt-6-astra")]
    assert status(api_client)["llm_configured"] is False

    res = admin_client.put("/api/settings/llm", {"active_provider": "OPENAI"}, format="json")
    assert res.status_code == 200
    active = LLMModelOption.objects.get(pk=res.data["settings"]["active_model_id"])
    assert active.model_id == "gpt-6-astra"
    assert status(api_client)["llm_configured"] is True


def test_verify_endpoint(admin_client, ok_provider):
    res = admin_client.post("/api/settings/llm/providers/GEMINI/verify", {}, format="json")
    assert res.data["ok"] is False
    assert res.data["message"] == "API Key가 저장되어 있지 않습니다."

    admin_client.put("/api/settings/llm/providers/GEMINI", {"api_key": "AIza-test"}, format="json")
    res = admin_client.post(
        "/api/settings/llm/providers/GEMINI/verify",
        {"model_id": "gemini-3.5-flash-lite"},
        format="json",
    )
    assert res.data["ok"] is True
    assert res.data["model_id"] == "gemini-3.5-flash-lite"


def test_unknown_provider_rejected(admin_client):
    res = admin_client.put("/api/settings/llm/providers/OTHER", {"api_key": "x"}, format="json")
    assert res.status_code == 400


def test_update_settings_validation(admin_client):
    gemini = LLMModelOption.objects.get(model_id="gemini-3.8-flash")
    res = admin_client.put("/api/settings/llm", {"active_model_id": gemini.id}, format="json")
    assert res.status_code == 400 and "active_model_id" in res.data["errors"]

    res = admin_client.put("/api/settings/llm", {"temperature": 3}, format="json")
    assert res.status_code == 400

    res = admin_client.put("/api/settings/llm", {"per_task_overrides": [1]}, format="json")
    assert res.status_code == 400

    fable = LLMModelOption.objects.get(model_id="claude-fable-5-1")
    res = admin_client.put(
        "/api/settings/llm",
        {"active_model_id": fable.id, "temperature": 0.5, "max_retries": 3},
        format="json",
    )
    assert res.status_code == 200
    settings_row = LLMSettings.load()
    assert settings_row.active_model == fable
    assert settings_row.temperature == 0.5


def test_model_option_crud(admin_client):
    res = admin_client.post(
        "/api/settings/llm/models",
        {
            "provider": "ANTHROPIC",
            "model_id": "claude-new",
            "display_name": "New",
            "is_default": True,
        },
        format="json",
    )
    assert res.status_code == 201
    defaults = LLMModelOption.objects.filter(provider="ANTHROPIC", is_default=True)
    assert list(defaults.values_list("model_id", flat=True)) == ["claude-new"]

    res = admin_client.get("/api/settings/llm/models?provider=ANTHROPIC")
    assert len(res.data) == 5

    duplicate = admin_client.post(
        "/api/settings/llm/models",
        {"provider": "ANTHROPIC", "model_id": "claude-new", "display_name": "dup"},
        format="json",
    )
    assert duplicate.status_code == 400

    new_id = LLMModelOption.objects.get(model_id="claude-new").id
    assert admin_client.delete(f"/api/settings/llm/models/{new_id}").status_code == 204


def test_active_model_cannot_be_deleted_or_deactivated(admin_client):
    active_id = LLMSettings.load().active_model_id
    assert admin_client.delete(f"/api/settings/llm/models/{active_id}").status_code == 400
    res = admin_client.patch(
        f"/api/settings/llm/models/{active_id}", {"is_active": False}, format="json"
    )
    assert res.status_code == 400


class _NeedsLLM(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        services.ensure_llm_configured()


def test_ensure_llm_configured_returns_409():
    response = _NeedsLLM.as_view()(APIRequestFactory().get("/x"))
    assert response.status_code == 409
    assert response.data["code"] == "llm_not_configured"
