"""Output-schema validation and the dynamic metadata schema (specs/07 §2, specs/06 §5)."""

import json

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from .prompt_defaults import CONFIDENCE, I, S, obj

TEXT_TYPES = {"str", "date"}


def validation_errors(data, schema: dict | None) -> list[str]:
    if not schema:
        return []
    validator = Draft202012Validator(schema)
    return [
        f"{'/'.join(str(p) for p in error.absolute_path) or '(root)'}: {error.message}"
        for error in sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))[:10]
    ]


def schema_error(schema) -> str | None:
    if schema is None:
        return None
    if not isinstance(schema, dict):
        return "JSON Schema는 객체여야 합니다."
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        return exc.message
    return None


def metadata_output_schema(fields: list[dict]) -> dict:
    """Strict schema for document.extract_metadata built from a category's field defs.

    Found fields come back as an array of same-shaped items (specs/07 §2): a nested object
    per field makes Anthropic reject the schema ("compiled grammar is too large"). No union
    types: values are strings, non-text types JSON-encoded and decoded by decode_field_value().
    """
    item = obj(
        {
            "key": {"type": "string", "enum": [f["key"] for f in fields] or [""]},
            "value": S,
            "raw": S,
            "page": I,
            "quote": S,
            "confidence": CONFIDENCE,
        }
    )
    return obj({"fields": {"type": "array", "items": item}, "transcript": S})


def decode_field_value(field: dict, value):
    """Turn the string returned for a field into its typed value; "" means not found."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if not isinstance(value, str) or field.get("type", "str") in TEXT_TYPES:
        return value
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return value
    kind = field.get("type")
    if kind == "int" and isinstance(decoded, float) and decoded.is_integer():
        return int(decoded)
    return decoded


def count_union_types(schema) -> int:
    """Union/nullable parameters in a schema (Anthropic allows at most 16)."""
    if isinstance(schema, dict):
        own = int(isinstance(schema.get("type"), list) or "anyOf" in schema or "oneOf" in schema)
        return own + sum(count_union_types(v) for v in schema.values())
    if isinstance(schema, list):
        return sum(count_union_types(v) for v in schema)
    return 0
