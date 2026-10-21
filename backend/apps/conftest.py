import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User

PASSWORD = "Str0ng-pass!23"


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    """Uploaded files go to a per-test temp dir."""
    settings.MEDIA_ROOT = tmp_path / "media"


@pytest.fixture
def inline_jobs(db):
    """Run background jobs synchronously inside the request."""
    from apps.core.app_settings import set_setting

    set_setting("jobs.run_inline", True)


@pytest.fixture
def company_data(db):
    """initial-data/company loaded through the real pipeline (rules only)."""
    from apps.documents.loader import load_company

    return load_company()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def admin_user(db):
    return User.objects.create_user(
        username="admin2", password=PASSWORD, role=User.Role.ADMIN, display_name="관리자2"
    )


@pytest.fixture
def manager_user(db):
    return User.objects.create_user(
        username="manager", password=PASSWORD, role=User.Role.BID_MANAGER, display_name="담당자"
    )


def _client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def admin_client(admin_user):
    return _client_for(admin_user)


@pytest.fixture
def manager_client(manager_user):
    return _client_for(manager_user)


RAW_KEY = "sk-ant-api03-SECRETVALUE-9876"


@pytest.fixture
def fake_llm(db, monkeypatch):
    """Active provider configured with a key; every LLM call goes to FakeProvider."""
    from apps.llm import services
    from apps.llm.models import LLMProviderConfig
    from apps.llm.providers.fake import FakeProvider

    config = LLMProviderConfig.objects.get(provider="ANTHROPIC")
    config.set_api_key(RAW_KEY)
    config.is_enabled = True
    config.save()
    monkeypatch.setattr(services, "get_provider_class", lambda name: FakeProvider)
    return FakeProvider.reset()
