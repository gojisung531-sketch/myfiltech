"""Provider abstraction (specs/07 §2)."""

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from apps.core.logging import mask_secrets

VERIFY_PROMPT = "Reply with exactly: OK"
VERIFY_MAX_TOKENS = 64


class LLMError(Exception):
    """Error with a user-facing Korean message (secrets masked)."""

    def __init__(self, message: str):
        super().__init__(mask_secrets(message))
        self.user_message = mask_secrets(message)


@dataclass
class FileInput:
    filename: str
    data: bytes
    mime_type: str = "application/pdf"


@dataclass
class LLMRequest:
    system: str
    user: str
    model: str
    temperature: float | None = None
    max_output_tokens: int = 8192
    json_schema: dict | None = None
    files: list[FileInput] = field(default_factory=list)
    timeout: int = 120
    max_retries: int = 2
    effort: str | None = None


@dataclass
class LLMResponse:
    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    raw: dict = field(default_factory=dict)


class LLMProvider(ABC):
    def __init__(self, api_key: str, base_url: str | None = None, timeout: int = 30):
        self.api_key = api_key
        self.base_url = base_url or None
        self.timeout = timeout

    @abstractmethod
    def verify(self, model: str) -> None:
        """Send a minimal request. Raise LLMError on failure."""

    @abstractmethod
    def generate(self, request: LLMRequest) -> LLMResponse:
        """Run one request and return the text (JSON text when json_schema is set)."""


def status_error(status_code: int | None, model: str, detail: str = "") -> LLMError:
    if status_code in (401, 403):
        return LLMError("API Key가 올바르지 않거나 권한이 없습니다.")
    if status_code == 404:
        return LLMError(f"모델을 찾을 수 없습니다: {model}")
    if status_code == 429:
        return LLMError("요청 한도를 초과했습니다. 잠시 후 다시 시도하세요.")
    suffix = f" — {detail[:200]}" if detail else ""
    return LLMError(f"LLM 호출 오류 (HTTP {status_code}){suffix}")


_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.S)


def parse_json_text(text: str):
    """Parse model output as JSON, tolerating a surrounding ``` code fence."""
    match = _FENCE.match(text or "")
    return json.loads(match.group(1) if match else text)
