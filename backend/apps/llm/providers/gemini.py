import httpx
from google import genai
from google.genai import errors, types

from .base import (
    VERIFY_MAX_TOKENS,
    VERIFY_PROMPT,
    LLMError,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    status_error,
)


class GeminiProvider(LLMProvider):
    def _client(self, max_retries: int = 0, timeout: int | None = None) -> genai.Client:
        options = {"timeout": (timeout or self.timeout) * 1000}
        if self.base_url:
            options["base_url"] = self.base_url
        if max_retries:
            options["retry_options"] = types.HttpRetryOptions(attempts=max_retries + 1)
        return genai.Client(api_key=self.api_key, http_options=types.HttpOptions(**options))

    def _call(self, model: str, client: genai.Client, **kwargs):
        try:
            return client.models.generate_content(model=model, **kwargs)
        except errors.APIError as exc:
            # Gemini reports an invalid key as HTTP 400 API_KEY_INVALID.
            if "API_KEY_INVALID" in str(exc) or "API key not valid" in str(exc):
                raise LLMError("API Key가 올바르지 않거나 권한이 없습니다.") from exc
            raise status_error(exc.code, model, str(exc.message or "")) from exc
        except httpx.TransportError as exc:
            raise LLMError("Gemini 서버에 연결할 수 없습니다.") from exc

    def verify(self, model: str) -> None:
        self._call(
            model,
            self._client(),
            contents=VERIFY_PROMPT,
            config=types.GenerateContentConfig(max_output_tokens=VERIFY_MAX_TOKENS),
        )

    def build_config(self, request: LLMRequest) -> types.GenerateContentConfig:
        config = {
            "system_instruction": request.system,
            "max_output_tokens": request.max_output_tokens,
        }
        if request.temperature is not None:
            config["temperature"] = request.temperature
        if request.json_schema:
            config["response_mime_type"] = "application/json"
            config["response_json_schema"] = request.json_schema
        return types.GenerateContentConfig(**config)

    def build_contents(self, request: LLMRequest) -> list:
        parts = [types.Part.from_bytes(data=f.data, mime_type=f.mime_type) for f in request.files]
        return [*parts, request.user]

    def generate(self, request: LLMRequest) -> LLMResponse:
        response = self._call(
            request.model,
            self._client(request.max_retries, request.timeout),
            contents=self.build_contents(request),
            config=self.build_config(request),
        )
        candidate = (response.candidates or [None])[0]
        finish = str(getattr(candidate, "finish_reason", "") or "")
        if "MAX_TOKENS" in finish:
            raise LLMError("응답이 최대 출력 토큰에 도달해 잘렸습니다. 최대 출력 토큰을 늘리세요.")
        if "SAFETY" in finish or "PROHIBITED" in finish:
            raise LLMError("LLM이 요청을 거부했습니다 (안전 정책).")
        usage = response.usage_metadata
        return LLMResponse(
            text=response.text or "",
            input_tokens=getattr(usage, "prompt_token_count", None),
            output_tokens=getattr(usage, "candidates_token_count", None),
            raw={"model": request.model, "finish_reason": finish},
        )
