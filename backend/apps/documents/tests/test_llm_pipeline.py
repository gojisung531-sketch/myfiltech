"""LLM fallbacks in the document pipeline (specs/06 §2.2, §3, §5.2), using FakeProvider."""

from pathlib import Path

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.documents.loader import load_company
from apps.documents.models import Document, MetadataSchema
from apps.llm.models import LLMModelOption, LLMSettings
from apps.llm.providers import LLMError

pytestmark = pytest.mark.django_db

DATA = Path(settings.INITIAL_DATA_DIR)


def field_value(key: str, value: str, confidence=0.9, raw=""):
    """One found field as the model returns it: value is always a string (specs/07 §2)."""
    return {
        "key": key,
        "value": value,
        "raw": raw,
        "page": 1,
        "quote": raw,
        "confidence": confidence,
    }


def response(*fields, transcript=""):
    return {"fields": list(fields), "transcript": transcript}


def upload(client, name, content: bytes, owner_type="COMPANY", category=None):
    data = {"owner_type": owner_type, "files": [SimpleUploadedFile(name, content)]}
    if category:
        data["category"] = category
    return client.post("/api/documents", data, format="multipart").data["documents"][0]


def metadata(doc_id):
    return {m.key: m for m in Document.objects.get(pk=doc_id).metadata.all()}


def test_llm_classifies_and_fills_missing_required_field(admin_client, inline_jobs, fake_llm):
    fake_llm.responses.extend(
        [
            {"code": "certificate", "confidence": 0.92, "reason": "인증서"},
            response(field_value("cert_no", "Q-1", raw="인증번호 Q-1")),
        ]
    )
    doc = upload(admin_client, "scan_001.txt", "품질 인증 문서\n인증번호 Q-1".encode())
    assert (doc["category_code"], doc["category_confidence"]) == ("certificate", 0.92)
    assert doc["status"] == "EXTRACTED"
    # Only the missing required field is requested from the LLM.
    extract_request = fake_llm.requests[1]
    item = extract_request.json_schema["properties"]["fields"]["items"]
    assert item["properties"]["key"]["enum"] == ["cert_no"]
    row = metadata(doc["id"])["cert_no"]
    assert (row.value, row.source, row.confidence) == ("Q-1", "LLM", 0.9)


def test_category_without_rule_extractor_uses_llm_for_all_fields(
    admin_client, inline_jobs, fake_llm
):
    schema = MetadataSchema.objects.get(code="company_profile")
    fake_llm.responses.append(
        response(
            field_value("name", "(주)필텍"),
            field_value("is_sme", "true"),
            field_value("g2b_items", '[{"code": "4016150501", "name": "공기여과기"}]'),
            field_value("ceo", ""),
        )
    )
    doc = upload(admin_client, "profile.txt", "(주)필텍 회사 소개".encode(), category=schema.code)
    item = fake_llm.requests[0].json_schema["properties"]["fields"]["items"]
    assert set(item["properties"]["key"]["enum"]) == {f["key"] for f in schema.fields}
    rows = metadata(doc["id"])
    assert rows["g2b_items"].value == [{"code": "4016150501", "name": "공기여과기"}]
    assert rows["is_sme"].value is True
    assert "ceo" not in rows  # empty values are not stored


def test_rule_complete_documents_make_no_llm_calls(fake_llm):
    load_company()
    assert fake_llm.requests == []
    assert Document.objects.filter(status="REVIEWED").count() == 19


def test_scanned_pdf_is_transcribed_by_pdf_capable_model(admin_client, inline_jobs, fake_llm):
    path = DATA / "bid_sample/won/20210829431/제한경쟁사유서.pdf"
    fake_llm.responses.append(
        response(
            field_value("restriction_type", "실적제한"),
            field_value("track_record_requirement", "최근 10년 F7 이상 GT 필터"),
            transcript="제한경쟁 사유서\n실적제한 ...",
        )
    )
    doc = upload(admin_client, path.name, path.read_bytes(), owner_type="BID")
    assert doc["category_code"] == "bid_restriction_reason"  # filename rule, no LLM classify
    assert doc["status"] == "EXTRACTED"
    assert len(fake_llm.requests) == 1
    assert fake_llm.requests[0].files[0].filename == path.name
    assert "원본 PDF가 첨부되어" in fake_llm.requests[0].user
    document = Document.objects.get(pk=doc["id"])
    assert document.extracted_text.startswith("제한경쟁 사유서")
    assert metadata(doc["id"])["restriction_type"].value == "실적제한"


def test_scanned_pdf_without_pdf_model_needs_ocr(admin_client, inline_jobs, fake_llm):
    LLMModelOption.objects.filter(pk=LLMSettings.load().active_model_id).update(
        supports_pdf_input=False
    )
    path = DATA / "bid_sample/won/20230342721/제한 경쟁 사유서.pdf"
    doc = upload(admin_client, path.name, path.read_bytes(), owner_type="BID")
    assert doc["status"] == "NEEDS_OCR"
    assert fake_llm.requests == []


def test_llm_failure_keeps_rule_results(admin_client, inline_jobs, fake_llm):
    fake_llm.responses.append(LLMError("요청 한도를 초과했습니다."))
    doc = upload(admin_client, "profile.txt", "회사 소개".encode(), category="company_profile")
    assert doc["status"] == "EXTRACTED"
    assert "LLM 처리 실패" in doc["error_message"]


def test_without_llm_the_step_is_deferred(admin_client, inline_jobs):
    doc = upload(admin_client, "profile.txt", "회사 소개".encode(), category="company_profile")
    assert doc["status"] == "EXTRACTED"
    assert "LLM 미설정" in doc["error_message"]
