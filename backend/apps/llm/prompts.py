"""Prompt rendering with a sandboxed Jinja2 environment (specs/07 §2)."""

import json

from jinja2 import StrictUndefined, TemplateError
from jinja2.sandbox import SandboxedEnvironment

from .providers import LLMError

_env = SandboxedEnvironment(undefined=StrictUndefined, autoescape=False, keep_trailing_newline=True)
_env.filters["tojson"] = lambda value: json.dumps(value, ensure_ascii=False, default=str)


def render(template: str, variables: dict) -> str:
    try:
        return _env.from_string(template).render(**variables)
    except TemplateError as exc:
        raise LLMError(f"프롬프트 템플릿 오류: {exc}") from exc


def check_syntax(template: str) -> str | None:
    """Return an error message when the template does not parse."""
    try:
        _env.parse(template)
    except TemplateError as exc:
        return str(exc)
    return None
