import logging
from types import SimpleNamespace

import anthropic
import httpx
import pytest

from apps.core.logging import SecretMaskingFilter, mask_secrets
from apps.llm.providers import LLMError, get_provider_class
from apps.llm.providers.anthropic import AnthropicProvider
from apps.llm.providers.base import status_error


@pytest.mark.parametrize(
    "code,expected",
    [
        (401, "API Key가 올바르지 않거나"),
        (403, "API Key가 올바르지 않거나"),
        (404, "모델을 찾을 수 없습니다: m1"),
        (429, "요청 한도를 초과"),
        (500, "HTTP 500"),
    ],
)
def test_status_error_messages(code, expected):
    assert expected in status_error(code, "m1").user_message


def test_provider_registry():
    for name in ("ANTHROPIC", "OPENAI", "GEMINI"):
        assert get_provider_class(name).__name__.lower().startswith(name.lower()[:4])
    with pytest.raises(ValueError):
        get_provider_class("OTHER")


def _raise(exc):
    def _create(**kwargs):
        raise exc

    return _create


def test_anthropic_auth_error_is_mapped(monkeypatch):
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    exc = anthropic.AuthenticationError(
        "invalid x-api-key", response=httpx.Response(401, request=request), body=None
    )
    client = SimpleNamespace(messages=SimpleNamespace(create=_raise(exc)))
    monkeypatch.setattr(AnthropicProvider, "_client", lambda self: client)
    with pytest.raises(LLMError, match="API Key가 올바르지 않거나"):
        AnthropicProvider(api_key="k").verify("claude-opus-5-5")


def test_anthropic_connection_error_is_mapped(monkeypatch):
    exc = anthropic.APIConnectionError(request=httpx.Request("POST", "https://x"))
    client = SimpleNamespace(messages=SimpleNamespace(create=_raise(exc)))
    monkeypatch.setattr(AnthropicProvider, "_client", lambda self: client)
    with pytest.raises(LLMError, match="연결할 수 없습니다"):
        AnthropicProvider(api_key="k").verify("claude-opus-5-5")


def test_mask_secrets():
    text = "key=sk-ant-api03-abcdefghijklmnop and AIzaSyABCDEFGHIJKLMNOPQRSTUVWX"
    masked = mask_secrets(text)
    assert "abcdefghijk" not in masked
    assert "ABCDEFGHIJKLMNOP" not in masked
    assert masked.startswith("key=sk-...mnop")


def test_logging_filter_masks_message():
    record = logging.LogRecord(
        "t", logging.INFO, "", 0, "using %s", ("sk-proj-0123456789abcd",), None
    )
    SecretMaskingFilter().filter(record)
    assert "0123456789" not in record.getMessage()


def test_llm_error_masks_secrets():
    assert "abcdefghijkl" not in str(LLMError("bad key sk-abcdefghijklmnop"))
