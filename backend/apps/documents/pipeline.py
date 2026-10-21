"""Document pipeline: parse → classify → extract → map (specs/06 §1).

Each step can be re-run on its own via run_pipeline(from_step=...).
Rules run first; the LLM fills gaps when configured (specs/06 §2.2, §3, §5).
"""

import logging
from collections.abc import Callable

from django.db import transaction

from apps.core.app_settings import get_setting
from apps.llm.services import active_model_supports_pdf

from .classify import classify
from .extractors import EXTRACTORS, MetaValue
from .llm_steps import (
    RULE_CONFIDENCE_THRESHOLD,
    LLMStepSkipped,
    llm_classify,
    llm_extract,
    pdf_input,
)
from .models import Document, DocumentMetadata
from .parsers import ParseError, parse_file
from .parsers.base import normalize_text

logger = logging.getLogger(__name__)

STEPS = ["parse", "classify", "extract", "map"]

Report = Callable[[int, str], None]


def _noop(progress: int, message: str = "") -> None:
    pass


def _set_status(document: Document, status: str, error: str = "") -> None:
    document.status = status
    document.error_message = error
    document.save(update_fields=["status", "error_message", "updated_at"])


def parse_step(document: Document) -> bool:
    """Fill extracted_text/tables. Returns False when the pipeline should stop."""
    _set_status(document, Document.Status.PARSING)
    if not document.file:
        text = normalize_text(document.source_text)
        document.extracted_text, document.extracted_tables, document.page_count = text, [], None
        document.save(update_fields=["extracted_text", "extracted_tables", "page_count"])
        _set_status(document, Document.Status.PARSED)
        return True
    try:
        result = parse_file(
            document.file.path,
            document.file_format,
            min_chars_per_page=get_setting("extraction.min_text_chars_per_page"),
        )
    except ParseError as exc:
        _set_status(document, Document.Status.FAILED, str(exc))
        return False
    document.extracted_text = result.text
    document.extracted_tables = result.tables
    document.page_count = result.page_count
    document.save(update_fields=["extracted_text", "extracted_tables", "page_count"])
    if result.is_scanned and not active_model_supports_pdf():
        _set_status(document, Document.Status.NEEDS_OCR, NEEDS_OCR_MESSAGE)
        return False
    _set_status(document, Document.Status.PARSED)
    return True


NEEDS_OCR_MESSAGE = "스캔 문서입니다. 텍스트를 직접 입력하거나, PDF 입력을 지원하는 LLM 모델을 설정한 뒤 다시 처리하세요."


def is_scanned(document: Document) -> bool:
    """A PDF whose text layer is empty; handled by sending the PDF itself to the LLM."""
    return (
        document.file_format == "PDF"
        and bool(document.file)
        and not document.extracted_text.strip()
    )


def classify_step(document: Document, path_hint: str | None = None, job=None) -> list[str]:
    """Rules first; the LLM classifies when rules fail or are unsure. Returns notes."""
    if document.category_source == Document.CategorySource.MANUAL and document.category_id:
        return []
    result = classify(
        filename=document.original_filename or document.title,
        text=document.extracted_text,
        owner_type=document.owner_type,
        path_hint=path_hint,
    )
    schema, confidence, notes = result.schema, result.confidence, []
    if schema is None or (confidence or 0) < RULE_CONFIDENCE_THRESHOLD:
        files = pdf_input(document) if is_scanned(document) else []
        try:
            llm_schema, llm_confidence = llm_classify(document, files=files, job=job)
            if llm_schema is not None and llm_confidence > (confidence or 0):
                schema, confidence = llm_schema, llm_confidence
        except LLMStepSkipped as exc:
            notes.append(str(exc))
    document.category = schema
    document.category_confidence = confidence
    document.category_source = Document.CategorySource.AUTO
    document.save(update_fields=["category", "category_confidence", "category_source"])
    return notes


def save_metadata(document: Document, values: dict[str, MetaValue], source: str) -> int:
    """Upsert extracted values; locked rows are never touched (specs/06 §5.3)."""
    schema = document.category
    locked = set(document.metadata.filter(is_locked=True).values_list("key", flat=True))
    saved = 0
    with transaction.atomic():
        document.metadata.filter(source=source, is_locked=False).exclude(
            key__in=list(values)
        ).delete()
        for key, item in values.items():
            if key in locked:
                continue
            field = schema.field(key) if schema else None
            DocumentMetadata.objects.update_or_create(
                document=document,
                key=key,
                defaults={
                    "label": (field or {}).get("label", key),
                    "value": item.value,
                    "raw_value": item.raw or "",
                    "unit": item.unit or (field or {}).get("unit", ""),
                    "source": source,
                    "confidence": item.confidence,
                    "evidence_page": item.page,
                    "evidence_quote": (item.quote or "")[:300],
                },
            )
            saved += 1
    return saved


def fields_for_llm(document: Document, rule_values: dict, has_extractor: bool) -> list[dict]:
    """No rule extractor (or a scanned PDF) → every field; otherwise only missing required
    fields, so documents the rules handle fully cost nothing (specs/06 §5.2)."""
    fields = document.category.fields or []
    if not has_extractor or is_scanned(document):
        return fields
    return [f for f in fields if f.get("required") and f["key"] not in rule_values]


def extract_step(document: Document, job=None) -> list[str]:
    """Rule extraction, then LLM for the gaps. Returns notes for the document."""
    if document.category is None:
        _set_status(
            document,
            Document.Status.PARSED,
            "문서 분류를 판별하지 못했습니다. 분류를 직접 지정한 뒤 다시 추출하세요.",
        )
        return []
    scanned = is_scanned(document)
    if scanned and not active_model_supports_pdf():
        _set_status(document, Document.Status.NEEDS_OCR, NEEDS_OCR_MESSAGE)
        return []
    _set_status(document, Document.Status.EXTRACTING)
    notes: list[str] = []
    extractor = EXTRACTORS.get(document.category.code)
    rule_values = {}
    if extractor is not None and not scanned:
        rule_values = extractor(document.extracted_text, document.extracted_tables)
    save_metadata(document, rule_values, DocumentMetadata.Source.RULE)

    llm_fields = fields_for_llm(document, rule_values, extractor is not None)
    if llm_fields:
        try:
            files = pdf_input(document) if scanned else []
            llm_values, transcript = llm_extract(document, llm_fields, files=files, job=job)
            if scanned and transcript:
                document.extracted_text = transcript
                document.save(update_fields=["extracted_text"])
            save_metadata(
                document,
                {k: v for k, v in llm_values.items() if k not in rule_values},
                DocumentMetadata.Source.LLM,
            )
        except LLMStepSkipped as exc:
            notes.append(str(exc))
            if scanned:
                _set_status(document, Document.Status.NEEDS_OCR, " ".join(notes))
                return notes
    _set_status(document, Document.Status.EXTRACTED, " ".join(notes))
    return notes


def map_step(document: Document) -> list[dict]:
    from apps.company.mapping import apply

    return [change.as_dict() for change in apply(document)]


def run_pipeline(
    document: Document,
    *,
    from_step: str = "parse",
    path_hint: str | None = None,
    apply: bool | None = None,
    report: Report = _noop,
    job=None,
) -> dict:
    """Run steps from `from_step`. Company documents are mapped when `apply` (or the
    extraction.auto_apply_company setting) is true."""
    if from_step not in STEPS:
        raise ValueError(f"unknown step: {from_step}")
    start = STEPS.index(from_step)
    result: dict = {"document_id": document.pk}

    if start <= 0:
        report(10, "텍스트 추출 중")
        if not parse_step(document):
            result["status"] = document.status
            return result
    notes: list[str] = []
    if start <= 1:
        report(40, "문서 분류 중")
        notes += classify_step(document, path_hint, job=job)
    if start <= 2:
        report(60, "메타데이터 추출 중")
        notes += extract_step(document, job=job)
        if notes and not document.error_message:
            document.error_message = " ".join(dict.fromkeys(notes))
            document.save(update_fields=["error_message"])

    should_map = apply if apply is not None else get_setting("extraction.auto_apply_company")
    if (
        start <= 3
        and should_map
        and document.owner_type == "COMPANY"
        and document.status == Document.Status.EXTRACTED
    ):
        report(85, "회사 자료에 반영 중")
        result["changes"] = map_step(document)
    document.refresh_from_db()
    result["status"] = document.status
    return result
