"""/api/bids endpoints (specs/10 §5)."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.bids.models import BidItem, BidNotice, BidRequirement
from apps.bids.services import add_attachment
from apps.company.models import Product

pytestmark = pytest.mark.django_db

NOTICE_TEXT = """입찰공고번호: 20240101234-00
[당진발전본부] 가스터빈 흡기 필터 구매 입찰 공고
1. 입찰에 부치는 사항
수요기관: 한국동서발전(주)당진발전본부
"""


def upload(name="공고서.txt", content=NOTICE_TEXT):
    return SimpleUploadedFile(name, content.encode("utf-8"), content_type="text/plain")


@pytest.fixture
def bid(db):
    bid = BidNotice.objects.create(title="테스트 공고", buyer_org="한국동서발전")
    add_attachment(bid, text=NOTICE_TEXT, title="공고 본문")
    return bid


def test_create_with_files_and_text(admin_client):
    response = admin_client.post(
        "/api/bids",
        {
            "title": "",
            "source_text": NOTICE_TEXT,
            "files": [upload("규격서.txt", "규격서 내용"), upload("x.exe", "MZ")],
        },
        format="multipart",
    )
    assert response.status_code == 201, response.data
    assert response.data["processing_status"] == "DRAFT"
    assert response.data["title"] == "입찰공고번호: 20240101234-00"  # first line of the text
    assert len(response.data["attachments"]) == 2
    assert [s["filename"] for s in response.data["skipped"]] == ["x.exe"]
    primaries = [a for a in response.data["attachments"] if a["is_primary"]]
    assert len(primaries) == 1


def test_create_requires_input(admin_client):
    response = admin_client.post("/api/bids", {"title": "빈"}, format="multipart")
    assert response.status_code == 400
    assert not BidNotice.objects.exists()


def test_managers_read_only(manager_client, bid):
    assert manager_client.get("/api/bids").status_code == 200
    assert manager_client.get(f"/api/bids/{bid.pk}").status_code == 200
    assert (
        manager_client.patch(f"/api/bids/{bid.pk}", {"title": "x"}, format="json").status_code
        == 403
    )
    assert manager_client.post(f"/api/bids/{bid.pk}/extract").status_code == 403
    assert manager_client.delete(f"/api/bids/{bid.pk}").status_code == 403


def test_list_filters(admin_client, bid):
    BidNotice.objects.create(title="공조 필터", is_power_plant=False, fit_score=20)
    bid.is_power_plant, bid.fit_score = True, 80
    bid.save()
    data = admin_client.get("/api/bids", {"is_power_plant": "true"}).data
    assert [b["id"] for b in data["results"]] == [bid.pk]
    assert admin_client.get("/api/bids", {"fit_min": 50}).data["count"] == 1
    assert admin_client.get("/api/bids", {"q": "공조"}).data["count"] == 1
    ordered = admin_client.get("/api/bids", {"ordering": "fit"}).data["results"]
    assert ordered[0]["id"] == bid.pk


def test_patch_locks_fields_and_unlock(admin_client, bid):
    response = admin_client.patch(
        f"/api/bids/{bid.pk}", {"title": "수정", "budget_krw": 1000}, format="json"
    )
    assert response.status_code == 200
    assert set(response.data["locked_fields"]) == {"title", "budget_krw"}
    response = admin_client.patch(
        f"/api/bids/{bid.pk}", {"unlock_fields": ["title"]}, format="json"
    )
    assert response.data["locked_fields"] == ["budget_krw"]


def test_extract_needs_llm(admin_client, bid):
    response = admin_client.post(f"/api/bids/{bid.pk}/extract")
    assert response.status_code == 409
    assert response.data["code"] == "llm_not_configured"


def test_extract_enqueues_job(admin_client, bid, fake_llm):
    response = admin_client.post(f"/api/bids/{bid.pk}/extract")
    assert response.status_code == 202
    assert response.data["job"]["type"] == "EXTRACT_BID"


def test_attachments_add_reclassify_primary_delete(admin_client, bid):
    response = admin_client.post(
        f"/api/bids/{bid.pk}/attachments",
        {"files": [upload("구매규격서.txt", "구매규격서\n규격")]},
        format="multipart",
    )
    assert response.status_code == 201
    attachments = response.data["attachments"]
    assert len(attachments) == 2
    second = next(a for a in attachments if not a["is_primary"])

    url = f"/api/bids/{bid.pk}/attachments/{second['id']}"
    assert admin_client.patch(url, {"category": "datasheet"}, format="json").status_code == 400
    response = admin_client.patch(url, {"category": "bid_spec", "is_primary": True}, format="json")
    assert response.status_code == 200
    assert response.data["role"] == "bid_spec"
    assert bid.attachments.filter(is_primary=True).get().pk == second["id"]

    assert admin_client.delete(url).status_code == 204
    assert bid.attachments.get().is_primary is True  # primary reassigned


def test_item_matched_product_by_manager(manager_client, admin_client, bid, company_data):
    item = BidItem.objects.create(bid=bid, item_no="1", name="V-bank", filter_type="V_BANK")
    product = Product.objects.get(model_no="FT-VB500")
    url = f"/api/bids/{bid.pk}/items/{item.pk}"
    assert manager_client.patch(url, {"name": "x"}, format="json").status_code == 403
    response = manager_client.patch(url, {"matched_product": product.pk}, format="json")
    assert response.status_code == 200
    assert response.data["matched_model_no"] == "FT-VB500"
    assert (
        manager_client.post(f"/api/bids/{bid.pk}/items", {"name": "y"}, format="json").status_code
        == 403
    )
    assert admin_client.patch(url, {"quantity": 10}, format="json").status_code == 200


def test_requirement_edit_locks(admin_client, bid):
    requirement = BidRequirement.objects.create(
        bid=bid, category="DELIVERY", title="납기", requirement_text="90일", source="LLM"
    )
    url = f"/api/bids/{bid.pk}/requirements/{requirement.pk}"
    response = admin_client.patch(url, {"requirement_text": "120일"}, format="json")
    assert response.data["is_locked"] is True
    assert response.data["source"] == "MANUAL"
    response = admin_client.patch(url, {"is_locked": False}, format="json")
    assert response.data["is_locked"] is False

    created = admin_client.post(
        f"/api/bids/{bid.pk}/requirements",
        {"category": "WARRANTY", "title": "하자보증", "requirement_text": "2년"},
        format="json",
    )
    assert created.status_code == 201
    assert created.data["is_locked"] is True
    listed = admin_client.get(f"/api/bids/{bid.pk}/requirements", {"category": "WARRANTY"}).data
    assert [r["id"] for r in listed] == [created.data["id"]]


def test_delete_bid_removes_documents(admin_client, bid):
    from apps.documents.models import Document

    assert admin_client.delete(f"/api/bids/{bid.pk}").status_code == 204
    assert not Document.objects.filter(owner_type="BID").exists()
