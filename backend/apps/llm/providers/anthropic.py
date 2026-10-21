import base64
import re

import anthropic

from .base import (
    VERIFY_MAX_TOKENS,
    VERIFY_PROMPT,
    LLMError,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    status_error,
)

# Models that accept server-side refusal fallbacks (fallbacks: "default"), specs/07 §2.
_FALLBACK_MODELS = re.compile(r"^claude-(opus-5|fable-5|sonnet-5-5)")
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicProvider(LLMProvider):
    def _client(self, max_retries: int = 0, timeout: int | None = None) -> anthropic.Anthropic:
        return anthropic.Anthropic(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=timeout or self.timeout,
            max_retries=max_retries,
        )

    def verify(self, model: str) -> None:
        try:
            self._client().messages.create(
                model=model,
                max_tokens=VERIFY_MAX_TOKENS,
                messages=[{"role": "user", "content": VERIFY_PROMPT}],
            )
        except anthropic.APIStatusError as exc:
            raise status_error(exc.status_code, model, str(exc.message)) from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError("Anthropic 서버에 연결할 수 없습니다.") from exc

    def build_params(self, request: LLMRequest) -> dict:
        """Messages API parameters. temperature is never sent (specs/07 §2)."""
        content: list[dict] = [
            {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": f.mime_type,
                    "data": base64.b64encode(f.data).decode(),
                },
                "title": f.filename,
            }
            for f in request.files
        ]
        content.append({"type": "text", "text": request.user})
        params: dict = {
            "model": request.model,
            "max_tokens": request.max_output_tokens,
            "system": request.system,
            "messages": [{"role": "user", "content": content}],
        }
        output_config: dict = {}
        if request.json_schema:
            output_config["format"] = {"type": "json_schema", "schema": request.json_schema}
        if request.effort:
            output_config["effort"] = request.effort
        if output_config:
            params["output_config"] = output_config
        if not self.base_url and _FALLBACK_MODELS.match(request.model):
            params["betas"] = [FALLBACK_BETA]
            params["fallbacks"] = "default"
        return params

    def generate(self, request: LLMRequest) -> LLMResponse:
        params = self.build_params(request)
        client = self._client(request.max_retries, request.timeout)
        messages = client.beta.messages if "betas" in params else client.messages
        try:
            with messages.stream(**params) as stream:
                message = stream.get_final_message()
        except anthropic.APIStatusError as exc:
            raise status_error(exc.status_code, request.model, str(exc.message)) from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError("Anthropic 서버에 연결할 수 없습니다.") from exc

        if message.stop_reason == "refusal":
            details = getattr(message, "stop_details", None)
            category = getattr(details, "category", None) if details else None
            raise LLMError(f"LLM이 요청을 거부했습니다 (분류: {category or '미상'}).")
        if message.stop_reason == "max_tokens":
            raise LLMError("응답이 최대 출력 토큰에 도달해 잘렸습니다. 최대 출력 토큰을 늘리세요.")
        text = "".join(block.text for block in message.content if block.type == "text")
        usage = message.usage
        return LLMResponse(
            text=text,
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
            raw={"id": message.id, "model": message.model, "stop_reason": message.stop_reason},
        )
