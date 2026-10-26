"""Synthetic notices only; real pasted source is kept outside Git."""

import json
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.bids.extraction import apply_notice
from apps.bids.models import BidNotice
from apps.bids.pasted_metadata import MAX_SOURCE_LENGTH, preview, source_hash
from apps.core.models import Job
from apps.documents.models import Document
from apps.llm.models import LLMCallLog


def test_rules_spaced_labels_markdown_br_and_exact_quotes():
    text = "  | 항목 | 내용 |\r\n| :--- | ---: |\r\n| **공고 번호** | AB-42 |\r\n| 건명 | 합성 검증용 구매<br>조건 |\r\n| 추정 가격 | 1,234,000원 |\r\n"
    p = preview(text)
    assert p["source_sha256"] == source_hash(text)
    assert p["values"] == {
        "notice_no": "AB-42",
        "title": "합성 검증용 구매 조건",
        "estimated_price_krw": 1234000,
    }
    assert all(e["quote"] in text for e in p["evidence"].values())
    assert "<br>" in p["evidence"]["title"]["quote"]


def test_plain_text_inline_tabs_and_next_line():
    p = preview(
        "공고번호: A12 건명: 합성 안내\n수요기관\t명시 기관\n납품장소\n검증 현장\n개찰일시: 2027.01.05 10:10"
    )
    assert p["values"]["title"] == "합성 안내"
    assert p["values"]["buyer_org"] == "명시 기관"
    assert p["values"]["delivery_place"] == "검증 현장"
    assert p["values"]["opening_at"] == "2027-01-05T10:10:00+09:00"
    assert "bid_open_at" not in p["values"]


def test_horizontal_markdown_headers_map_only_explicit_fields():
    text = "| 공고번호 | 건명 | 추정가격 | 비고 |\n| --- | --- | ---: | --- |\n| TEST-7 | 가로표 검증 | 1,000 | 기관 추정 금지 |"
    p = preview(text)
    assert p["values"] == {
        "notice_no": "TEST-7",
        "title": "가로표 검증",
        "estimated_price_krw": 1000,
    }
    assert all(e["quote"] in text for e in p["evidence"].values())


def test_horizontal_rows_conflict_instead_of_selecting_a_record():
    p = preview("| 공고번호 | 건명 |\n| --- | --- |\n| A | 하나 |\n| B | 둘 |")
    assert not p["values"]
    assert sum(w["code"] == "CONFLICTING_VALUES" for w in p["warnings"]) == 2


@pytest.mark.parametrize(
    "label", ["부가세", "합계금액", "기초금액", "예비가기초금액", "추정금액", "공고일시"]
)
def test_unsupported_values_are_not_budget_or_start(label):
    p = preview(f"{label}: 2027.01.05 09:00\n담당부서: 구매처")
    assert p["values"] == {}
    assert any(w["code"] == "UNSUPPORTED_FIELD" and w["field"] is None for w in p["warnings"])


def test_duplicates_and_conflicts_fail_closed():
    p = preview(
        "공고번호: AB\n공고번호: AB\n추정가격: 1,000\n추정가격: 2,000\n수요기관: 기관A\n수요기관: 기관B"
    )
    assert p["values"] == {"notice_no": "AB"}
    assert {w["field"] for w in p["warnings"] if w["code"] == "CONFLICTING_VALUES"} == {
        "estimated_price_krw",
        "buyer_org",
    }


@pytest.mark.parametrize(
    "value",
    [
        "2027.02.30 10:00",
        "2027.01.05",
        "2027.01.05 24:00",
        "2027.01.05 10:61",
        "2027.01.05(월) 10:00",
        "2027-01-05T10:00:00+99:99",
    ],
)
def test_invalid_dates_never_get_a_fabricated_time(value):
    p = preview("입찰마감일시: " + value)
    assert "bid_close_at" not in p["values"]
    assert p["warnings"][0]["code"] == "INVALID_VALUE"


def test_blank_table_cell_does_not_borrow_next_row():
    p = preview("| 공고번호 | |\n| 비고 | 설명 |\n건명: 합성 검증")
    assert p["values"] == {"title": "합성 검증"}


def test_invalid_duplicate_blocks_valid_candidate():
    p = preview("추정가격: 1,000\n추정가격: 1,00\n입찰마감일시:\n건명: 합성 검증")
    assert p["values"] == {"title": "합성 검증"}


def test_datetime_order_and_timezone():
    p = preview("입찰시작일시: 2027.01.06 10:00\n입찰마감일시: 2027.01.05 10:00")
    assert not p["values"] and any(w["code"] == "DATE_ORDER_CONFLICT" for w in p["warnings"])
    p = preview("개찰일시: 2027-01-05T01:10:00Z")
    assert p["values"]["opening_at"] == "2027-01-05T10:10:00+09:00"


@pytest.mark.django_db
@pytest.mark.parametrize("metadata", ["{broken", "[]", "null", '{"values":{}}'])
def test_malformed_envelopes(admin_client, metadata):
    response = admin_client.post(
        "/api/bids",
        {"source_text": "건명: 합성 검증", "notice_metadata": metadata},
        format="multipart",
    )
    assert response.status_code == 400 and not BidNotice.objects.exists()


@pytest.mark.django_db
def test_preview_admin_only_no_queries_or_side_effects(
    admin_client, manager_client, api_client, django_assert_num_queries
):
    url = "/api/bids/preview-metadata"
    with (
        django_assert_num_queries(0),
        patch("apps.llm.services.run_task", side_effect=AssertionError("LLM forbidden")),
        patch("apps.bids.views.enqueue", side_effect=AssertionError("Job forbidden")),
    ):
        response = admin_client.post(url, {"source_text": "건명: 합성 검증"}, format="json")
    assert response.status_code == 200
    assert manager_client.post(url, {"source_text": "건명: 검증"}, format="json").status_code == 403
    assert api_client.post(url, {"source_text": "건명: 검증"}, format="json").status_code == 401
    assert (
        not BidNotice.objects.exists()
        and not Job.objects.exists()
        and not Document.objects.exists()
    )
    assert not LLMCallLog.objects.exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "text",
    [None, [], {}, 3, "", "   ", "x" * (MAX_SOURCE_LENGTH + 1)],
    ids=["null", "list", "object", "number", "empty", "whitespace", "too_long"],
)
def test_preview_input_validation(admin_client, text):
    assert (
        admin_client.post(
            "/api/bids/preview-metadata", {"source_text": text}, format="json"
        ).status_code
        == 400
    )


@pytest.mark.django_db
def test_create_legacy_autofill_raw_source_and_explicit_lock(admin_client):
    text = " \r\n공고번호: SYN-501\r\n건명: 자동 건명\r\n추정가격: 1,000원\r\n "
    with patch("apps.llm.services.run_task", side_effect=AssertionError("LLM forbidden")):
        response = admin_client.post(
            "/api/bids", {"source_text": text, "title": "직원 지정"}, format="multipart"
        )
    assert response.status_code == 201, response.data
    bid = BidNotice.objects.get(pk=response.data["id"])
    assert bid.source_text == text
    assert bid.attachments.get().document.source_text == text
    assert (
        bid.title == "직원 지정" and bid.notice_no == "SYN-501" and bid.estimated_price_krw == 1000
    )
    assert bid.locked_fields == ["title"]
    assert bid.processing_status == "DRAFT" and not Job.objects.exists()
    assert response.data["notice_metadata"]["field_sources"]["title"] == "EXPLICIT_INPUT"


@pytest.mark.django_db
def test_confirmed_metadata_typed_dates_manual_clear_and_followup_lock(admin_client):
    text = "건명: 자동 건명\n추정가격: 1,000\n입찰마감일시: 2027.01.05 10:00"
    p = preview(text)
    values = {**p["values"], "title": "수동 제목", "estimated_price_krw": None}
    metadata = {
        "source_sha256": p["source_sha256"],
        "values": values,
        "edited_fields": ["title", "estimated_price_krw"],
    }
    response = admin_client.post(
        "/api/bids",
        {"source_text": text, "notice_metadata": json.dumps(metadata)},
        format="multipart",
    )
    assert response.status_code == 201, response.data
    bid = BidNotice.objects.get(pk=response.data["id"])
    assert bid.title == "수동 제목" and bid.estimated_price_krw is None
    assert set(bid.locked_fields) == {"title", "estimated_price_krw"}
    assert response.data["bid_close_at"] == "2027-01-05T10:00:00+09:00"
    assert "title" not in response.data["notice_metadata"]["evidence"]
    assert response.data["notice_metadata"]["field_sources"]["title"] == "MANUAL"
    # Apply only the existing metadata assignment function, no extraction/LLM/job.
    apply_notice(bid, {"title": "나중 자동 제목", "estimated_price_krw": 999}, "")
    assert bid.title == "수동 제목" and bid.estimated_price_krw is None
    url = f"/api/bids/{bid.pk}"
    response = admin_client.patch(url, {"delivery_place": "직원 수정 현장"}, format="json")
    assert "delivery_place" in response.data["locked_fields"]
    bid.refresh_from_db()
    apply_notice(bid, {"delivery_place": "다른 자동 현장"}, "")
    assert bid.delivery_place == "직원 수정 현장"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "change",
    [
        {"source_sha256": "wrong"},
        {"values": {"title": "위조 자동 제목"}},
        {"values": {"processing_status": "EVALUATED"}},
        {"values": {"estimated_price_krw": "1000"}, "edited_fields": ["estimated_price_krw"]},
        {"values": {"estimated_price_krw": True}, "edited_fields": ["estimated_price_krw"]},
        {"values": {"estimated_price_krw": -1}, "edited_fields": ["estimated_price_krw"]},
        {"values": {"notice_no": 123}, "edited_fields": ["notice_no"]},
        {"values": {"opening_at": "2027-01-05"}, "edited_fields": ["opening_at"]},
        {"values": {"title": ""}, "edited_fields": ["title"]},
        {"edited_fields": ["summary"]},
        {"edited_fields": ["title", "title"]},
        {"edited_fields": "title"},
        {"evidence": {"title": {"quote": "위조"}}},
    ],
)
def test_reject_untrusted_metadata_without_partial_save(admin_client, change):
    text = "건명: 검증용\n추정가격: 1,000"
    p = preview(text)
    meta = {
        "source_sha256": p["source_sha256"],
        "values": p["values"],
        "edited_fields": [],
        **change,
    }
    response = admin_client.post(
        "/api/bids", {"source_text": text, "notice_metadata": json.dumps(meta)}, format="multipart"
    )
    assert response.status_code == 400, response.data
    assert (
        not BidNotice.objects.exists()
        and not Document.objects.exists()
        and not Job.objects.exists()
    )


@pytest.mark.django_db
def test_auto_title_echo_is_not_manual_and_urls_never_fetched(admin_client):
    text = "건명: 검증용\n납품조건: https://example.invalid/notice"
    p = preview(text)
    meta = {"source_sha256": p["source_sha256"], "values": p["values"], "edited_fields": []}
    response = admin_client.post(
        "/api/bids",
        {"source_text": text, "title": "검증용", "notice_metadata": json.dumps(meta)},
        format="multipart",
    )
    assert response.status_code == 201
    assert response.data["locked_fields"] == []
    assert response.data["delivery_terms"] == "https://example.invalid/notice"
    assert not LLMCallLog.objects.exists()


@pytest.mark.django_db
def test_file_only_remains_supported(admin_client):
    file = SimpleUploadedFile("notice.txt", b"synthetic notice", content_type="text/plain")
    response = admin_client.post("/api/bids", {"files": [file]}, format="multipart")
    assert response.status_code == 201 and response.data["title"] == "notice"
    assert response.data["processing_status"] == "DRAFT"
