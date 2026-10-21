import pytest
from django.core.files.base import ContentFile

from apps.documents.models import Document, MetadataSchema
from apps.llm.models import LLMCallLog, PromptTemplate
from apps.llm.providers import LLMError

pytestmark = pytest.mark.django_db

BASE = "/api/settings/prompts"
CLASSIFY = f"{BASE}/document.classify"


def test_prompt_list_requires_admin(admin_client, manager_client):
    assert manager_client.get(BASE).status_code == 403
    rows = admin_client.get(BASE).data
    assert len(rows) == 9
    classify = next(r for r in rows if r["key"] == "document.classify")
    assert classify["variables"] == ["categories", "filename", "text_head", "has_file"]
    assert classify["version"] == 1 and classify["version_count"] == 1
    extract = next(r for r in rows if r["key"] == "document.extract_metadata")
    assert extract["dynamic_schema"] is True and extract["output_schema"] is None


def test_new_version_validation_and_rollback(admin_client):
    active = admin_client.get(CLASSIFY).data["active"]
    bad = admin_client.post(
        CLASSIFY,
        {"system_prompt": "{% if %}", "user_prompt_template": "x", "output_schema": {"type": 5}},
        format="json",
    )
    assert bad.status_code == 400
    assert {"system_prompt", "output_schema"} <= set(bad.data["errors"])

    res = admin_client.post(
        CLASSIFY,
        {
            "system_prompt": active["system_prompt"] + "\n- 추가 규칙",
            "user_prompt_template": active["user_prompt_template"],
            "output_schema": active["output_schema"],
            "notes": "규칙 추가",
        },
        format="json",
    )
    assert res.status_code == 201
    assert (res.data["version"], res.data["is_active"], res.data["notes"]) == (2, True, "규칙 추가")
    assert PromptTemplate.objects.filter(key="document.classify", is_active=True).count() == 1

    detail = admin_client.get(CLASSIFY).data
    assert [v["version"] for v in detail["versions"]] == [2, 1]
    assert [v["updated_by_name"] for v in detail["versions"]] == ["관리자2", None]

    rolled = admin_client.post(f"{CLASSIFY}/activate", {"version": 1}, format="json")
    assert rolled.data["is_active"] is True
    assert PromptTemplate.active("document.classify").version == 1
    assert (
        admin_client.post(f"{CLASSIFY}/activate", {"version": 9}, format="json").status_code == 404
    )

    reset = admin_client.post(f"{CLASSIFY}/reset")
    assert (reset.data["version"], reset.data["notes"]) == (3, "기본값으로 복원")


def test_extract_metadata_schema_stays_dynamic(admin_client):
    url = f"{BASE}/document.extract_metadata"
    active = admin_client.get(url).data["active"]
    res = admin_client.post(
        url,
        {
            "system_prompt": active["system_prompt"],
            "user_prompt_template": active["user_prompt_template"],
            "output_schema": {"type": "object"},
        },
        format="json",
    )
    assert res.data["output_schema"] is None


def test_prompt_test_requires_llm(admin_client):
    assert (
        admin_client.post(f"{CLASSIFY}/test", {"variables": {}}, format="json").status_code == 409
    )


def test_prompt_test_with_variables(admin_client, fake_llm):
    fake_llm.responses.append({"code": "", "confidence": 0.2, "reason": "모름"})
    res = admin_client.post(
        f"{CLASSIFY}/test",
        {
            "variables": {
                "categories": [],
                "filename": "a",
                "text_head": "본문",
                "has_file": False,
            },
            "user_prompt_template": "파일 {{ filename }} 분류: {{ text_head }}",
        },
        format="json",
    )
    assert res.data["ok"] is True
    assert res.data["user"] == "파일 a 분류: 본문"
    assert res.data["parsed"]["reason"] == "모름"
    log = LLMCallLog.objects.get()
    assert log.task_key == "test:document.classify" and log.prompt_version == 1
    assert PromptTemplate.objects.filter(key="document.classify").count() == 1  # nothing saved


def test_prompt_test_with_document(admin_client, fake_llm):
    schema = MetadataSchema.objects.get(code="certificate")
    document = Document.objects.create(
        owner_type="COMPANY", file_format="TXT", extracted_text="인증 번호 X-1", category=schema
    )
    fake_llm.responses.append({"fields": [], "transcript": ""})
    res = admin_client.post(
        f"{BASE}/document.extract_metadata/test", {"document_id": document.id}, format="json"
    )
    assert res.data["ok"] is True
    request = fake_llm.requests[0]
    assert "인증 번호 X-1" in request.user
    item = request.json_schema["properties"]["fields"]["items"]
    assert set(item["properties"]["key"]["enum"]) == {f["key"] for f in schema.fields}


def test_prompt_test_errors(admin_client, fake_llm):
    assert (
        admin_client.post(f"{CLASSIFY}/test", {"variables": [1]}, format="json").status_code == 400
    )
    document = Document.objects.create(owner_type="COMPANY", file_format="TXT")
    res = admin_client.post(f"{BASE}/bid.extract/test", {"document_id": document.id}, format="json")
    assert res.status_code == 400

    fake_llm.responses.extend(["oops", "still oops"])
    res = admin_client.post(
        f"{CLASSIFY}/test",
        {"variables": {"categories": [], "filename": "a", "text_head": "", "has_file": False}},
        format="json",
    )
    assert res.data["ok"] is False
    assert "형식이 올바르지 않습니다" in res.data["error"]
    assert res.data["raw_text"] == "still oops"


def test_scanned_document_test_sends_pdf(admin_client, fake_llm):
    document = Document.objects.create(
        owner_type="BID", file_format="PDF", original_filename="s.pdf"
    )
    document.file.save("s.pdf", ContentFile(b"%PDF-1.4"))
    fake_llm.responses.append({"code": "", "confidence": 0, "reason": "-"})
    admin_client.post(f"{CLASSIFY}/test", {"document_id": document.id}, format="json")
    assert fake_llm.requests[0].files[0].data == b"%PDF-1.4"


def test_app_settings_api(admin_client, manager_client):
    assert manager_client.get("/api/settings/app").status_code == 403
    groups = {
        g["group"]: g["settings"] for g in admin_client.get("/api/settings/app").data["groups"]
    }
    threshold = next(
        s for s in groups["extraction"] if s["key"] == "extraction.low_confidence_threshold"
    )
    assert (threshold["value"], threshold["default"], threshold["is_default"]) == (0.7, 0.7, True)

    res = admin_client.put(
        "/api/settings/app",
        {"values": {"extraction.low_confidence_threshold": 0.5, "jobs.concurrency": 3}},
        format="json",
    )
    assert res.status_code == 200
    bad = admin_client.put(
        "/api/settings/app",
        {"values": {"jobs.concurrency": "many", "upload.max_mb": 10, "nope.key": 1}},
        format="json",
    )
    assert bad.status_code == 400
    assert set(bad.data["errors"]) == {"jobs.concurrency", "nope.key"}
    groups = {
        g["group"]: g["settings"] for g in admin_client.get("/api/settings/app").data["groups"]
    }
    upload = next(s for s in groups["upload"] if s["key"] == "upload.max_mb")
    assert upload["value"] == 50  # rolled back with the failed batch

    reset = admin_client.post("/api/settings/app/jobs.concurrency/reset")
    assert reset.data["value"] == 2


def test_llm_logs(admin_client, manager_client, fake_llm):
    fake_llm.responses.extend([{"code": "", "confidence": 0, "reason": "-"}, LLMError("x")])
    variables = {"categories": [], "filename": "a", "text_head": "", "has_file": False}
    admin_client.post(f"{CLASSIFY}/test", {"variables": variables}, format="json")
    admin_client.post(f"{CLASSIFY}/test", {"variables": variables}, format="json")
    assert manager_client.get("/api/llm-logs").status_code == 403
    res = admin_client.get("/api/llm-logs")
    assert res.data["count"] == 2
    assert res.data["summary"]["today"]["calls"] == 2
    assert res.data["summary"]["month"]["input_tokens"] > 0
    assert admin_client.get("/api/llm-logs?status=ERROR").data["count"] == 1
    assert admin_client.get("/api/llm-logs?task_key=classify").data["count"] == 2
    row = res.data["results"][0]
    assert "response_text" not in row and "request_excerpt" not in row  # list stays light
    detail = admin_client.get(f"/api/llm-logs/{row['id']}").data
    assert "request_excerpt" in detail and "response_text" in detail
