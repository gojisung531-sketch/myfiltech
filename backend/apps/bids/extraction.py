"""EXTRACT_BID: attachments → notice metadata, items and key requirements (specs/08 §2)."""

import hashlib
import json
import logging
import re
from datetime import datetime

from django.db import transaction
from django.utils import timezone

from apps.company.models import FilterType
from apps.core.app_settings import get_setting
from apps.core.units import parse_airflow, parse_dimension, parse_pressure
from apps.documents.extractors.company import classify_filter_type
from apps.documents.llm_steps import pdf_input
from apps.documents.models import Document
from apps.documents.pipeline import run_pipeline
from apps.evaluation.context import EvaluationContext
from apps.evaluation.matching import match_items, update_fit
from apps.llm.models import PromptTemplate
from apps.llm.prompt_defaults import REQUIREMENT_CATEGORIES
from apps.llm.prompts import render
from apps.llm.services import ensure_llm_configured, run_task, task_config

from .models import BidAttachment, BidItem, BidNotice, BidRequirement, RequirementCategory
from .services import ensure_primary

logger = logging.getLogger(__name__)

# Attachment order and whether long legal text is excerpted (specs/06 §2.3, specs/07 §2).
ROLE_PRIORITY = {
    "bid_notice": 0,
    "bid_spec": 1,
    "bid_item_list": 2,
    "bid_drawing": 3,
    "bid_restriction_reason": 4,
    "bid_contract_terms": 5,
    "bid_evaluation_criteria": 6,
}
EXCERPT_ROLES = {"bid_contract_terms", "bid_evaluation_criteria"}
EXCERPT_CONTEXT_LINES = 2
EXCERPT_MAX_CHARS = 6000
PROMPT_OVERHEAD_CHARS = 6000

NOTICE_NO_PATTERN = re.compile(r"입찰\s*공고\s*번호\s*[:：]?\s*(\d{11}-\d{2})")
DATETIME_FIELDS = ["bid_open_at", "bid_close_at", "opening_at", "qualification_deadline_at"]
INT_FIELDS = ["budget_krw", "estimated_price_krw"]
TEXT_FIELDS = [
    "notice_no",
    "title",
    "buyer_org",
    "contracting_org",
    "plant_name",
    "bid_method",
    "item_category_code",
    "item_category_name",
    "delivery_terms",
    "delivery_place",
    "warranty_terms",
    "summary",
]

# Categories that must exist after extraction; otherwise a placeholder is added (specs/08 §2).
REQUIRED_CATEGORY_GROUPS = [
    ("DIMENSION",),
    ("FILTER_GRADE", "EFFICIENCY"),
    ("PRESSURE_DROP",),
    ("TEST_STANDARD",),
    ("CERTIFICATION",),
    ("DELIVERY",),
    ("SUBMISSION_DOC",),
]


class BidExtractionError(Exception):
    pass


# ---- input building ---------------------------------------------------------------


def excerpt(text: str, keywords: list[str]) -> str:
    """Lines containing a keyword plus a little context, for long legal attachments."""
    lines = text.splitlines()
    keep: set[int] = set()
    for index, line in enumerate(lines):
        if any(k in line for k in keywords):
            keep.update(
                range(
                    max(0, index - EXCERPT_CONTEXT_LINES),
                    min(len(lines), index + EXCERPT_CONTEXT_LINES + 1),
                )
            )
    if not keep:
        return ""
    parts, previous = [], None
    for index in sorted(keep):
        if previous is not None and index != previous + 1:
            parts.append("…")
        parts.append(lines[index])
        previous = index
    result = "\n".join(parts)
    return result[:EXCERPT_MAX_CHARS]


def build_attachment_inputs(bid: BidNotice, *, require_all: bool = False) -> list[dict]:
    """Attachment texts in priority order within llm.max_input_chars (specs/07 §2)."""
    keywords = get_setting("extraction.excerpt_keywords")
    budget = max(10_000, get_setting("llm.max_input_chars") - PROMPT_OVERHEAD_CHARS)
    attachments = sorted(
        bid.attachments.select_related("document"),
        key=lambda a: (not a.is_primary, ROLE_PRIORITY.get(a.role, 9), a.order, a.pk),
    )
    inputs = []
    for attachment in attachments:
        document = attachment.document
        text = document.extracted_text or ""
        note = ""
        if require_all and not text.strip():
            if document.file_format == "PDF" and document.file:
                text = "원본 PDF가 같은 파일명으로 직접 첨부되어 있습니다. PDF 내용을 읽으세요. 전사문은 없습니다."
                note = " (원본 PDF 직접 입력)"
            else:
                raise BidExtractionError(f"읽을 수 없는 첨부가 있습니다: {document.display_name}")
        if require_all and document.file_format != "PDF":
            note += " (물리 페이지 미확인; source.page는 0)"
        if attachment.role in EXCERPT_ROLES and text:
            text = excerpt(text, keywords)
            note = " (핵심 조항 발췌)"
        if not text.strip():
            continue
        if len(text) > budget:
            if require_all:
                raise BidExtractionError(
                    "입력 한도로 첨부 전체를 포함할 수 없습니다. 범위를 확인하세요."
                )
            omitted = len(text) - budget
            text = text[:budget] + f"\n[입력 한도로 이 첨부의 뒷부분 {omitted:,}자를 생략했습니다.]"
        budget -= len(text)
        inputs.append(
            {
                "name": document.original_filename or document.display_name,
                "category": (document.category.name if document.category else "기타") + note,
                "text": text,
            }
        )
        if budget <= 0 and not require_all:
            break
    return inputs


def extraction_files(bid: BidNotice, inputs: list[dict]) -> list:
    """An unread PDF must reach bid.extract itself, even if no transcript was generated."""
    names = {i["name"] for i in inputs}
    files = []
    for attachment in bid.attachments.select_related("document"):
        document = attachment.document
        if document.extracted_text.strip() or document.file_format != "PDF":
            continue
        if document.original_filename not in names:
            raise BidExtractionError("스캔 PDF가 통합 추출 입력에서 누락되었습니다.")
        model = task_config("bid.extract").model
        if not model or not model.supports_pdf_input:
            raise BidExtractionError("공고 추출 모델이 원본 PDF 입력을 지원하지 않습니다.")
        original = pdf_input(document)
        if not original:
            raise BidExtractionError("스캔 PDF 원본 파일을 읽을 수 없습니다.")
        files.extend(original)
    return files


def source_page(source: dict, attachment: BidAttachment | None) -> int | None:
    """Only PDF page numbers have a known physical page mapping here."""
    page = source.get("page")
    if (
        attachment is not None
        and attachment.document.file_format == "PDF"
        and isinstance(page, int)
        and not isinstance(page, bool)
        and 0 < page <= (attachment.document.page_count or 0)
    ):
        return page
    return None


# ---- post-processing ----------------------------------------------------------------


def parse_datetime_kst(value) -> datetime | None:
    if not value:
        return None
    text = str(value).strip().replace("/", "-").replace(".", "-")
    text = re.sub(r"\s+", " ", text)
    for candidate in (text, text.replace(" ", "T")):
        try:
            parsed = datetime.fromisoformat(candidate)
            break
        except ValueError:
            parsed = None
    if parsed is None:
        match = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T](\d{1,2}):(\d{2}))?", text)
        if not match:
            return None
        y, m, d, hh, mm = match.groups()
        parsed = datetime(int(y), int(m), int(d), int(hh or 0), int(mm or 0))
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_default_timezone())
    return parsed


def _json(value) -> dict:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        decoded = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {"raw": str(value)}
    return decoded if isinstance(decoded, dict) else {"value": decoded}


def normalize_requirement(category: str, text: str, normalized: dict) -> dict:
    """Re-check units with apps.core.units; the rule value wins on >1% disagreement."""
    raw = normalized.get("raw") or text or ""
    if category == "PRESSURE_DROP":
        computed = parse_pressure(raw) or parse_pressure(text)
        value = normalized.get("value")
        if computed is not None:
            if not isinstance(value, (int, float)) or abs(value - computed) > computed * 0.01:
                normalized["value"] = computed
                normalized["unit_corrected"] = value is not None
            normalized["unit"] = "Pa"
        if not normalized.get("at_airflow_m3h"):
            airflow = parse_airflow(text)
            if airflow:
                normalized["at_airflow_m3h"] = airflow
    elif category == "AIRFLOW":
        computed = parse_airflow(raw) or parse_airflow(text)
        value = normalized.get("value")
        if computed is not None:
            if not isinstance(value, (int, float)) or abs(value - computed) > computed * 0.01:
                normalized["value"] = computed
                normalized["unit_corrected"] = value is not None
            normalized["unit"] = "m3/h"
    elif category == "DELIVERY":
        months = normalized.get("months_after_contract")
        if (
            not normalized.get("days_after_contract")
            and isinstance(months, (int, float))
            and months
        ):
            normalized["days_after_contract"] = int(months * 30)
    elif category == "DIMENSION" and not any(normalized.get(k) for k in ("w", "dia")):
        dimension = parse_dimension(raw) or parse_dimension(text)
        if dimension:
            normalized.update({k: v for k, v in dimension.items() if v is not None})
    return normalized


def _attachment_by_name(bid: BidNotice) -> dict[str, BidAttachment]:
    return {
        (a.document.original_filename or a.document.display_name): a
        for a in bid.attachments.select_related("document")
    }


def apply_notice(bid: BidNotice, notice: dict, primary_text: str) -> None:
    locked = set(bid.locked_fields)
    for name in TEXT_FIELDS:
        value = (notice.get(name) or "").strip()
        if name in locked or not value:
            continue
        max_length = bid._meta.get_field(name).max_length
        setattr(bid, name, value[:max_length] if max_length else value)
    for name in INT_FIELDS:
        if name not in locked:
            setattr(bid, name, int(notice.get(name) or 0) or None)
    for name in DATETIME_FIELDS:
        if name not in locked:
            setattr(bid, name, parse_datetime_kst(notice.get(name)))
    match = NOTICE_NO_PATTERN.search(primary_text or "")
    if match and "notice_no" not in locked:
        bid.notice_no = match.group(1)
    if "is_power_plant" not in locked:
        keywords = get_setting("fit.power_plant_keywords")
        text = f"{bid.title} {bid.buyer_org} {bid.plant_name}"
        bid.is_power_plant = bool(notice.get("is_power_plant")) or any(k in text for k in keywords)


def upsert_items(bid: BidNotice, items: list[dict], attachments: dict) -> dict[str, BidItem]:
    existing = {i.item_no or i.name: i for i in bid.items.all()}
    seen: dict[str, BidItem] = {}
    for data in items:
        name = (data.get("name") or "").strip()
        if not name:
            continue
        key = (data.get("item_no") or "").strip() or name
        item = existing.get(key) or BidItem(bid=bid)
        item.item_no = (data.get("item_no") or "").strip()
        item.name = name[:300]
        item.spec_text = data.get("spec_text") or ""
        filter_type = data.get("filter_type") or ""
        item.filter_type = filter_type if filter_type in FilterType.values else ""
        if not item.filter_type:
            guessed = classify_filter_type(f"{item.name} {item.spec_text}")
            item.filter_type = guessed if guessed != "OTHER" else ""
        dimension = _json(data.get("dimension_json"))
        if not any(dimension.get(k) for k in ("w", "dia", "len")):
            dimension = parse_dimension(item.spec_text) or {}
        item.width_mm, item.height_mm, item.depth_mm = (
            dimension.get("w"),
            dimension.get("h"),
            dimension.get("d"),
        )
        item.depth_mm_max = dimension.get("d_max")
        item.diameter_mm, item.diameter2_mm, item.length_mm = (
            dimension.get("dia"),
            dimension.get("dia2"),
            dimension.get("len"),
        )
        item.quantity = data.get("quantity") or None
        item.unit = (data.get("unit") or "")[:20]
        item.material_no = (data.get("material_no") or "")[:50]
        source = data.get("source") or {}
        item.source_attachment = attachments.get(source.get("attachment") or "")
        item.save()
        seen[item.item_no or item.name] = item
    locked_item_ids = set(bid.requirements.filter(is_locked=True).values_list("item_id", flat=True))
    for key, item in existing.items():
        if key not in seen and item.pk not in locked_item_ids:
            item.delete()
    return seen


def replace_requirements(
    bid: BidNotice, requirements: list[dict], items: dict[str, BidItem], attachments: dict
) -> int:
    bid.requirements.filter(is_locked=False).delete()
    order = bid.requirements.count()
    valid = set(REQUIREMENT_CATEGORIES)
    created = 0
    for data in requirements:
        category = data.get("category") if data.get("category") in valid else "OTHER"
        text = (data.get("requirement_text") or "").strip()
        normalized = normalize_requirement(category, text, _json(data.get("normalized_json")))
        source = data.get("source") or {}
        attachment = attachments.get(source.get("attachment") or "")
        BidRequirement.objects.create(
            bid=bid,
            item=items.get((data.get("item_no") or "").strip()),
            category=category,
            title=(data.get("title") or text[:50] or category)[:200],
            requirement_text=text,
            normalized=normalized,
            is_mandatory=bool(data.get("is_mandatory", True)),
            source_attachment=attachment,
            source_page=source_page(source, attachment),
            source_quote=(source.get("quote") or "")[:2000],
            order=order + created,
            source=BidRequirement.Source.LLM,
        )
        created += 1
    return created


def add_placeholders(bid: BidNotice) -> list[str]:
    present = set(bid.requirements.values_list("category", flat=True))
    added = []
    order = bid.requirements.count()
    for group in REQUIRED_CATEGORY_GROUPS:
        if present & set(group):
            continue
        label = RequirementCategory(group[0]).label
        BidRequirement.objects.create(
            bid=bid,
            category=group[0],
            title=f"{label} 요구사항 미확인",
            requirement_text=f"추출 결과에서 {label} 요구조건을 확인하지 못함 — 원문 확인 필요",
            normalized={"placeholder": True},
            is_mandatory=False,
            order=order + len(added),
            source=BidRequirement.Source.RULE,
        )
        added.append(group[0])
    return added


def review_sources(bid: BidNotice) -> dict:
    """Check quote correspondence, not technical correctness or PDF visual content."""

    def squash(value):
        return re.sub(r"\s+", "", value)

    def unquote(value):
        return squash(value).translate(str.maketrans("", "", "\"'“”‘’"))

    counts, rows = {}, []
    for requirement in bid.requirements.select_related("source_attachment__document"):
        attachment = requirement.source_attachment
        quote = requirement.source_quote
        if requirement.normalized.get("placeholder"):
            state = "PLACEHOLDER"
        elif attachment is None:
            state = "MISSING_ATTACHMENT"
        elif not quote.strip():
            state = "MISSING_QUOTE"
        else:
            document = attachment.document
            text = document.extracted_text
            if quote in text:
                state = "EXACT_TEXT"
            elif squash(quote) in squash(text):
                state = "WHITESPACE_MATCH"
            elif unquote(quote) and unquote(quote) in unquote(text):
                state = "QUOTATION_MARK_DIFFERENCE"
            elif document.file_format == "PDF" and not text.strip():
                state = "PDF_VISUAL_REVIEW_REQUIRED"
            else:
                state = "QUOTE_NOT_FOUND"
        counts[state] = counts.get(state, 0) + 1
        rows.append(
            {
                "requirement_id": requirement.pk,
                "attachment_id": attachment.pk if attachment else None,
                "quote_status": state,
            }
        )
    return {"counts": counts, "requirements": rows, "technical_review_completed": False}


# ---- job ---------------------------------------------------------------------------


def process_attachments(
    bid: BidNotice, job=None, report=lambda p, m="": None, *, parse_only: bool = False
) -> None:
    attachments = list(bid.attachments.select_related("document"))
    for index, attachment in enumerate(attachments, start=1):
        document = attachment.document
        report(
            5 + int(35 * index / max(1, len(attachments))), f"첨부 처리 중: {document.display_name}"
        )
        if document.status not in (Document.Status.EXTRACTED, Document.Status.REVIEWED):
            if parse_only:
                # add_attachment already parses and rule-classifies without any paid calls.
                from .services import _quick_process

                _quick_process(document)
                document.refresh_from_db()
                if document.status == Document.Status.FAILED:
                    raise BidExtractionError(f"첨부 읽기 실패: {document.display_name}")
            else:
                from_step = (
                    "classify"
                    if (document.extracted_text or document.status == Document.Status.NEEDS_OCR)
                    else "parse"
                )
                run_pipeline(document, from_step=from_step, apply=False, job=job)
                document.refresh_from_db()
        role = document.category.code if document.category else ""
        if attachment.role != role:
            attachment.role = role
            attachment.save(update_fields=["role"])
    ensure_primary(bid)


def validate_extraction_only_target(bid: BidNotice) -> None:
    if bid.processing_status not in (
        BidNotice.ProcessingStatus.DRAFT,
        BidNotice.ProcessingStatus.FAILED,
    ):
        raise BidExtractionError(
            "등록/실패 상태의 공고만 실행합니다. 완료 결과를 반복 호출하지 않습니다."
        )
    if (
        bid.fit_score is not None
        or bid.items.filter(matched_product__isnull=False).exists()
        or bid.requirements.filter(is_locked=True).exists()
        or bid.requirements.filter(source=BidRequirement.Source.MANUAL).exists()
        or bid.requirements.filter(evaluation__isnull=False).exists()
        or bid.drafts.exists()
    ):
        raise BidExtractionError(
            "기존 매칭·적합도·수동 요구조건·판정·초안이 있어 재추출하지 않습니다."
        )


def extract_bid(
    bid: BidNotice, *, job=None, report=lambda p, m="": None, extraction_only: bool = False
) -> dict:
    if extraction_only:
        validate_extraction_only_target(bid)
    ensure_llm_configured()
    bid.processing_status = BidNotice.ProcessingStatus.EXTRACTING
    bid.processing_error = ""
    bid.save(update_fields=["processing_status", "processing_error", "updated_at"])
    try:
        process_attachments(bid, job=job, report=report, parse_only=extraction_only)
        inputs = build_attachment_inputs(bid, require_all=extraction_only)
        files = extraction_files(bid, inputs)
        if not inputs:
            raise BidExtractionError("텍스트를 추출한 첨부가 없습니다. 첨부 파일을 확인하세요.")
        report(45, "공고 통합 추출 중 (LLM)")
        template = PromptTemplate.active("bid.extract")
        cfg = task_config("bid.extract")
        variables = {
            "attachments": inputs,
            "today": timezone.localdate().isoformat(),
            "requirement_categories": REQUIREMENT_CATEGORIES,
        }
        limit = get_setting("llm.max_input_chars")
        if extraction_only and template and limit:
            if len(render(template.user_prompt_template, variables)) > limit:
                raise BidExtractionError(
                    "통합 프롬프트가 입력 한도를 초과해 첨부가 잘릴 수 있습니다."
                )
        response = run_task(
            "bid.extract",
            variables,
            files=files,
            template=template,
            job=job,
        )
        data = response.data
        report(80, "추출 결과 정리 중")
        primary = bid.attachments.filter(is_primary=True).select_related("document").first()
        with transaction.atomic():
            attachments = _attachment_by_name(bid)
            apply_notice(
                bid, data.get("notice") or {}, primary.document.extracted_text if primary else ""
            )
            items = upsert_items(bid, data.get("items") or [], attachments)
            created = replace_requirements(bid, data.get("requirements") or [], items, attachments)
            placeholders = add_placeholders(bid)
            bid.extra = {
                **(bid.extra or {}),
                "placeholders": placeholders,
                "extraction_run": {
                    "scope": "REQUIREMENTS_ONLY" if extraction_only else "FULL",
                    "completed_at": timezone.now().isoformat(),
                    "llm_call_id": response.call_log.pk if response.call_log else None,
                    "prompt_version": template.version if template else None,
                    "system_sha256": hashlib.sha256(response.system.encode()).hexdigest(),
                    "user_sha256": hashlib.sha256(response.user.encode()).hexdigest(),
                    "provider": cfg.provider,
                    "model": cfg.model_id,
                    "temperature": cfg.temperature,
                    "max_output_tokens": cfg.max_output_tokens,
                    "timeout_sec": cfg.timeout_sec,
                    "max_retries": cfg.max_retries,
                    "effort": cfg.effort,
                    "max_input_chars": get_setting("llm.max_input_chars"),
                    "attachments": [
                        {
                            "id": a.pk,
                            "document_id": a.document_id,
                            "sha256": a.document.sha256,
                            "text_sha256": hashlib.sha256(
                                a.document.extracted_text.encode()
                            ).hexdigest(),
                            "input_mode": "ORIGINAL_PDF"
                            if any(f.filename == a.document.original_filename for f in files)
                            else "STORED_TEXT",
                        }
                        for a in bid.attachments.select_related("document")
                    ],
                },
            }
            bid.extra["extraction_source_review"] = review_sources(bid)
            bid.save()
        if not extraction_only:
            report(90, "제품 매칭·적합도 계산 중")
            ctx = EvaluationContext.for_bid(bid)
            match_items(bid, ctx)
            update_fit(bid, ctx, job=job)
    except Exception as exc:
        bid.processing_status = BidNotice.ProcessingStatus.FAILED
        bid.processing_error = (
            str(exc)[:2000] if not isinstance(exc, BidExtractionError) else str(exc)
        )
        bid.save(update_fields=["processing_status", "processing_error", "updated_at"])
        raise
    bid.processing_status = BidNotice.ProcessingStatus.EXTRACTED
    bid.save(update_fields=["processing_status", "updated_at"])
    return {
        "bid_id": bid.pk,
        "items": len(items),
        "requirements": created,
        "placeholders": placeholders,
        "fit_score": None if extraction_only else bid.fit_score,
    }
