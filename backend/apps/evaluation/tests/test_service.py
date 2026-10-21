"""EVALUATE_BID service: rules first, LLM assist, manual edits protected (specs/08 §7–8)."""

import re

import pytest

from apps.bids.models import BidItem, BidNotice, BidRequirement
from apps.company.models import Product
from apps.core.app_settings import set_setting
from apps.evaluation.models import RequirementEvaluation
from apps.evaluation.service import (
    evaluate_bid,
    merge,
    revert_evaluation,
    template_answer,
    update_evaluation,
)
from apps.llm.providers import LLMError

pytestmark = pytest.mark.django_db


@pytest.fixture
def bid(company_data):
    bid = BidNotice.objects.create(title="GT 흡기 필터", buyer_org="가상발전")
    item = BidItem.objects.create(
        bid=bid,
        item_no="1",
        name="V-bank",
        filter_type="V_BANK",
        matched_product=Product.objects.get(model_no="FT-VB500"),
    )
    BidRequirement.objects.create(
        bid=bid,
        item=item,
        category="DIMENSION",
        title="치수",
        requirement_text="592×592×292",
        normalized={"w": 592, "h": 592, "d": 292},
        source_quote="Size 592x592x292",
        order=0,
    )
    BidRequirement.objects.create(
        bid=bid,
        category="CERTIFICATION",
        title="ISO 14001",
        normalized={"cert_type": "ISO14001"},
        order=1,
    )
    BidRequirement.objects.create(
        bid=bid,
        category="WARRANTY",
        title="하자보증",
        requirement_text="2년",
        normalized={"months": 24},
        order=2,
    )
    return bid


def by_category(bid, category) -> RequirementEvaluation:
    return RequirementEvaluation.objects.get(requirement__bid=bid, requirement__category=category)


def judge_responder(make):
    """Answer evaluation.judge with make(requirement_id) for every requirement in the prompt."""

    def respond(request):
        ids = [int(i) for i in re.findall(r'<requirement id="(\d+)">', request.user)]
        return {"results": [make(i) for i in ids]}

    return respond


def llm_result(rid, verdict="MET", risk="LOW", refs=True):
    return {
        "requirement_id": rid,
        "verdict": verdict,
        "risk_level": risk,
        "company_value": "LLM 값",
        "auto_answer": f"LLM 답변 {rid}",
        "rationale": "LLM 근거",
        "action_items": ["LLM 조치"],
        "clarification_question": "",
        "evidence_refs": [
            {"type": "document", "id": 1, "label": "회사 소개서", "page": 2, "quote": "q"}
        ]
        if refs
        else [],
    }


def test_rules_only_without_llm(bid):
    result = evaluate_bid(bid)
    bid.refresh_from_db()
    assert bid.processing_status == "EVALUATED"
    assert result["evaluated"] == 3 and result["llm_used"] is False

    dim = by_category(bid, "DIMENSION")
    assert (dim.verdict, dim.decided_by) == ("MET", "RULE")
    assert dim.auto_answer.startswith("충족 — FT-VB500")
    assert {e["type"] for e in dim.evidences} == {"product", "bid_quote"}
    assert dim.ai_verdict == "MET" and dim.history.count() == 1

    cert = by_category(bid, "CERTIFICATION")
    assert (cert.verdict, cert.risk_level) == ("NEEDS_SUPPLEMENT", "HIGH")
    assert cert.auto_answer.startswith("보완 필요 — ")

    warranty = by_category(bid, "WARRANTY")  # no rule, no LLM → never MET
    assert warranty.verdict == "NEEDS_CONFIRMATION"

    assert bid.extra["verdict_counts"] == {
        "MET": 1,
        "NEEDS_SUPPLEMENT": 1,
        "NEEDS_CONFIRMATION": 1,
        "HIGH": 1,
        "total": 3,
    }


def test_llm_cannot_override_rule_verdict(bid, fake_llm):
    fake_llm.reset(responder=judge_responder(lambda rid: llm_result(rid, "MET", "HIGH")))
    evaluate_bid(bid)
    cert = by_category(bid, "CERTIFICATION")
    assert cert.verdict == "NEEDS_SUPPLEMENT"  # rule verdict kept
    assert cert.decided_by == "RULE+LLM"
    assert cert.auto_answer.startswith("LLM 답변")
    assert "LLM 조치" in cert.action_items
    assert cert.llm_call is not None

    dim = by_category(bid, "DIMENSION")
    assert dim.verdict == "MET" and dim.risk_level == "HIGH"  # risk = max(rule, LLM)

    warranty = by_category(bid, "WARRANTY")
    assert (warranty.verdict, warranty.decided_by) == ("MET", "LLM")
    assert warranty.evidences[0]["label"] == "회사 소개서"


def test_llm_met_without_evidence_is_downgraded(bid, fake_llm):
    fake_llm.reset(responder=judge_responder(lambda rid: llm_result(rid, refs=False)))
    evaluate_bid(bid)
    warranty = by_category(bid, "WARRANTY")
    assert warranty.verdict == "NEEDS_CONFIRMATION"
    assert "근거 자료가 제시되지 않아" in warranty.rationale


def test_llm_failure_falls_back(bid, fake_llm):
    fake_llm.reset(LLMError("timeout"))
    evaluate_bid(bid)
    assert by_category(bid, "DIMENSION").decided_by == "RULE"
    assert by_category(bid, "WARRANTY").verdict == "NEEDS_CONFIRMATION"


def test_batches_follow_setting(bid, fake_llm):
    set_setting("evaluation.batch_size", 2)
    fake_llm.reset(responder=judge_responder(llm_result))
    evaluate_bid(bid)
    assert len(fake_llm.requests) == 2


def test_use_llm_setting_off(bid, fake_llm):
    set_setting("evaluation.use_llm", False)
    fake_llm.reset(responder=judge_responder(llm_result))
    evaluate_bid(bid)
    assert fake_llm.requests == []


def test_manual_edit_kept_and_revert(bid, manager_user):
    evaluate_bid(bid)
    cert = by_category(bid, "CERTIFICATION")
    update_evaluation(
        cert, {"verdict": "MET", "auto_answer": "갱신 완료", "action_items": []}, manager_user
    )
    cert.refresh_from_db()
    assert cert.is_modified and cert.decided_by == "MANUAL"
    assert cert.ai_verdict == "NEEDS_SUPPLEMENT"
    bid.refresh_from_db()
    assert bid.extra["verdict_counts"]["MET"] == 2

    evaluate_bid(bid)  # keep_modified=True by default
    cert.refresh_from_db()
    assert cert.verdict == "MET" and cert.is_modified

    revert_evaluation(cert, manager_user)
    cert.refresh_from_db()
    assert (cert.verdict, cert.is_modified) == ("NEEDS_SUPPLEMENT", False)
    assert cert.auto_answer.startswith("보완 필요")

    update_evaluation(cert, {"verdict": "MET"}, manager_user)
    evaluate_bid(bid, keep_modified=False)
    cert.refresh_from_db()
    assert (cert.verdict, cert.is_modified) == ("NEEDS_SUPPLEMENT", False)
    assert cert.history.filter(changed_by=manager_user).count() == 3


def test_selected_requirements_only(bid):
    target = bid.requirements.get(category="DIMENSION")
    result = evaluate_bid(bid, requirement_ids=[target.pk])
    assert result["evaluated"] == 1
    assert RequirementEvaluation.objects.filter(requirement__bid=bid).count() == 1


def test_template_answers():
    assert template_answer("MET", "130 Pa", "r", []) == "충족 — 130 Pa"
    assert template_answer("NEEDS_SUPPLEMENT", "", "성적서 없음.", ["시험 의뢰"]) == (
        "보완 필요 — 성적서 없음. 시험 의뢰 예정."
    )
    assert template_answer("NEEDS_CONFIRMATION", "", "확인 필요함", []) == "확인 필요 — 확인 필요함"


def test_merge_placeholder_question(bid):
    requirement = BidRequirement(bid=bid, category="SUBMISSION_DOC", title="x", normalized={})
    from apps.evaluation import rules

    data = merge(
        requirement,
        rules.RuleResult("NEEDS_CONFIRMATION", "MEDIUM", "r", trace={"question": "Q?"}),
        None,
    )
    assert data["clarification_question"] == "Q?"
