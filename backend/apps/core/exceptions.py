"""Uniform API error body: {"detail": str, "code": str, "errors": {field: [..]}} (specs/01 §6)."""

from rest_framework.exceptions import ValidationError
from rest_framework.views import exception_handler


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return None

    data = response.data
    if isinstance(exc, ValidationError):
        errors = data if isinstance(data, dict) else {"non_field_errors": data}
        body = {"detail": "입력값을 확인하세요.", "code": "invalid", "errors": errors}
    else:
        detail = data.get("detail", "") if isinstance(data, dict) else data
        code = getattr(getattr(exc, "detail", None), "code", None) or getattr(
            exc, "default_code", "error"
        )
        body = {"detail": str(detail), "code": code}
    response.data = body
    return response
