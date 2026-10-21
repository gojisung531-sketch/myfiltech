"""Evaluation, review, comparison and dashboard endpoints (specs/10)."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.bids.models import BidItem, BidNotice, BidRequirement
from apps.company.models import Product
from apps.evaluation.service import evaluate_bid

pytestmark = pytest.mark.django_db


@pytest.fixture
def bid(company_data):
    bid = BidNotice.objects.create(title="GT 흡기 필터", buyer_org="가상발전")
    item = BidItem.objects.create(
        bid=bid,
        item_no="1",
        name="V-bank",
        matched_product=Product.objects.get(model_no="FT-VB500"),
    )
    BidRequirement.objects.create(
        bid=bid,
        item=item,
        category="FILTER_GRADE",
        title="등급",
        normalized={"standard": "EN779", "class": "F9"},
    )
    BidRequirement.objects.create(
        bid=bid, category="CERTIFICATION", title="ISO 9001", normalized={"cert_type": "ISO9001"}
    )
    return bid


def test_evaluate_needs_llm(manager_client, bid):
    response = manager_client.post(f"/api/bids/{bid.pk}/evaluate", {}, format="json")
    assert response.status_code == 409


def test_evaluate_job_inline(manager_client, bid, fake_llm, inline_jobs):
    from apps.evaluation.tests.test_service import judge_responder, llm_result

    fake_llm.reset(responder=judge_responder(llm_result))
    response = manager_client.post(
        f"/api/bids/{bid.pk}/evaluate", {"keep_modified": True}, format="json"
    )
    assert response.status_code == 202
    assert response.data["job"]["status"] == "SUCCEEDED", response.data["job"]
    data = manager_client.get(f"/api/bids/{bid.pk}/evaluations").data
    assert data["summary"]["total"] == 2
    assert {r["verdict"] for r in data["results"]} == {"MET"}


def test_evaluate_validation(manager_client, fake_llm, company_data):
    empty = BidNotice.objects.create(title="빈 공고")
    assert (
        manager_client.post(f"/api/bids/{empty.pk}/evaluate", {}, format="json").status_code == 400
    )


def test_patch_revert_history(manager_client, bid):
    evaluate_bid(bid)
    evaluation = bid.requirements.get(category="CERTIFICATION").evaluation
    url = f"/api/evaluations/{evaluation.pk}"
    response = manager_client.patch(
        url,
        {
            "verdict": "NEEDS_CONFIRMATION",
            "risk_level": "MEDIUM",
            "auto_answer": "확인 중",
            "action_items": ["인증서 원본 확인"],
            "evidences": [
                {"type": "certificate", "id": 1, "label": "ISO 9001", "page": 1, "quote": ""}
            ],
        },
        format="json",
    )
    assert response.status_code == 200, response.data
    assert response.data["is_modified"] is True
    assert response.data["decided_by"] == "MANUAL"
    assert response.data["modified_by_name"] == "담당자"
    assert response.data["ai_verdict"] == "MET"

    assert manager_client.patch(url, {"verdict": "WRONG"}, format="json").status_code == 400
    history = manager_client.get(f"{url}/history").data
    assert [h["changed_by_name"] for h in history] == ["담당자", None]

    reverted = manager_client.post(f"{url}/revert").data
    assert (reverted["verdict"], reverted["is_modified"]) == ("MET", False)


def test_requirements_include_evaluation(manager_client, bid):
    evaluate_bid(bid)
    rows = manager_client.get(f"/api/bids/{bid.pk}/requirements", {"include": "evaluation"}).data
    assert all(r["evaluation"]["verdict"] for r in rows)
    plain = manager_client.get(f"/api/bids/{bid.pk}/requirements").data
    assert "evaluation" not in plain[0]


def test_review_and_dashboard(manager_client, bid):
    BidNotice.objects.create(title="다른 공고")
    assert manager_client.get("/api/dashboard/summary").data == {
        "total": 2,
        "reviewed": 0,
        "unreviewed": 2,
    }
    response = manager_client.post(f"/api/bids/{bid.pk}/review", {"reviewed": True}, format="json")
    assert response.data["review_status"] == "REVIEWED"
    assert response.data["reviewed_by_name"] == "담당자"
    assert manager_client.get("/api/dashboard/summary").data["reviewed"] == 1
    manager_client.post(f"/api/bids/{bid.pk}/review", {"reviewed": False}, format="json")
    assert manager_client.get("/api/dashboard/summary").data["reviewed"] == 0
    assert manager_client.post(f"/api/bids/{bid.pk}/review", {}, format="json").status_code == 400


def test_comparison(manager_client, bid):
    evaluate_bid(bid)
    data = manager_client.get(f"/api/bids/{bid.pk}/comparison").data
    assert data["items"][0]["matched_model_no"] == "FT-VB500"
    grade = next(r for r in data["rows"] if r["category"] == "FILTER_GRADE")
    assert grade["product"]["model_no"] == "FT-VB500"
    assert "EN 779 F9" in grade["product_spec"]
    assert [r["label"][:13] for r in grade["test_reports"]] == ["AFT-2017-0730"]
    cert = next(r for r in data["rows"] if r["category"] == "CERTIFICATION")
    assert cert["certificates"][0]["status"] == "VALID"
    assert cert["verdict"] == "MET"


def test_list_default_order_closing_filter_and_counts(manager_client, company_data):
    now = timezone.now()
    reviewed = BidNotice.objects.create(
        title="확인됨", review_status="REVIEWED", bid_close_at=now + timedelta(days=1)
    )
    closed = BidNotice.objects.create(title="마감", bid_close_at=now - timedelta(days=3))
    soon = BidNotice.objects.create(title="임박", bid_close_at=now + timedelta(days=2))
    later = BidNotice.objects.create(title="여유", bid_close_at=now + timedelta(days=20))
    rows = manager_client.get("/api/bids").data["results"]
    assert [r["id"] for r in rows] == [soon.pk, later.pk, closed.pk, reviewed.pk]
    before = manager_client.get("/api/bids", {"closing": "before"}).data["results"]
    assert closed.pk not in [r["id"] for r in before]
    after = manager_client.get("/api/bids", {"closing": "after"}).data["results"]
    assert [r["id"] for r in after] == [closed.pk]
    assert rows[0]["verdict_counts"] == {}


def test_detail_reference_and_modified_count(manager_client, bid, manager_user):
    from apps.evaluation.service import update_evaluation

    bid.bid_close_at = timezone.now() - timedelta(days=30)
    bid.save()
    evaluate_bid(bid)
    update_evaluation(bid.requirements.first().evaluation, {"verdict": "MET"}, manager_user)
    data = manager_client.get(f"/api/bids/{bid.pk}").data
    assert data["reference"]["is_simulation"] is True
    assert data["modified_evaluation_count"] == 1
    assert data["verdict_counts"]["total"] == 2
