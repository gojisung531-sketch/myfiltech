"""Single entry point for LLM operations (CLAUDE.md: views must not import SDKs)."""

import fnmatch
import json
import logging
import time
from dataclasses import dataclass

from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException

from apps.core.app_settings import get_setting
from apps.core.logging import mask_secrets

from .crypto import DecryptionError
from .models import LLMCallLog, LLMModelOption, LLMProviderConfig, LLMSettings, PromptTemplate
from .prompts import render
from .providers import LLMError, get_provider_class
from .providers.base import FileInput, LLMRequest, parse_json_text
from .schemas import validation_errors

logger = logging.getLogger(__name__)

VERIFY_TIMEOUT_SEC = 30
EXCERPT_CHARS = 2000


class LLMNotConfigured(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "LLM API Key가 설정되지 않았습니다. 관리자에게 문의하세요."
    default_code = "llm_not_configured"


class LLMInvalidOutput(LLMError):
    """The model did not return schema-valid JSON even after one repair request."""


@dataclass
class VerifyResult:
    ok: bool
    message: str
    model_id: str


@dataclass
class TaskConfig:
    provider: str
    model: LLMModelOption | None
    model_id: str
    temperature: float
    max_output_tokens: int
    timeout_sec: int
    max_retries: int
    effort: str | None


# ---- configuration state -----------------------------------------------------------


def is_llm_configured() -> bool:
    """Active provider exists, is enabled and has an API key (specs/03 §4)."""
    active_provider = LLMSettings.load().active_provider
    config = LLMProviderConfig.objects.filter(provider=active_provider).first()
    return bool(config and config.is_enabled and config.has_api_key)


def ensure_llm_configured() -> None:
    """Call at the start of any endpoint that needs the LLM; raises 409 llm_not_configured."""
    if not is_llm_configured():
        raise LLMNotConfigured()


def resolve_model(provider: str) -> LLMModelOption | None:
    """Model used for `provider`: the active model if it belongs to it, else its default."""
    settings_row = LLMSettings.load()
    model = settings_row.active_model
    if model and model.provider == provider and model.is_active:
        return model
    options = LLMModelOption.objects.filter(provider=provider, is_active=True)
    return options.filter(is_default=True).first() or options.first()


def task_overrides(task_key: str, overrides: dict) -> dict:
    """Exact key first, then glob patterns such as 'draft.*' (specs/07 §2)."""
    if task_key in overrides:
        return overrides[task_key]
    for pattern, values in overrides.items():
        if fnmatch.fnmatchcase(task_key, pattern):
            return values
    return {}


def task_config(task_key: str) -> TaskConfig:
    settings_row = LLMSettings.load()
    provider = settings_row.active_provider
    override = task_overrides(task_key, settings_row.per_task_overrides or {})
    model = resolve_model(provider)
    if override.get("model"):
        model = (
            LLMModelOption.objects.filter(provider=provider, model_id=override["model"]).first()
            or model
        )
    model_id = override.get("model") or (model.model_id if model else "")
    max_tokens = int(override.get("max_output_tokens") or settings_row.max_output_tokens)
    if model and model.max_output_tokens:
        max_tokens = min(max_tokens, model.max_output_tokens)
    return TaskConfig(
        provider=provider,
        model=model,
        model_id=model_id,
        temperature=float(override.get("temperature", settings_row.temperature)),
        max_output_tokens=max_tokens,
        timeout_sec=settings_row.timeout_sec,
        max_retries=settings_row.max_retries,
        effort=override.get("effort"),
    )


def active_model_supports_pdf() -> bool:
    if not is_llm_configured():
        return False
    model = task_config("document.extract_metadata").model
    return bool(model and model.supports_pdf_input)


def _provider_for(config: LLMProviderConfig, timeout: int):
    return get_provider_class(config.provider)(
        api_key=config.get_api_key(), base_url=config.base_url, timeout=timeout
    )


# ---- connection test ---------------------------------------------------------------


def verify_provider(config: LLMProviderConfig, model_id: str | None = None) -> VerifyResult:
    """Send a minimal request with the stored key and record the outcome on `config`."""
    if not model_id:
        model = resolve_model(config.provider)
        model_id = model.model_id if model else ""
    if not config.has_api_key:
        result = VerifyResult(False, "API Key가 저장되어 있지 않습니다.", model_id)
    elif not model_id:
        result = VerifyResult(False, "사용 가능한 모델이 없습니다. 모델을 먼저 등록하세요.", "")
    else:
        try:
            _provider_for(config, VERIFY_TIMEOUT_SEC).verify(model_id)
            result = VerifyResult(True, f"연결 성공 ({model_id})", model_id)
        except (LLMError, DecryptionError) as exc:
            result = VerifyResult(False, str(exc), model_id)

    config.last_verified_at = timezone.now()
    config.last_verify_ok = result.ok
    config.last_verify_error = "" if result.ok else result.message
    config.save(update_fields=["last_verified_at", "last_verify_ok", "last_verify_error"])
    return result


# ---- task execution ----------------------------------------------------------------


@dataclass
class TaskResult:
    data: dict
    raw_text: str
    system: str
    user: str
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int
    call_log: LLMCallLog | None = None


def _truncate(text: str, limit: int) -> str:
    if limit and len(text) > limit:
        omitted = len(text) - limit
        return text[:limit] + f"\n\n[입력이 길어 뒷부분 {omitted:,}자를 생략했습니다.]"
    return text


def _log(task_key, cfg, template, job, status, *, request_text, response=None, error="", latency):
    return LLMCallLog.objects.create(
        task_key=task_key,
        provider=cfg.provider,
        model_id=cfg.model_id,
        prompt_template=template if template and template.pk else None,
        prompt_version=template.version if template else None,
        request_tokens=getattr(response, "input_tokens", None),
        response_tokens=getattr(response, "output_tokens", None),
        latency_ms=latency,
        status=status,
        error=mask_secrets(error)[:2000],
        request_excerpt=mask_secrets(request_text[:EXCERPT_CHARS]),
        response_text=getattr(response, "text", "") or "",
        job=job,
    )


def _parse(text: str, schema: dict | None) -> tuple[dict | None, str]:
    try:
        data = parse_json_text(text)
    except (json.JSONDecodeError, TypeError) as exc:
        return None, f"JSON 파싱 실패: {exc}"
    errors = validation_errors(data, schema)
    if errors:
        return None, "스키마 불일치: " + "; ".join(errors)
    return data, ""


def run_task(
    task_key: str,
    variables: dict,
    *,
    files: list[FileInput] | None = None,
    output_schema: dict | None = None,
    template: PromptTemplate | None = None,
    log_key: str | None = None,
    job=None,
) -> TaskResult:
    """Render the active prompt for `task_key`, call the LLM and return schema-valid JSON.

    Raises LLMNotConfigured, LLMError (provider failure) or LLMInvalidOutput.
    `template` overrides the active one (used by the prompt test endpoint).
    """
    ensure_llm_configured()
    template = template or PromptTemplate.active(task_key)
    if template is None:
        raise LLMError(f"활성 프롬프트가 없습니다: {task_key}")
    schema = output_schema if output_schema is not None else template.output_schema
    cfg = task_config(task_key)
    if not cfg.model_id:
        raise LLMError("사용할 모델이 설정되지 않았습니다.")

    system = render(template.system_prompt, variables)
    user = _truncate(
        render(template.user_prompt_template, variables), get_setting("llm.max_input_chars")
    )
    config = LLMProviderConfig.objects.get(provider=cfg.provider)
    try:
        provider = _provider_for(config, cfg.timeout_sec)
    except DecryptionError as exc:
        raise LLMError(str(exc)) from exc

    log_key = log_key or task_key
    prompt = user
    last_error = ""
    for attempt in range(2):
        request = LLMRequest(
            system=system,
            user=prompt,
            model=cfg.model_id,
            temperature=cfg.temperature,
            max_output_tokens=cfg.max_output_tokens,
            json_schema=schema,
            files=files or [],
            timeout=cfg.timeout_sec,
            max_retries=cfg.max_retries,
            effort=cfg.effort,
        )
        started = time.monotonic()
        try:
            response = provider.generate(request)
        except LLMError as exc:
            latency = int((time.monotonic() - started) * 1000)
            _log(
                log_key,
                cfg,
                template,
                job,
                "ERROR",
                request_text=prompt,
                error=str(exc),
                latency=latency,
            )
            raise
        latency = int((time.monotonic() - started) * 1000)
        data, last_error = _parse(response.text, schema)
        if data is not None:
            call_log = _log(
                log_key,
                cfg,
                template,
                job,
                "OK",
                request_text=prompt,
                response=response,
                latency=latency,
            )
            return TaskResult(
                data=data,
                raw_text=response.text,
                system=system,
                user=user,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                latency_ms=latency,
                call_log=call_log,
            )
        _log(
            log_key,
            cfg,
            template,
            job,
            "INVALID_JSON",
            request_text=prompt,
            response=response,
            error=last_error,
            latency=latency,
        )
        if attempt == 0:
            prompt = (
                f"{user}\n\n[이전 응답 오류] {last_error}\n"
                "지정된 JSON 스키마에 맞는 JSON만 다시 출력하세요."
            )
    raise LLMInvalidOutput(f"LLM 응답 형식이 올바르지 않습니다. {last_error}")
