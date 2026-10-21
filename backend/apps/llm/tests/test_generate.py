"""Request building and response handling per provider (no network)."""

from contextlib import contextmanager
from types import SimpleNamespace

import httpx
import openai
import pytest

from apps.llm.providers import LLMError
from apps.llm.providers.anthropic import FALLBACK_BETA, AnthropicProvider
from apps.llm.providers.base import FileInput, LLMRequest
from apps.llm.providers.gemini import GeminiProvider
from apps.llm.providers.openai import OpenAIProvider

SCHEMA = {
    "type": "object",
    "properties": {"a": {"type": "string"}},
    "required": ["a"],
    "additionalProperties": False,
}


def request(**kwargs):
    defaults = {"system": "SYS", "user": "USER", "model": "claude-opus-5-5", "temperature": 0.2}
    return LLMRequest(**{**defaults, **kwargs})


def test_anthropic_params():
    params = AnthropicProvider("k").build_params(
        request(json_schema=SCHEMA, effort="high", files=[FileInput("x.pdf", b"%PDF")])
    )
    assert "temperature" not in params
    assert params["system"] == "SYS"
    content = params["messages"][0]["content"]
    assert [c["type"] for c in content] == ["document", "text"]  # document before text
    assert content[0]["source"]["media_type"] == "application/pdf"
    assert params["output_config"] == {
        "format": {"type": "json_schema", "schema": SCHEMA},
        "effort": "high",
    }
    assert (params["betas"], params["fallbacks"]) == ([FALLBACK_BETA], "default")


@pytest.mark.parametrize(
    "model,base_url,expected",
    [
        ("claude-fable-5-1", None, True),
        ("claude-sonnet-5-5", None, True),
        ("claude-haiku-4-5-20251001", None, False),
        ("claude-opus-5-5", "https://proxy.example.com", False),
    ],
)
def test_anthropic_fallbacks_only_where_supported(model, base_url, expected):
    params = AnthropicProvider("k", base_url=base_url).build_params(request(model=model))
    assert ("fallbacks" in params) is expected
    assert "output_config" not in params


def _stream_client(message, captured):
    @contextmanager
    def stream(**kwargs):
        captured.update(kwargs)
        yield SimpleNamespace(get_final_message=lambda: message)

    namespace = SimpleNamespace(stream=stream)
    return SimpleNamespace(messages=namespace, beta=SimpleNamespace(messages=namespace))


def _message(stop_reason="end_turn", text='{"a": "b"}', **extra):
    return SimpleNamespace(
        id="msg_1",
        model="claude-opus-5-5",
        stop_reason=stop_reason,
        content=[
            SimpleNamespace(type="thinking", thinking=""),
            SimpleNamespace(type="text", text=text),
        ],
        usage=SimpleNamespace(input_tokens=10, output_tokens=5),
        **extra,
    )


def test_anthropic_generate(monkeypatch):
    captured = {}
    client = _stream_client(_message(), captured)
    monkeypatch.setattr(AnthropicProvider, "_client", lambda self, *a, **k: client)
    response = AnthropicProvider("k").generate(request(json_schema=SCHEMA))
    assert (response.text, response.input_tokens, response.output_tokens) == ('{"a": "b"}', 10, 5)
    assert captured["fallbacks"] == "default"


@pytest.mark.parametrize(
    "message,match",
    [
        (
            _message("refusal", stop_details=SimpleNamespace(category="cyber")),
            "거부했습니다 \\(분류: cyber\\)",
        ),
        (_message("max_tokens"), "최대 출력 토큰"),
    ],
)
def test_anthropic_stop_reasons(monkeypatch, message, match):
    client = _stream_client(message, {})
    monkeypatch.setattr(AnthropicProvider, "_client", lambda self, *a, **k: client)
    with pytest.raises(LLMError, match=match):
        AnthropicProvider("k").generate(request())


def test_openai_params():
    params = OpenAIProvider("k").build_params(
        request(model="gpt-6-astra", json_schema=SCHEMA, files=[FileInput("x.pdf", b"%PDF")])
    )
    assert params["instructions"] == "SYS"
    assert params["temperature"] == 0.2
    assert params["text"]["format"] == {
        "type": "json_schema",
        "name": "result",
        "schema": SCHEMA,
        "strict": True,
    }
    content = params["input"][0]["content"]
    assert content[0]["type"] == "input_file"
    assert content[0]["file_data"].startswith("data:application/pdf;base64,")
    assert content[1] == {"type": "input_text", "text": "USER"}


def test_openai_retries_without_temperature(monkeypatch):
    calls = []
    bad = openai.BadRequestError(
        "Unsupported parameter: 'temperature'",
        response=httpx.Response(400, request=httpx.Request("POST", "https://x")),
        body=None,
    )

    def create(**kwargs):
        calls.append(kwargs)
        if "temperature" in kwargs:
            raise bad
        return SimpleNamespace(
            id="r",
            model="gpt-6-astra",
            status="completed",
            output_text='{"a": "b"}',
            usage=SimpleNamespace(input_tokens=3, output_tokens=4),
        )

    client = SimpleNamespace(responses=SimpleNamespace(create=create))
    monkeypatch.setattr(OpenAIProvider, "_client", lambda self, *a, **k: client)
    response = OpenAIProvider("k").generate(request(model="gpt-6-astra"))
    assert response.text == '{"a": "b"}'
    assert ["temperature" in c for c in calls] == [True, False]


def test_gemini_config_and_contents():
    provider = GeminiProvider("k")
    req = request(model="gemini-3.8-flash", json_schema=SCHEMA, files=[FileInput("x.pdf", b"%PDF")])
    config = provider.build_config(req)
    assert config.system_instruction == "SYS"
    assert config.response_mime_type == "application/json"
    assert config.response_json_schema == SCHEMA
    assert config.temperature == 0.2
    contents = provider.build_contents(req)
    assert contents[-1] == "USER" and contents[0].inline_data.mime_type == "application/pdf"
