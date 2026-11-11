"""Synthetic catalog evidence boundaries; no private company fixtures or real LLM calls."""

import pytest

from apps.bids.models import BidItem, BidNotice, BidProductMatch, BidRequirement
from apps.company.models import DeliveryRecord, Product, TestReport
from apps.documents.models import Document
from apps.evaluation import rules
from apps.evaluation.comparison import comparison
from apps.evaluation.context import EvaluationContext
from apps.evaluation.evidence import company_evidence, evidence_document_map
from apps.evaluation.matching import match_items
from apps.evaluation.models import RequirementEvaluation
from apps.evaluation.service import (
    evaluate_bid,
    merge,
    update_evaluation,
    validate_judgment_sources,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def case(fake_llm):
    document = Document.objects.create(
        owner_type="COMPANY",
        file_format="PDF",
        page_count=3,
        extracted_text="SYNTHETIC-A",
        original_filename="synthetic.pdf",
        status="PARSED",
    )
    product = Product.objects.create(
        model_no="SYNTHETIC-A",
        filter_type="CARTRIDGE_PULSE",
        diameter_mm=320,
        length_mm=650,
        dimension_text="OD320 x L650",
        en779_class="F9",
        source_document=document,
        extra={
            "manufacturer_source": {"page": 3, "quote": "SYNTHETIC-A", "section": "synthetic row"},
            "manufacturer_claims": {
                "EFFICIENCY": {
                    "display": "manufacturer lower bound >=95%; unknown test conditions",
                    "value": 95,
                    "operator": ">=",
                    "scope": "PAIR",
                },
                "PRESSURE_DROP": {"display": "pair <=150 Pa at 2700 m3/h", "scope": "PAIR"},
            },
        },
    )
    bid = BidNotice.objects.create(title="synthetic comparison")
    item = BidItem.objects.create(
        bid=bid,
        item_no="1",
        name="synthetic",
        diameter_mm=320,
        length_mm=650,
        filter_type="CARTRIDGE_PULSE",
    )
    req = BidRequirement.objects.create(
        bid=bid,
        item=item,
        category="DIMENSION",
        normalized={"dia": 320, "len": 650},
        title="synthetic dimensions",
    )
    BidProductMatch.objects.create(bid=bid, item=item, product=product, score=0.8, rank=1)
    return bid, item, req, product


def test_candidate_dimensions_are_compared_without_becoming_selected(case):
    bid, item, req, product = case
    result = rules.evaluate(req, EvaluationContext.for_bid(bid))
    assert result.verdict == "NEEDS_CONFIRMATION"
    assert result.trace["candidate_comparisons"][0]["candidate_verdict"] == "MET"
    assert "OD320" in result.company_value
    item.refresh_from_db()
    assert item.matched_product_id is None
    assert (
        evidence_document_map([result.evidences])[("product", product.pk)]
        == product.source_document_id
    )
    assert result.evidences[0]["page"] == 3 and result.evidences[0]["quote"] == "SYNTHETIC-A"


@pytest.mark.parametrize("diameter,expected", [(320, "MET"), (400, "NEEDS_SUPPLEMENT")])
def test_confirmed_direct_dimension_match_and_actual_shortfall_remain_distinct(
    case, diameter, expected
):
    bid, item, req, product = case
    item.matched_product = product
    item.save()
    req.normalized = {"dia": diameter, "len": 650}
    req.save()
    assert rules.evaluate(req, EvaluationContext.for_bid(bid)).verdict == expected


def test_unregistered_product_is_unknown(case):
    bid, item, req, product = case
    BidProductMatch.objects.all().delete()
    assert rules.evaluate(req, EvaluationContext.for_bid(bid)).verdict == "NEEDS_CONFIRMATION"


@pytest.mark.parametrize(
    "shape,expected",
    [("CYLINDRICAL", "MET"), ("CONICAL", "NEEDS_SUPPLEMENT"), (None, "NEEDS_CONFIRMATION")],
)
def test_cartridge_type_does_not_hide_shape_mismatch(case, shape, expected):
    bid, item, req, product = case
    req.category = "FILTER_TYPE"
    req.normalized = {"type": "CARTRIDGE_PULSE", "shape": "CYLINDRICAL"}
    product.extra = {**product.extra, "shape": shape}
    product.save()
    result = rules.evaluate(req, EvaluationContext.for_bid(bid))
    assert result.verdict == "NEEDS_CONFIRMATION"
    assert result.trace["candidate_comparisons"][0]["candidate_verdict"] == expected


def test_missing_delivery_record_is_unknown_but_explicit_amount_shortfall_remains(case):
    bid, item, req, product = case
    req.category = "TRACK_RECORD"
    req.normalized = {
        "period_years": 10,
        "product_types": ["CARTRIDGE_PULSE"],
        "min_amount_krw": 200,
    }
    ctx = EvaluationContext.for_bid(bid)
    assert rules.evaluate(req, ctx).verdict == "NEEDS_CONFIRMATION"
    record = DeliveryRecord.objects.create(
        delivered_ym=f"{ctx.reference_date.year}-01", client="synthetic", amount_krw=100
    )
    record.products.add(product)
    result = rules.evaluate(req, EvaluationContext.for_bid(bid))
    assert result.verdict == "NEEDS_SUPPLEMENT"
    assert result.evidences[0]["page"] == 0 and result.evidences[0]["quote"] == ""


@pytest.mark.parametrize(
    "category,norm",
    [
        ("ENVIRONMENT", {"min_temp_c": 40, "max_temp_c": 60}),
        ("PRESSURE_DROP", {"metric": "test_endpoint_dp", "value": 450}),
        ("AIRFLOW", {"value": 1000000, "comparison_scope": "SYSTEM"}),
        (
            "MATERIAL",
            {"part": "liner", "required": ["coated", "stainless"], "required_operator": "ANY"},
        ),
        ("SUBMISSION_DOC", {"doc": "QIP", "applicability": "when required"}),
    ],
)
def test_reviewed_uncertainty_blocks_rules_and_generated_answer(case, category, norm):
    bid, item, req, product = case
    req.category = category
    req.normalized = {
        **norm,
        "interpretation_review": {
            "status": "NEEDS_CONFIRMATION",
            "reason": "synthetic unresolved condition",
        },
    }
    rr = rules.evaluate(req, EvaluationContext.for_bid(bid))
    merged = merge(
        req, rr, {"verdict": "MET", "auto_answer": "invented success", "rationale": "invented"}
    )
    assert merged["verdict"] == "NEEDS_CONFIRMATION" and "invented" not in merged["auto_answer"]
    assert "synthetic unresolved condition" in merged["rationale"]


def test_lower_bound_is_not_a_measured_shortfall_and_pair_is_not_individual(case):
    bid, item, req, product = case
    req.category = "EFFICIENCY"
    req.normalized = {"metric": "avg_eff_0_4um", "value": 95.4, "operator": ">="}
    result = rules.evaluate(req, EvaluationContext.for_bid(bid))
    assert result.verdict == "NEEDS_CONFIRMATION"
    assert result.trace["candidate_comparisons"][0]["candidate_verdict"] == "NEEDS_CONFIRMATION"
    assert product.rated_airflow_m3h is None and product.initial_dp_pa is None
    inputs = company_evidence(req, EvaluationContext.for_bid(bid))["comparison_candidates"]
    assert inputs[0]["published_claims"]["PRESSURE_DROP"]["scope"] == "PAIR"
    assert TestReport.objects.count() == 0


def test_comparison_returns_real_candidate_values_and_linked_source(case):
    bid, item, req, product = case
    row = comparison(bid)["rows"][0]
    assert row["product"] is None and "OD320" in row["product_spec"]
    assert row["comparison_candidates"][0]["source_document_id"] == product.source_document_id
    assert row["comparison_candidates"][0]["selection_status"] == "CANDIDATE_NOT_CONFIRMED"


def test_candidate_scoring_preserves_existing_manual_selection(case):
    bid, item, req, product = case
    item.matched_product = product
    item.save()
    match_items(bid, confirm=False)
    item.refresh_from_db()
    assert item.matched_product_id == product.pk


def test_self_issued_document_is_not_proof_of_readiness(case):
    bid, item, req, product = case
    req.category = "SUBMISSION_DOC"
    req.normalized = {"doc": "synthetic guarantee", "issuer_type": "COMPANY"}
    assert rules.evaluate(req, EvaluationContext.for_bid(bid)).verdict == "NEEDS_CONFIRMATION"


def test_source_validation_discards_invented_location_and_claim(case):
    bid, item, req, product = case
    out = {
        "verdict": "MET",
        "company_value": "invented",
        "auto_answer": "invented success",
        "evidence_refs": [
            {
                "type": "product",
                "id": product.pk,
                "label": "invented",
                "page": 99,
                "quote": "not present",
            }
        ],
    }
    result = validate_judgment_sources(out, EvaluationContext.for_bid(bid))
    assert result["verdict"] == "NEEDS_CONFIRMATION" and result["evidence_refs"] == []
    assert "invented" not in result["company_value"] + result["auto_answer"]


def test_unknown_llm_text_does_not_publish_unsupported_absence_or_source_locations(case):
    bid, item, req, product = case
    out = {
        "verdict": "NEEDS_CONFIRMATION",
        "rationale": "invented absence at page 99",
        "auto_answer": "invented 102 percent",
        "evidence_refs": [],
    }
    ctx = EvaluationContext.for_bid(bid)
    result = validate_judgment_sources(out, ctx, req)
    assert "invented" not in result["rationale"] + result["auto_answer"]
    assert result["_source_validation"]["unverified_generated_details_not_published"]
    # Company-level LLM inputs must include registered attributes rather than names alone.
    req.category = "WARRANTY"
    payload = company_evidence(req, ctx)
    assert payload["products"][0]["dimension_text"] == product.dimension_text


def test_comparison_and_evaluation_gets_return_consistent_sources_without_calls(
    case, manager_client, fake_llm
):
    from apps.core.models import Job
    from apps.llm.models import LLMCallLog

    bid, item, req, product = case
    evaluate_bid(bid, rules_first=True, source_scoped=True)
    before = (LLMCallLog.objects.count(), Job.objects.count())
    for _ in range(2):
        rows = manager_client.get(f"/api/bids/{bid.pk}/comparison")
        assert rows.status_code == 200
        row = rows.data["rows"][0]
        assert row["verdict"] == "NEEDS_CONFIRMATION" and row["product"] is None
        assert product.model_no in row["company_value"] and "OD320" in row["product_spec"]
        result = manager_client.get(f"/api/bids/{bid.pk}/evaluations")
        assert result.status_code == 200
        evidence = result.data["results"][0]["evidences"][0]
        assert evidence["document_id"] == product.source_document_id and evidence["page"] == 3
    assert before == (LLMCallLog.objects.count(), Job.objects.count())
    assert fake_llm.requests == []


def test_rules_first_run_sends_only_unresolved_and_preserves_manual(case, fake_llm, monkeypatch):
    from apps.evaluation import service

    bid, item, req, product = case
    unknown = BidRequirement.objects.create(
        bid=bid, category="WARRANTY", title="synthetic warranty"
    )
    calls = []

    def judge(bid, batch, ctx, job):
        calls.extend(r.pk for r, _ in batch)
        payload = service._requirement_payload(batch[0][0], None, ctx)
        assert "comparison_candidates" in payload["company_evidence"]
        return {
            unknown.pk: {
                "verdict": "NEEDS_CONFIRMATION",
                "rationale": "no commitment",
                "evidence_refs": [],
            }
        }, None

    monkeypatch.setattr(service, "_judge", judge)
    summary = evaluate_bid(bid, rules_first=True, source_scoped=True)
    assert calls == [unknown.pk] and summary["evaluated"] == 2
    saved = RequirementEvaluation.objects.get(requirement=req)
    update_evaluation(saved, {"rationale": "manual preserved"}, None)
    calls.clear()
    summary = evaluate_bid(bid, rules_first=True, source_scoped=True)
    saved.refresh_from_db()
    assert saved.rationale == "manual preserved" and saved.is_modified
    assert summary["skipped_modified"] == 1 and saved.history.count() == 2
