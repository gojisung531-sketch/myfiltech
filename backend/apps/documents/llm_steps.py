"""LLM fallbacks for the document pipeline (specs/06 §2.2, §3.3, §5.2).

These never raise for LLM problems: the caller keeps the rule results and records a note.
"""

import logging
from pathlib import Path

from apps.llm.providers import LLMError
from apps.llm.providers.base import FileInput
from apps.llm.schemas import decode_field_value, metadata_output_schema
from apps.llm.services import LLMNotConfigured, is_llm_configured, run_task

from .extractors import MetaValue
from .models import Document, MetadataSchema

logger = logging.getLogger(__name__)

RULE_CONFIDENCE_THRESHOLD = 0.8
CLASSIFY_HEAD_CHARS = 4000


class LLMStepSkipped(Exception):
    """LLM is unavailable or failed; message is a Korean note for the document."""


def pdf_input(document: Document) -> list[FileInput]:
    if not document.file or document.file_format != "PDF":
        return []
    return [
        FileInput(
            filename=document.original_filename or Path(document.file.name).name,
            data=Path(document.file.path).read_bytes(),
        )
    ]


def _run(task_key: str, variables: dict, **kwargs):
    if not is_llm_configured():
        raise LLMStepSkipped("LLM 미설정 — LLM 단계는 보류되었습니다. LLM 설정 후 다시 추출하세요.")
    try:
        return run_task(task_key, variables, **kwargs).data
    except (LLMError, LLMNotConfigured) as exc:
        logger.warning("LLM step %s failed: %s", task_key, exc)
        raise LLMStepSkipped(f"LLM 처리 실패 — {exc}") from exc


def classify_variables(document: Document, files: list[FileInput]) -> dict:
    schemas = MetadataSchema.objects.filter(is_active=True, owner_type=document.owner_type)
    return {
        "categories": [
            {"code": s.code, "name": s.name, "description": s.description} for s in schemas
        ],
        "filename": document.original_filename or document.title,
        "text_head": (document.extracted_text or "")[:CLASSIFY_HEAD_CHARS],
        "has_file": bool(files),
    }


def extract_variables(document: Document, fields: list[dict], files: list[FileInput]) -> dict:
    schema = document.category
    return {
        "category": {"code": schema.code, "name": schema.name, "description": schema.description},
        "fields": fields,
        "text": document.extracted_text or "",
        "has_file": bool(files),
    }


def test_inputs(task_key: str, document: Document) -> tuple[dict, list[FileInput], dict | None]:
    """Variables/files/schema for running a document prompt against a real document."""
    files = pdf_input(document) if not (document.extracted_text or "").strip() else []
    if task_key == "document.classify":
        return classify_variables(document, files), files, None
    if task_key == "document.extract_metadata":
        if document.category is None:
            raise ValueError("문서 분류가 없는 문서입니다. 분류를 먼저 지정하세요.")
        fields = document.category.fields or []
        return extract_variables(document, fields, files), files, metadata_output_schema(fields)
    raise ValueError("이 프롬프트는 문서로 테스트할 수 없습니다. 변수를 직접 입력하세요.")


def llm_classify(document: Document, *, files: list[FileInput], job=None):
    """Return (schema, confidence) chosen by the LLM, or (None, None)."""
    schemas = list(MetadataSchema.objects.filter(is_active=True, owner_type=document.owner_type))
    data = _run("document.classify", classify_variables(document, files), files=files, job=job)
    by_code = {s.code: s for s in schemas}
    schema = by_code.get(data.get("code") or "")
    return (schema, float(data.get("confidence") or 0)) if schema else (None, None)


def llm_extract(
    document: Document, fields: list[dict], *, files: list[FileInput], job=None
) -> tuple[dict[str, MetaValue], str | None]:
    """Extract `fields` with the LLM. Returns ({key: MetaValue}, transcript)."""
    data = _run(
        "document.extract_metadata",
        extract_variables(document, fields, files),
        files=files,
        output_schema=metadata_output_schema(fields),
        job=job,
    )
    values: dict[str, MetaValue] = {}
    by_key = {f["key"]: f for f in fields}
    for item in data.get("fields") or []:
        field = by_key.get(item.get("key")) if isinstance(item, dict) else None
        if field is None:
            continue
        key = field["key"]
        value = decode_field_value(field, item.get("value"))
        if value is None:
            continue
        values[key] = MetaValue(
            value=value,
            raw=item.get("raw") or "",
            confidence=float(item.get("confidence") or 0),
            page=item.get("page") or None,
            quote=item.get("quote") or "",
        )
    return values, data.get("transcript") or None
