from pathlib import Path

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.company.models import Product
from apps.core.app_settings import set_setting
from apps.documents.models import Document, MetadataSchema

pytestmark = pytest.mark.django_db

DATA = Path(settings.INITIAL_DATA_DIR) / "company"


def upload(client, *files, owner_type="COMPANY", category=None):
    data = {"owner_type": owner_type, "files": list(files)}
    if category:
        data["category"] = category
    return client.post("/api/documents", data, format="multipart")


def pdf_file(relative: str) -> SimpleUploadedFile:
    path = DATA / relative
    return SimpleUploadedFile(path.name, path.read_bytes(), content_type="application/pdf")


def test_upload_extracts_without_applying_by_default(admin_client, inline_jobs):
    res = upload(admin_client, pdf_file("datasheets/FT-VB500_기술사양서.pdf"))
    assert res.status_code == 201
    doc = res.data["documents"][0]
    assert doc["status"] == "EXTRACTED"
    assert doc["category_code"] == "datasheet"
    assert doc["metadata_count"] > 15
    detail = admin_client.get(f"/api/documents/{doc['id']}").data
    assert detail["low_confidence_threshold"] == 0.7
    assert not Product.objects.exists()  # extraction.auto_apply_company = false


def test_preview_then_apply(admin_client, inline_jobs):
    doc_id = upload(admin_client, pdf_file("datasheets/FT-EP700_기술사양서.pdf")).data["documents"][
        0
    ]["id"]
    preview = admin_client.get(f"/api/documents/{doc_id}/mapping-preview").data["changes"][0]
    assert (preview["model"], preview["lookup"], preview["action"]) == (
        "company.Product",
        "FT-EP700",
        "create",
    )
    assert preview["changes"]["en1822_class"] == [None, "E12"]
    res = admin_client.post(f"/api/documents/{doc_id}/apply")
    assert res.data["document"]["status"] == "REVIEWED"
    assert Product.objects.get(model_no="FT-EP700").initial_dp_pa == 190
    again = admin_client.get(f"/api/documents/{doc_id}/mapping-preview").data["changes"][0]
    assert again["action"] == "unchanged"


def test_auto_apply_setting(admin_client, inline_jobs):
    set_setting("extraction.auto_apply_company", True)
    res = upload(admin_client, pdf_file("certificates/C01_ISO9001_인증서.pdf"))
    assert res.data["documents"][0]["status"] == "REVIEWED"


def test_upload_rejections(admin_client, inline_jobs):
    res = upload(
        admin_client,
        SimpleUploadedFile("evil.exe", b"MZ..."),
        SimpleUploadedFile("fake.pdf", b"not a pdf at all"),
        SimpleUploadedFile("a.hwp:Zone.Identifier", b"[ZoneTransfer]"),
        SimpleUploadedFile("sheet.xlsx", b"PK\x03\x04data"),  # XLSX is only for bid attachments
    )
    assert res.status_code == 400
    reasons = {s["filename"]: s["reason"] for s in res.data["skipped"]}
    assert "지원하지 않는 형식" in reasons["evil.exe"]
    assert "확장자와 일치하지" in reasons["fake.pdf"]
    assert "숨김" in reasons["a.hwp:Zone.Identifier"]
    assert "지원하지 않는 형식" in reasons["sheet.xlsx"]


def test_upload_size_limit(admin_client, inline_jobs):
    set_setting("upload.max_mb", 0)
    res = upload(admin_client, SimpleUploadedFile("a.txt", b"hello"))
    assert "너무 큽니다" in res.data["skipped"][0]["reason"]


def test_duplicate_upload_is_reported(admin_client, inline_jobs):
    first = upload(admin_client, SimpleUploadedFile("memo.txt", "회사 메모".encode()))
    second = upload(admin_client, SimpleUploadedFile("memo2.txt", "회사 메모".encode()))
    assert second.data["documents"][0]["duplicate_of"] == [first.data["documents"][0]["id"]]


def test_text_input_document(admin_client, inline_jobs):
    schema = MetadataSchema.objects.get(code="company_profile")
    res = admin_client.post(
        "/api/documents",
        {
            "title": "회사 소개",
            "source_text": "(주)필텍 회사 소개",
            "owner_type": "COMPANY",
            "category": schema.id,
        },
        format="json",
    )
    assert res.status_code == 201
    doc = res.data["documents"][0]
    assert (doc["file_format"], doc["has_file"], doc["category_source"]) == ("TXT", False, "MANUAL")
    text = admin_client.get(f"/api/documents/{doc['id']}/text").data
    assert text["pages"] == ["(주)필텍 회사 소개"]
    assert admin_client.get(f"/api/documents/{doc['id']}/download").status_code == 404


def test_unclassified_document_waits_for_manual_category(admin_client, inline_jobs):
    res = upload(admin_client, SimpleUploadedFile("memo.txt", "아무 내용".encode()))
    doc = res.data["documents"][0]
    assert doc["category"] is None and doc["status"] == "PARSED"
    assert "분류를 판별하지 못했습니다" in doc["error_message"]

    schema = MetadataSchema.objects.get(code="certificate")
    res = admin_client.patch(
        f"/api/documents/{doc['id']}",
        {"category": schema.id, "reextract": True},
        format="json",
    )
    assert res.data["category_code"] == "certificate"
    assert res.data["category_source"] == "MANUAL"
    assert res.data["status"] == "EXTRACTED"


def test_category_must_match_owner_type(admin_client, inline_jobs):
    doc = upload(admin_client, SimpleUploadedFile("memo.txt", b"x")).data["documents"][0]
    bid_schema = MetadataSchema.objects.get(code="bid_notice")
    res = admin_client.patch(
        f"/api/documents/{doc['id']}", {"category": bid_schema.id}, format="json"
    )
    assert res.status_code == 400


def test_metadata_edit_locks_and_survives_reextract(admin_client, inline_jobs):
    doc_id = upload(admin_client, pdf_file("datasheets/FT-HP900_기술사양서.pdf")).data["documents"][
        0
    ]["id"]
    rows = admin_client.get(f"/api/documents/{doc_id}/metadata").data
    max_rh = next(r for r in rows if r["key"] == "max_rh")
    assert (max_rh["value"], max_rh["source"], max_rh["is_locked"]) == (90, "RULE", False)

    res = admin_client.patch(
        f"/api/documents/{doc_id}/metadata/{max_rh['id']}", {"value": 95}, format="json"
    )
    assert (res.data["source"], res.data["is_locked"]) == ("MANUAL", True)

    admin_client.post(f"/api/documents/{doc_id}/reprocess", {"from_step": "parse"}, format="json")
    rows = {r["key"]: r for r in admin_client.get(f"/api/documents/{doc_id}/metadata").data}
    assert rows["max_rh"]["value"] == 95
    assert rows["initial_dp_pa"]["value"] == 250

    custom = admin_client.post(
        f"/api/documents/{doc_id}/metadata",
        {"key": "lead_time_days", "label": "납기", "value": 60},
        format="json",
    )
    assert custom.status_code == 201 and custom.data["is_locked"]
    dup = admin_client.post(
        f"/api/documents/{doc_id}/metadata", {"key": "lead_time_days", "value": 1}, format="json"
    )
    assert dup.status_code == 400

    unlock = admin_client.patch(
        f"/api/documents/{doc_id}/metadata/{max_rh['id']}", {"is_locked": False}, format="json"
    )
    assert unlock.data["is_locked"] is False
    admin_client.post(f"/api/documents/{doc_id}/reprocess", {"from_step": "extract"}, format="json")
    rows = {r["key"]: r for r in admin_client.get(f"/api/documents/{doc_id}/metadata").data}
    assert rows["max_rh"]["value"] == 90
    assert rows["lead_time_days"]["value"] == 60  # manual rows are kept


def test_manager_can_read_but_not_write(manager_client, admin_client, inline_jobs):
    doc_id = upload(admin_client, SimpleUploadedFile("memo.txt", b"x")).data["documents"][0]["id"]
    assert manager_client.get("/api/documents").status_code == 200
    assert manager_client.get(f"/api/documents/{doc_id}/text").status_code == 200
    assert upload(manager_client, SimpleUploadedFile("m.txt", b"x")).status_code == 403
    assert manager_client.delete(f"/api/documents/{doc_id}").status_code == 403
    assert manager_client.post(f"/api/documents/{doc_id}/reprocess").status_code == 403
    assert manager_client.get(f"/api/documents/{doc_id}/mapping-preview").status_code == 403
    assert (
        manager_client.post(
            f"/api/documents/{doc_id}/metadata", {"key": "k"}, format="json"
        ).status_code
        == 403
    )


def test_list_filters(admin_client, inline_jobs):
    upload(admin_client, pdf_file("certificates/C01_ISO9001_인증서.pdf"))
    upload(admin_client, SimpleUploadedFile("notice.txt", b"x"), owner_type="BID")
    assert admin_client.get("/api/documents?owner_type=BID").data["count"] == 1
    assert admin_client.get("/api/documents?category=certificate").data["count"] == 1
    assert admin_client.get("/api/documents?q=ISO9001").data["count"] == 1


def test_delete_document_removes_file(admin_client, inline_jobs):
    doc_id = upload(admin_client, pdf_file("certificates/C01_ISO9001_인증서.pdf")).data[
        "documents"
    ][0]["id"]
    path = Path(Document.objects.get(pk=doc_id).file.path)
    assert path.exists()
    assert admin_client.delete(f"/api/documents/{doc_id}").status_code == 204
    assert not path.exists()


def test_scanned_pdf_needs_ocr(admin_client, inline_jobs):
    path = Path(settings.INITIAL_DATA_DIR) / "bid_sample/won/20210829431/제한경쟁사유서.pdf"
    res = upload(admin_client, SimpleUploadedFile(path.name, path.read_bytes()), owner_type="BID")
    assert res.data["documents"][0]["status"] == "NEEDS_OCR"


def test_metadata_schema_crud(admin_client, manager_client):
    assert len(manager_client.get("/api/metadata-schemas").data) == 13
    payload = {
        "code": "patent",
        "name": "특허",
        "owner_type": "COMPANY",
        "filename_patterns": ["특허"],
        "fields": [{"key": "patent_no", "label": "특허번호", "type": "str"}],
    }
    assert manager_client.post("/api/metadata-schemas", payload, format="json").status_code == 403
    res = admin_client.post("/api/metadata-schemas", payload, format="json")
    assert res.status_code == 201
    assert res.data["fields"][0]["key"] == "patent_no"

    bad = admin_client.patch(
        f"/api/metadata-schemas/{res.data['id']}", {"filename_patterns": ["("]}, format="json"
    )
    assert bad.status_code == 400
    dup = admin_client.patch(
        f"/api/metadata-schemas/{res.data['id']}",
        {"fields": [{"key": "a", "label": "A"}, {"key": "a", "label": "B"}]},
        format="json",
    )
    assert dup.status_code == 400
    assert admin_client.delete(f"/api/metadata-schemas/{res.data['id']}").status_code == 204


def test_schema_in_use_cannot_be_deleted(admin_client, inline_jobs):
    upload(admin_client, pdf_file("certificates/C01_ISO9001_인증서.pdf"))
    schema = MetadataSchema.objects.get(code="certificate")
    assert admin_client.delete(f"/api/metadata-schemas/{schema.id}").status_code == 400
    res = admin_client.post(f"/api/metadata-schemas/{schema.id}/reextract")
    assert res.data["count"] == 1


def test_load_initial_data_endpoint(admin_client, manager_client, inline_jobs):
    assert manager_client.post("/api/admin/load-initial-data").status_code == 403
    res = admin_client.post("/api/admin/load-initial-data", {"mode": "skip"}, format="json")
    assert res.status_code == 202
    assert res.data["job"]["status"] == "SUCCEEDED"
    assert res.data["job"]["result"]["company"]["created"] == 19
    assert Product.objects.count() == 6
