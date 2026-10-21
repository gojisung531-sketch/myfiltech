"""EXTRACT_BID post-processing with a fake LLM (specs/06 §6, specs/12 §3.3)."""

from datetime import datetime

import pytest
from django.utils import timezone

from apps.bids.extraction import (
    BidExtractionError,
    build_attachment_inputs,
    excerpt,
    extract_bid,
    parse_datetime_kst,
)
from apps.bids.models import BidNotice, BidRequirement
from apps.core.app_settings import set_setting
from apps.llm.services import LLMInvalidOutput, LLMNotConfigured

from .conftest import extract_output, schema_responder

pytestmark = pytest.mark.django_db


def kst(*args):
    return timezone.make_aware(datetime(*args))


def test_parse_datetime_kst_formats():
    assert parse_datetime_kst("2023/04/03 10:00") == kst(2023, 4, 3, 10, 0)
    assert parse_datetime_kst("2023.04.05") == kst(2023, 4, 5)
    assert parse_datetime_kst("2023-04-05T12:00:00+09:00") == kst(2023, 4, 5, 12, 0)
    assert parse_datetime_kst("") is None
    assert parse_datetime_kst("미정") is None


def test_excerpt_keeps_keyword_paragraphs():
    text = "\n\n".join(["일반 조항입니다."] * 5 + ["납품기한은 계약 후 90일", "기타 내용"])
    result = excerpt(text, ["납품기한"])
    assert "납품기한은 계약 후 90일" in result
    assert result.count("일반 조항") < 5


def test_attachment_inputs_primary_first(sample_bid):
    primary = sample_bid.attachments.get(is_primary=True)
    assert primary.role == "bid_notice"
    inputs = build_attachment_inputs(sample_bid)
    assert inputs[0]["name"] == primary.document.original_filename
    assert {i["name"] for i in inputs} >= {
        "정비용 기자재 구매규격서.hwp",
        "구매 청구 품목 명세서.xlsx",
    }


def test_extract_requires_llm(sample_bid):
    with pytest.raises(LLMNotConfigured):
        extract_bid(sample_bid)


def test_extract_bid_applies_output(sample_bid, company_data, fake_llm):
    fake_llm.reset(responder=schema_responder())
    result = extract_bid(sample_bid)
    bid = BidNotice.objects.get(pk=sample_bid.pk)

    assert bid.processing_status == "EXTRACTED"
    assert bid.notice_no == "20230323830-00"  # suffix restored by the regex on the notice text
    assert bid.budget_krw == 370062000
    assert bid.bid_open_at == kst(2023, 4, 3, 10, 0)
    assert bid.bid_close_at == kst(2023, 4, 5, 12, 0)
    assert bid.is_power_plant is True
    assert result["placeholders"] == ["SUBMISSION_DOC"]
    assert result["requirements"] == 12

    cone = bid.items.get(item_no="2")
    assert (cone.diameter_mm, cone.diameter2_mm, cone.length_mm) == (
        445,
        324,
        660,
    )  # from spec_text
    assert cone.source_attachment.document.original_filename == "정비용 기자재 구매규격서.hwp"

    pressure = bid.requirements.get(category="PRESSURE_DROP")
    assert pressure.normalized["value"] == pytest.approx(176.85, abs=0.1)
    assert pressure.normalized["unit"] == "Pa"
    assert pressure.normalized["unit_corrected"] is True
    assert pressure.normalized["at_airflow_m3h"] == 2770
    assert pressure.item.item_no == "1"

    cone_dim = bid.requirements.get(category="DIMENSION", item=cone)
    assert (cone_dim.normalized["dia"], cone_dim.normalized["dia2"]) == (445, 324)

    other = bid.requirements.get(category="OTHER")
    assert other.normalized == {"raw": "not json at all"}
    assert other.source_attachment is None

    placeholder = bid.requirements.get(category="SUBMISSION_DOC")
    assert placeholder.normalized == {"placeholder": True}
    assert placeholder.source == "RULE"

    cylinder = bid.items.get(item_no="1")
    assert cylinder.matched_product.model_no == "FT-CP200"
    rule_score = bid.extra["rule_fit_score"]
    assert set(bid.extra["fit_breakdown"]) == {
        "product_type",
        "power_plant",
        "qualification",
        "spec_coverage",
    }
    assert bid.fit_score == max(rule_score - 10, min(rule_score + 10, 60))  # LLM may move it ±10
    assert "GT 흡기 필터" in bid.fit_reason


def test_reextract_keeps_locked_values(sample_bid, company_data, fake_llm):
    fake_llm.reset(responder=schema_responder())
    extract_bid(sample_bid)
    bid = BidNotice.objects.get(pk=sample_bid.pk)
    bid.title = "수정한 제목"
    bid.extra = {**bid.extra, "locked_fields": ["title"]}
    bid.save()
    edited = bid.requirements.get(category="DELIVERY")
    edited.requirement_text = "계약 후 120일 이내"
    edited.is_locked = True
    edited.save()

    changed = extract_output()
    changed["notice"]["title"] = "LLM 제목"
    changed["requirements"] = [r for r in changed["requirements"] if r["category"] != "OTHER"]
    fake_llm.reset(responder=schema_responder(extract=changed))
    extract_bid(bid)
    bid.refresh_from_db()

    assert bid.title == "수정한 제목"
    assert bid.requirements.get(pk=edited.pk).requirement_text == "계약 후 120일 이내"
    assert bid.requirements.filter(category="DELIVERY").count() == 2  # locked + re-extracted
    assert not bid.requirements.filter(category="OTHER").exists()


def test_extract_failure_marks_bid(sample_bid, fake_llm):
    fake_llm.reset(responder=schema_responder(extract={"bad": True}))
    with pytest.raises(LLMInvalidOutput):
        extract_bid(sample_bid)
    sample_bid.refresh_from_db()
    assert sample_bid.processing_status == "FAILED"
    assert sample_bid.processing_error


def test_extract_without_text(db, fake_llm):
    bid = BidNotice.objects.create(title="빈 공고")
    with pytest.raises(BidExtractionError):
        extract_bid(bid)
    bid.refresh_from_db()
    assert bid.processing_status == "FAILED"
    assert "첨부" in bid.processing_error


def test_extract_job_chains_without_evaluate_handler(
    sample_bid, company_data, fake_llm, inline_jobs
):
    from apps.core import jobs

    fake_llm.reset(responder=schema_responder())
    set_setting("bid.auto_evaluate_after_extract", True)
    job = jobs.enqueue("EXTRACT_BID", target=sample_bid)
    job.refresh_from_db()
    assert job.status == "SUCCEEDED", job.error
    assert job.result["placeholders"] == ["SUBMISSION_DOC"]
    assert BidRequirement.objects.filter(bid=sample_bid).count() == 13


def test_delivery_months_become_days():
    from apps.bids.extraction import normalize_requirement

    out = normalize_requirement(
        "DELIVERY",
        "계약일로부터 5개월 이내",
        {"days_after_contract": None, "months_after_contract": 5},
    )
    assert out["days_after_contract"] == 150 and out["months_after_contract"] == 5
    kept = normalize_requirement(
        "DELIVERY", "", {"days_after_contract": 90, "months_after_contract": 5}
    )
    assert kept["days_after_contract"] == 90
