from datetime import date

import pytest

from apps.bids.models import BidItem, BidNotice, BidRequirement
from apps.company.models import Certificate, Company, Product
from apps.core.app_settings import set_setting
from apps.core.freshness import FreshnessReader
from apps.drafts.generators import analysis_snapshot
from apps.evaluation import formal_sources, rules, service
from apps.evaluation.context import EvaluationContext
from apps.evaluation.evidence import target_product
from apps.llm.budget import AttemptBudget, BudgetExceeded

pytestmark = pytest.mark.django_db


@pytest.fixture
def case(monkeypatch):
    Company.objects.create(name="주식회사 합성기업", is_sme=True)
    cert = Certificate.objects.create(
        name="합성 직접생산",
        cert_no="SYNTHETIC",
        cert_type="DIRECT_PRODUCTION",
        holder="합성기업",
        scope="프리필터에 한함",
        product_codes=["4016150501"],
        issuer="합성 발급처",
        issue_date=date(2026, 1, 1),
        valid_from=date(2026, 1, 1),
        valid_until=date(2027, 1, 1),
    )
    anchor = {
        "document_id": 999,
        "document_sha256": "a" * 64,
        "declared_page": 2,
        "quote": "합성기업 / 프리필터에 한함",
        "status": "MANUAL_REVIEWED_PAGE",
        "quote_status": "HUMAN_TRANSCRIBED_NOT_MACHINE_CHECKED",
        "source_verification": "VERIFIED",
        "record_value_consistency": "MATCHES_REVIEW",
        "fields": ["holder", "scope"],
    }
    monkeypatch.setattr(
        formal_sources.SourceLocator, "manual_locations", lambda self, **kwargs: [anchor]
    )
    bid = BidNotice.objects.create(title="합성 과거 공고")
    req = BidRequirement.objects.create(
        bid=bid,
        category="CERTIFICATION",
        title="직접생산",
        normalized={
            "cert_type": "DIRECT_PRODUCTION",
            "product_code": "4016150501",
            "required_note": "제안 제품 일치 및 외부 등록 확인",
        },
    )
    ctx = EvaluationContext.for_bid(bid, read_only=True)
    ctx.reference_date = date(2026, 10, 26)
    return bid, req, ctx, cert


def test_formal_payload_retains_holder_scope_dates_sources_and_unknowns(case):
    _, _, ctx, cert = case
    row = formal_sources.catalog(ctx)["certificates"][0]
    assert row["holder"] == cert.holder and row["scope"] == cert.scope
    assert row["valid_from"] == str(cert.valid_from) and row["issue_date"] == str(cert.issue_date)
    assert row["sources"][0]["declared_page"] == 2
    assert row["sources"][0]["quote_status"] == "HUMAN_TRANSCRIBED_NOT_MACHINE_CHECKED"
    assert formal_sources.catalog(ctx)["company"]["established_date"] is None


def test_certificate_presence_does_not_resolve_scope_or_external_check(case):
    _, req, ctx, _ = case
    result = formal_sources.rule_with_formal_sources(req, rules.evaluate(req, ctx), ctx)
    assert result.verdict == "NEEDS_CONFIRMATION"
    assert result.evidences[0]["document_id"] == 999
    assert result.evidences[0]["page"] == 2
    assert result.trace["formal_certificates"][0]["scope"] == "프리필터에 한함"


def test_formal_execution_saves_date_provenance_atomically(case):
    from apps.evaluation.models import RequirementEvaluation

    bid, req, _, _ = case
    set_setting("evaluation.use_llm", False)
    service.evaluate_bid(bid, rules_first=True, formal_sources=True)
    saved = RequirementEvaluation.objects.get(requirement=req)
    assert saved.rule_trace["formal_certificates"][0]["valid_from"] == "2026-01-01"
    assert saved.analysis_run.state == "COMPLETED"
    assert FreshnessReader().evaluations(bid.pk)["status"] == "CURRENT"


@pytest.mark.parametrize("field,value", [("holder", "다른기업"), ("valid_from", date(2027, 1, 1))])
def test_holder_and_start_date_can_block_fulfilment(case, field, value):
    _, req, ctx, cert = case
    req.normalized = {"cert_type": "DIRECT_PRODUCTION", "product_code": "4016150501"}
    setattr(cert, field, value)
    ctx.certificates = [cert]
    result = formal_sources.rule_with_formal_sources(req, rules.evaluate(req, ctx), ctx)
    assert result.verdict == "NEEDS_CONFIRMATION"


def test_exact_citations_only_and_no_unfounded_absence(case):
    _, req, ctx, cert = case
    ref = formal_sources.certificate_refs(formal_sources.catalog(ctx)["certificates"][0])[0]
    for bad in [{**ref, "page": 100}, {**ref, "quote": "invented"}, {**ref, "id": cert.pk + 1}]:
        out = formal_sources.validate_judgment(
            {
                "verdict": "MET",
                "rationale": "회사에 인증서가 없다",
                "evidence_refs": [bad],
            },
            ctx,
            req,
        )
        assert out["verdict"] == "NEEDS_CONFIRMATION" and out["evidence_refs"] == []
        assert "인증서가 없다" not in out["rationale"]
        assert out["_source_validation"]["rejected_refs"] == 1
    assert formal_sources.validate_judgment({"evidence_refs": [ref]}, ctx, req)[
        "evidence_refs"
    ] == [ref]


def test_common_product_condition_keeps_unselected_item(case):
    bid, _, ctx, _ = case
    p = Product.objects.create(model_no="SYNTHETIC-P")
    BidItem.objects.create(bid=bid, item_no="1", matched_product=p)
    other = BidItem.objects.create(bid=bid, item_no="2")
    req = BidRequirement(bid=bid, category="FILTER_GRADE")
    ctx.matched_products = [p]
    assert target_product(req, ctx) is None
    other.refresh_from_db()
    assert other.matched_product_id is None


def test_new_run_draft_context_never_uses_legacy_date(case):
    bid, req, _, _ = case
    set_setting("evaluation.use_llm", False)
    bid.extra = {"b5c_run": {"reference_date": "2001-01-01"}}
    bid.save()
    # Legacy is honestly unknown before any new execution.
    from apps.evaluation.models import RequirementEvaluation

    RequirementEvaluation.objects.create(requirement=req)
    assert analysis_snapshot(bid)["saved_evaluation_date"] == "미기록/혼합"
    service.evaluate_bid(bid, rules_first=True)
    context = analysis_snapshot(bid)
    assert context["saved_evaluation_date"] != "2001-01-01"
    assert context["evaluation_run_ids"]
    assert FreshnessReader().evaluations(bid.pk)["status"] == "CURRENT"


def test_budget_counts_every_attempt_and_refuses_before_overspend():
    budget = AttemptBudget(10)
    for _ in range(4):
        budget.reserve("2.40")  # failed attempts, retries and repair are never refunded
    with pytest.raises(BudgetExceeded):
        budget.reserve("0.41")
    assert len(budget.attempts) == 4 and str(budget.reserved) == "9.60"
    with pytest.raises(ValueError):
        budget.reserve("NaN")


def test_formal_judge_receives_shared_catalog_once_and_refuses_truncation(case, monkeypatch):
    from types import SimpleNamespace

    bid, req, ctx, _ = case
    req.category = "OTHER"
    called = []

    def fake(task, variables, **kwargs):
        called.append(variables)
        return SimpleNamespace(data={"results": []}, call_log=None)

    monkeypatch.setattr(service, "run_task", fake)
    service._judge(bid, [(req, None)], ctx, None, formal_sources=True)
    assert "CURRENT_FORMAL_COMPANY_DATA" in called[0]["bid_context"]
    assert "합성기업 / 프리필터에 한함" in called[0]["bid_context"]
    assert "certificates" not in called[0]["requirements"][0]["company_evidence"]
    set_setting("llm.max_input_chars", 10)
    with pytest.raises(ValueError, match="한도"):
        service._judge(bid, [(req, None)], ctx, None, formal_sources=True)
    assert len(called) == 1
