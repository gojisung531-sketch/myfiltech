import base64

import openai

from .base import (
    VERIFY_MAX_TOKENS,
    VERIFY_PROMPT,
    LLMError,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    status_error,
)


class OpenAIProvider(LLMProvider):
    def _client(self, max_retries: int = 0, timeout: int | None = None) -> openai.OpenAI:
        return openai.OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=timeout or self.timeout,
            max_retries=max_retries,
        )

    def verify(self, model: str) -> None:
        try:
            self._client().responses.create(
                model=model, input=VERIFY_PROMPT, max_output_tokens=VERIFY_MAX_TOKENS
            )
        except openai.APIStatusError as exc:
            raise status_error(exc.status_code, model, str(exc.message)) from exc
        except openai.APIConnectionError as exc:
            raise LLMError("OpenAI 서버에 연결할 수 없습니다.") from exc

    def build_params(self, request: LLMRequest, *, with_temperature: bool = True) -> dict:
        content: list[dict] = [
            {
                "type": "input_file",
                "filename": f.filename,
                "file_data": f"data:{f.mime_type};base64,{base64.b64encode(f.data).decode()}",
            }
            for f in request.files
        ]
        content.append({"type": "input_text", "text": request.user})
        params: dict = {
            "model": request.model,
            "instructions": request.system,
            "input": [{"role": "user", "content": content}],
            "max_output_tokens": request.max_output_tokens,
        }
        if with_temperature and request.temperature is not None:
            params["temperature"] = request.temperature
        if request.json_schema:
            params["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": "result",
                    "schema": request.json_schema,
                    "strict": True,
                }
            }
        return params

    def generate(self, request: LLMRequest) -> LLMResponse:
        client = self._client(request.max_retries, request.timeout)
        try:
            try:
                response = client.responses.create(**self.build_params(request))
            except openai.BadRequestError as exc:
                # Some models reject sampling parameters; retry once without them.
                if request.temperature is None or "temperature" not in str(exc.message):
                    raise
                response = client.responses.create(
                    **self.build_params(request, with_temperature=False)
                )
        except openai.APIStatusError as exc:
            raise status_error(exc.status_code, request.model, str(exc.message)) from exc
        except openai.APIConnectionError as exc:
            raise LLMError("OpenAI 서버에 연결할 수 없습니다.") from exc

        if getattr(response, "status", None) == "incomplete":
            raise LLMError("응답이 최대 출력 토큰에 도달해 잘렸습니다. 최대 출력 토큰을 늘리세요.")
        usage = getattr(response, "usage", None)
        return LLMResponse(
            text=response.output_text or "",
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
            raw={"id": response.id, "model": response.model},
        )
