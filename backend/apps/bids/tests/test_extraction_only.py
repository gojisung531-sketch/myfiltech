"""Synthetic extraction boundaries: no company fixtures, SDK transport or downstream work."""

from io import StringIO
from unittest.mock import Mock

import pytest
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.bids import extraction, tasks
from apps.bids.models import BidAttachment, BidNotice
from apps.core.app_settings import set_setting
from apps.core.models import Job
from apps.documents.models import Document
from apps.documents.parsers.base import ParseResult
from apps.llm.models import LLMCallLog, LLMModelOption
from apps.llm.prompt_defaults import PROMPTS_BY_KEY

pytestmark = pytest.mark.django_db


def blank(schema):
    kind = schema["type"]
    if kind == "object":
        return {key: blank(value) for key, value in schema["properties"].items()}
    return {"array": [], "string": "", "boolean": False, "integer": 0, "number": 0}[kind]


def output():
    result = blank(PROMPTS_BY_KEY["bid.extract"]["output_schema"])
    result["notice"]["title"] = "합성 추출"
    for name, filename in [("1", "synthetic.hwp"), ("2", "scan.pdf")]:
        source = {"attachment": filename, "page": 1, "quote": "합성 조건"}
        result["items"].append(
            {
                "item_no": name,
                "name": "합성 품목",
                "spec_text": "",
                "filter_type": "",
                "dimension_json": "{}",
                "quantity": 2,
                "unit": "EA",
                "material_no": "",
                "source": source,
            }
        )
        result["requirements"].append(
            {
                "item_no": name,
                "category": "OTHER",
                "title": "합성 조건",
                "requirement_text": "합성 조건",
                "normalized_json": "{}",
                "is_mandatory": True,
                "source": source,
            }
        )
    return result


@pytest.fixture
def synthetic_bid(fake_llm, monkeypatch):
    from apps.documents import pipeline

    bid = BidNotice.objects.create(title="합성 공고")
    text = Document.objects.create(
        owner_type="BID",
        file_format="HWP",
        original_filename="synthetic.hwp",
        source_text="합성 조건",
        extracted_text="합성 조건",
        status="PARSED",
        sha256="a" * 64,
    )
    scanned = Document.objects.create(
        owner_type="BID",
        file_format="PDF",
        original_filename="scan.pdf",
        status="PARSED",
        page_count=1,
    )
    scanned.file.save("scan.pdf", ContentFile(b"%PDF-synthetic-original"))
    BidAttachment.objects.create(bid=bid, document=text, is_primary=True)
    BidAttachment.objects.create(bid=bid, document=scanned)
    monkeypatch.setattr(
        pipeline, "parse_file", lambda *a, **kw: ParseResult(text="", pages=[""], is_scanned=True)
    )
    fake_llm.responses.append(output())
    return bid


def test_extraction_only_includes_pdf_and_never_runs_downstream(
    synthetic_bid, fake_llm, monkeypatch
):
    forbidden = Mock(side_effect=AssertionError("Downstream work is forbidden"))
    for name in ("match_items", "update_fit", "run_pipeline"):
        monkeypatch.setattr(extraction, name, forbidden)
    monkeypatch.setattr(extraction.EvaluationContext, "for_bid", forbidden)
    result = extraction.extract_bid(synthetic_bid, extraction_only=True)
    assert len(fake_llm.requests) == 1
    request = fake_llm.requests[0]
    assert request.files[0].filename == "scan.pdf"
    assert request.files[0].data == b"%PDF-synthetic-original"
    assert 'name="scan.pdf"' in request.user and "전사문은 없습니다" in request.user
    synthetic_bid.refresh_from_db()
    assert synthetic_bid.fit_score is None and synthetic_bid.fit_reason == ""
    assert result["fit_score"] is None and result["requirements"] == 2
    assert not synthetic_bid.items.filter(matched_product__isnull=False).exists()
    hwp = synthetic_bid.requirements.get(item__item_no="1")
    pdf = synthetic_bid.requirements.get(item__item_no="2")
    assert hwp.source_attachment.document.original_filename == "synthetic.hwp"
    assert hwp.source_page is None and pdf.source_page == 1
    assert pdf.source_attachment.document.original_filename == "scan.pdf"
    assert hwp.source_quote == pdf.source_quote == "합성 조건"
    placeholder = synthetic_bid.requirements.filter(normalized__placeholder=True).first()
    assert placeholder.source == "RULE" and "원문 확인 필요" in placeholder.requirement_text
    assert "명시되어 있지 않음" not in placeholder.requirement_text
    run = synthetic_bid.extra["extraction_run"]
    assert run["scope"] == "REQUIREMENTS_ONLY"
    assert {a["input_mode"] for a in run["attachments"]} == {"STORED_TEXT", "ORIGINAL_PDF"}
    assert not Job.objects.exists()
    forbidden.assert_not_called()


def test_scanned_pdf_unsupported_fails_before_paid_request(synthetic_bid, fake_llm):
    LLMModelOption.objects.update(supports_pdf_input=False)
    with pytest.raises(extraction.BidExtractionError, match="PDF 입력"):
        extraction.extract_bid(synthetic_bid, extraction_only=True)
    assert fake_llm.requests == [] and not LLMCallLog.objects.exists()


def test_unread_or_oversized_attachment_is_never_silently_dropped(synthetic_bid):
    doc = synthetic_bid.attachments.get(is_primary=True).document
    doc.extracted_text = ""
    doc.save()
    with pytest.raises(extraction.BidExtractionError, match="읽을 수 없는"):
        extraction.build_attachment_inputs(synthetic_bid, require_all=True)
    doc.extracted_text = "가" * 20000
    doc.save()
    set_setting("llm.max_input_chars", 11000)
    with pytest.raises(extraction.BidExtractionError, match="입력 한도"):
        extraction.build_attachment_inputs(synthetic_bid, require_all=True)


def test_rendered_input_limit_is_checked_before_paid_request(synthetic_bid, fake_llm):
    set_setting("llm.max_input_chars", 100)
    with pytest.raises(extraction.BidExtractionError, match="입력 한도"):
        extraction.extract_bid(synthetic_bid, extraction_only=True)
    assert not fake_llm.requests


def test_only_job_does_not_chain_even_with_global_auto_evaluation(synthetic_bid, monkeypatch):
    set_setting("bid.auto_evaluate_after_extract", True)
    enqueue = Mock(side_effect=AssertionError("No evaluation enqueue"))
    monkeypatch.setattr(tasks, "enqueue", enqueue)
    job = Job.objects.create(
        type="EXTRACT_BID", target_id=synthetic_bid.pk, payload={"extraction_only": True}
    )
    result = tasks.extract_bid_job(job, lambda *a: None)
    assert "evaluate_job_id" not in result
    enqueue.assert_not_called()


def test_regular_path_keeps_match_fit_and_auto_evaluation_defaults(synthetic_bid, monkeypatch):
    match, fit = Mock(), Mock()
    monkeypatch.setattr(extraction, "process_attachments", lambda *a, **kw: None)
    monkeypatch.setattr(
        extraction,
        "build_attachment_inputs",
        lambda *a, **kw: [{"name": "scan.pdf", "category": "합성", "text": "합성"}],
    )
    monkeypatch.setattr(extraction.EvaluationContext, "for_bid", lambda bid: object())
    monkeypatch.setattr(extraction, "match_items", match)
    monkeypatch.setattr(extraction, "update_fit", fit)
    set_setting("bid.auto_evaluate_after_extract", True)
    job = Job.objects.create(type="EXTRACT_BID", target_id=synthetic_bid.pk)
    enqueued = Mock(pk=99)
    enqueue = Mock(return_value=enqueued)
    monkeypatch.setattr(tasks, "enqueue", enqueue)
    monkeypatch.setattr(tasks, "has_handler", lambda key: True)
    result = tasks.extract_bid_job(job, lambda *a: None)
    match.assert_called_once()
    fit.assert_called_once()
    enqueue.assert_called_once()
    assert result["evaluate_job_id"] == 99


def test_command_runs_only_named_bid_and_refuses_completed_repeat(synthetic_bid, monkeypatch):
    other = BidNotice.objects.create(title="보존 대상")
    before = dict(BidNotice.objects.values().get(pk=other.pk))
    call_command("extract_bid_only", bid_id=synthetic_bid.pk, stdout=StringIO())
    assert BidNotice.objects.values().get(pk=other.pk) == before
    with pytest.raises(CommandError, match="완료 결과"):
        call_command("extract_bid_only", bid_id=synthetic_bid.pk, stdout=StringIO())


def test_equal_airflow_still_has_explicit_normalized_unit():
    result = extraction.normalize_requirement(
        "AIRFLOW", "최소 4320m3/h", {"value": 4320, "raw": "최소 4320m3/h"}
    )
    assert result["value"] == 4320 and result["unit"] == "m3/h"


def test_source_review_flags_missing_quote_and_pdf_without_inventing_corrections(synthetic_bid):
    extraction.extract_bid(synthetic_bid, extraction_only=True)
    text = synthetic_bid.requirements.get(item__item_no="1")
    text.source_quote = "없는 인용문"
    text.save()
    review = extraction.review_sources(synthetic_bid)
    assert review["counts"]["QUOTE_NOT_FOUND"] == 1
    assert review["counts"]["PDF_VISUAL_REVIEW_REQUIRED"] == 1
    text.refresh_from_db()
    assert text.source_quote == "없는 인용문" and text.source_page is None
    assert not review["technical_review_completed"]


def test_json_repair_keeps_original_pdf_input(synthetic_bid, fake_llm):
    fake_llm.responses[:] = ["invalid json", output()]
    extraction.extract_bid(synthetic_bid, extraction_only=True)
    assert len(fake_llm.requests) == 2
    assert all(r.files[0].data == b"%PDF-synthetic-original" for r in fake_llm.requests)
    assert list(LLMCallLog.objects.order_by("id").values_list("status", flat=True)) == [
        "INVALID_JSON",
        "OK",
    ]


def test_whitespace_quote_is_missing_and_punctuation_difference_stays_explicit(synthetic_bid):
    extraction.extract_bid(synthetic_bid, extraction_only=True)
    req = synthetic_bid.requirements.get(item__item_no="1")
    req.source_quote = " "
    req.save()
    assert extraction.review_sources(synthetic_bid)["counts"]["MISSING_QUOTE"] == 1
    req.source_quote = "“합성 조건”"
    req.save()
    assert extraction.review_sources(synthetic_bid)["counts"]["QUOTATION_MARK_DIFFERENCE"] == 1


@pytest.mark.parametrize(
    "kind", ["fit", "match", "locked", "manual_requirement", "evaluation", "draft"]
)
def test_only_mode_preserves_existing_work_before_any_paid_request(kind, synthetic_bid, fake_llm):
    from apps.bids.models import BidItem, BidRequirement
    from apps.company.models import Product
    from apps.drafts.models import DraftDocument
    from apps.evaluation.models import RequirementEvaluation

    if kind == "fit":
        synthetic_bid.fit_score = 70
        synthetic_bid.save()
    if kind == "match":
        product = Product.objects.create(model_no="SYNTHETIC", name="합성")
        BidItem.objects.create(bid=synthetic_bid, name="합성", matched_product=product)
    if kind in ("locked", "manual_requirement", "evaluation"):
        requirement = BidRequirement.objects.create(
            bid=synthetic_bid,
            category="OTHER",
            title="수동 보존",
            is_locked=kind == "locked",
            source="MANUAL" if kind == "manual_requirement" else "LLM",
        )
        if kind == "evaluation":
            RequirementEvaluation.objects.create(
                requirement=requirement, verdict="MET", is_modified=True
            )
    if kind == "draft":
        DraftDocument.objects.create(
            bid=synthetic_bid, title="수동 초안", doc_type="TECHNICAL_QUERY", is_modified=True
        )
    models = (BidNotice, BidItem, BidRequirement, RequirementEvaluation, DraftDocument)
    before = [list(model.objects.values()) for model in models]
    with pytest.raises(extraction.BidExtractionError, match="기존"):
        extraction.extract_bid(synthetic_bid, extraction_only=True)
    assert [list(model.objects.values()) for model in models] == before
    assert not fake_llm.requests and not LLMCallLog.objects.exists()
