import copy
import hashlib
from datetime import timedelta

import pytest
from django.core.files.base import ContentFile
from django.utils import timezone

from apps.bids.models import BidAttachment, BidItem, BidNotice, BidProductMatch, BidRequirement
from apps.company.models import Certificate, Company, Product, TestReport
from apps.core.app_settings import set_setting
from apps.core.freshness import FreshnessReader, InputsChanged
from apps.documents.models import Document, DocumentMetadata
from apps.documents.tests.test_locations import pdf_bytes
from apps.evaluation import assessment, formal_sources, rules, service
from apps.evaluation.context import EvaluationContext
from apps.evaluation.models import EvaluationHistory, RequirementEvaluation
from apps.evaluation.serializers import EvaluationSerializer

pytestmark = pytest.mark.django_db


def document(text, owner="COMPANY"):
    data = text.encode()
    doc = Document(
        owner_type=owner,
        file_format="TXT",
        extracted_text=text,
        sha256=hashlib.sha256(data).hexdigest(),
    )
    doc.file.save("synthetic.txt", ContentFile(data), save=False)
    doc.save()
    return doc


@pytest.fixture
def case(monkeypatch):
    set_setting("evaluation.use_llm", False)
    company = Company.objects.create(name="합성기업", is_sme=True)
    doc = document("SYNTHETIC-ONE SYNTHETIC-TWO EPDM urethane MERV 15 F9")
    p = Product.objects.create(
        model_no="SYNTHETIC-ONE",
        media="Synthetic Fiber (F9)",
        gasket="urethane",
        en779_class="F9",
        ashrae_merv=15,
        source_document=doc,
    )
    other = Product.objects.create(
        model_no="SYNTHETIC-TWO", ashrae_merv=15, en779_class="F9", source_document=doc
    )
    bid = BidNotice.objects.create(title="합성 과거 공고")
    one = BidItem.objects.create(bid=bid, item_no="1", matched_product=p)
    two = BidItem.objects.create(bid=bid, item_no="2")
    for product in (p, other):
        BidProductMatch.objects.create(
            bid=bid, item=two, product=product, rank=product.pk, score=50
        )
    return {
        "bid": bid,
        "company": company,
        "p": p,
        "other": other,
        "one": one,
        "two": two,
        "doc": doc,
    }


def requirement(case, category, normalized, *, item=None, quote="", text=""):
    attachment = None
    if quote:
        attachment = BidAttachment.objects.create(
            bid=case["bid"], document=document(text or quote, "BID")
        )
    return BidRequirement.objects.create(
        bid=case["bid"],
        item=item,
        category=category,
        title="합성 요구",
        normalized=normalized,
        requirement_text=text,
        source_quote=quote,
        source_attachment=attachment,
    )


def evaluate(case, req):
    return rules.evaluate(req, EvaluationContext.for_bid(case["bid"], read_only=True))


def review():
    return {"status": "NEEDS_CONFIRMATION", "reason": "old unresolved interpretation"}


def test_review_rechecks_known_failure_without_selecting_second_item(case):
    req = requirement(
        case,
        "MATERIAL",
        {"part": "gasket", "required": ["EPDM"], "interpretation_review": review()},
    )
    old = copy.deepcopy(req.normalized)
    rr = evaluate(case, req)
    assert rr.verdict == "NEEDS_SUPPLEMENT"
    assert any(c["actual"] == "urethane" for c in rr.trace["assessment"]["checks"])
    case["two"].refresh_from_db()
    req.refresh_from_db()
    assert case["two"].matched_product_id is None and req.normalized == old


def test_known_pass_releases_only_comparable_review(case):
    case["p"].gasket = "EPDM"
    case["p"].save()
    req = requirement(
        case,
        "MATERIAL",
        {"part": "gasket", "required": ["EPDM"], "interpretation_review": review()},
        item=case["one"],
    )
    rr = evaluate(case, req)
    assert rr.verdict == "MET"
    assert rr.trace["assessment"]["interpretation_revalidation"]["status"] == "RESOLVED"
    assert rr.trace["assessment"]["interpretation_revalidation"]["original_review"] == review()


def test_synonym_match_does_not_prove_purity_or_discharge(case):
    req = requirement(
        case,
        "MATERIAL",
        {
            "part": "media",
            "required": ["100% Synthetic media(discharged)"],
            "interpretation_review": review(),
        },
        item=case["one"],
    )
    rr = evaluate(case, req)
    assert rr.verdict == "NEEDS_CONFIRMATION"
    checks = rr.trace["assessment"]["checks"]
    assert checks[0]["status"] == "MET"  # Family is known; qualifiers are not.
    assert {v["key"] for v in rr.trace["assessment"]["missing_inputs"]} == {
        f"products.{case['p'].pk}.media.purity",
        f"products.{case['p'].pk}.media.discharged",
    }


def test_all_candidates_same_grade_proves_attribute_without_selecting(case):
    req = requirement(
        case, "FILTER_GRADE", {"standard": "ASHRAE52_2", "class": "MERV 15", "operator": ">="}
    )
    rr = evaluate(case, req)
    assert rr.verdict == "MET"
    item = rr.trace["assessment"]["item_comparisons"][1]
    assert item["selection_independent_attribute"] and item["selected_product_id"] is None
    case["other"].ashrae_merv = 12
    case["other"].save()
    assert evaluate(case, req).verdict == "NEEDS_CONFIRMATION"


def test_source_change_prevents_releasing_grade(case):
    req = requirement(
        case, "FILTER_GRADE", {"standard": "ASHRAE52_2", "class": "MERV 15"}, item=case["one"]
    )
    assert evaluate(case, req).verdict == "MET"
    with case["doc"].file.open("wb") as stream:
        stream.write(b"changed")
    assert evaluate(case, req).verdict == "NEEDS_CONFIRMATION"


def test_grade_edition_remains_unknown_when_class_is_known(case):
    req = requirement(
        case,
        "FILTER_GRADE",
        {
            "standard": "EN779",
            "edition": "2012",
            "class": "F9",
            "operator": ">=",
            "interpretation_review": review(),
        },
        item=case["one"],
    )
    rr = evaluate(case, req)
    assert rr.verdict == "NEEDS_CONFIRMATION"
    assert rr.trace["assessment"]["checks"][0]["status"] == "MET"
    assert any("standard_edition" in m["key"] for m in rr.trace["assessment"]["missing_inputs"])


@pytest.mark.parametrize(
    "measured,expected", [(96, "MET"), (94, "NEEDS_SUPPLEMENT"), (None, "NEEDS_CONFIRMATION")]
)
def test_measured_efficiency_known_pass_fail_and_unknown(case, measured, expected):
    req = requirement(
        case,
        "EFFICIENCY",
        {
            "value": 95.4,
            "operator": ">=",
            "metric": "avg_eff_0_4um",
            "test_standard": "EN779",
            "interpretation_review": review(),
        },
        item=case["one"],
    )
    if measured is not None:
        TestReport.objects.create(
            report_no="SYNTHETIC",
            product=case["p"],
            standard="EN779:2012",
            standard_family="EN779",
            results={"0.4 평균": measured},
            source_document=case["doc"],
        )
    assert evaluate(case, req).verdict == expected


def test_notice_and_future_work_never_claim_completed_company_work(case):
    req = requirement(case, "WARRANTY", {"months": 24}, quote="하자담보책임기간: 2년")
    rr = evaluate(case, req)
    assert rr.verdict == "MET" and rr.trace["assessment"]["scope"] == "FUTURE_OBLIGATION"
    assert rr.trace["assessment"]["current_company_verdict"] == "NOT_APPLICABLE"
    assert rr.trace["assessment"]["follow_up_tasks"][0]["state"] == "OPEN"
    assert not rr.trace["assessment"]["submission_ready"]


def test_wrong_source_quote_cannot_verify_work_definition(case):
    req = requirement(
        case, "WARRANTY", {"months": 24}, quote="하자담보책임기간: 2년", text="다른 원문"
    )
    assert evaluate(case, req).verdict == "NEEDS_CONFIRMATION"


def test_matching_quote_but_wrong_normalized_duration_is_not_verified(case):
    req = requirement(case, "WARRANTY", {"months": 48}, quote="하자담보책임기간: 2년")
    assert evaluate(case, req).verdict == "NEEDS_CONFIRMATION"


def test_explicit_additional_quote_resolves_existing_source_without_replacing_it(case):
    from apps.documents.locations import text_digest

    original = "합성 확약서 제출"
    actual = "합성 ‘확약서’ 제출: 계약 시 작성"
    req = requirement(
        case,
        "SUBMISSION_DOC",
        {"doc": "확약서", "issuer_type": "COMPANY"},
        quote=original,
        text=actual,
    )
    doc = req.source_attachment.document
    meta = DocumentMetadata.objects.create(
        document=doc,
        key=f"manual_requirement_revalidation.{req.pk}",
        source="MANUAL",
        value={
            "requirement_id": req.pk,
            "original_quote": original,
            "reviewed_quote": actual,
            "source_sha256": doc.sha256,
            "text_sha256": text_digest(actual),
        },
    )
    rr = evaluate(case, req)
    assert rr.verdict == "MET"
    proof = rr.trace["assessment"]["notice_source"]
    assert (
        proof["status"] == "EXACT_MATCH"
        and proof["original_location"]["status"] == "QUOTE_NOT_FOUND"
    )
    req.refresh_from_db()
    assert req.source_quote == original
    meta.value["source_sha256"] = "b" * 64
    meta.save()
    assert evaluate(case, req).verdict == "NEEDS_CONFIRMATION"


def component_metadata(case):
    doc = case["doc"]
    data = pdf_bytes(3)
    doc.file.save("synthetic.pdf", ContentFile(data), save=False)
    doc.file_format = "PDF"
    doc.sha256 = hashlib.sha256(data).hexdigest()
    doc.save()
    value = {
        "product_id": case["p"].pk,
        "source_sha256": doc.sha256,
        "physical_page": 3,
        "values": {"liner": "Galvanized steel", "end_cap": "Galvanized steel"},
        "evidence": [
            {"field": part, "quote": part + " Galvanized steel"} for part in ["liner", "end_cap"]
        ],
    }
    return DocumentMetadata.objects.create(
        document=doc, key=f"manual_product_components.{case['p'].pk}", value=value, source="MANUAL"
    )


def test_existing_component_material_is_reused_and_only_finish_is_requested(case):
    component_metadata(case)
    req = requirement(
        case,
        "MATERIAL",
        {
            "part": "liner",
            "parts": ["liner", "end_cap"],
            "required": ["Galvanized With Powder Coated", "Stainless Steel"],
            "interpretation_review": review(),
        },
        item=case["one"],
    )
    rr = evaluate(case, req)
    assert rr.verdict == "NEEDS_CONFIRMATION"
    assert (
        sum(
            c["status"] == "MET" and "base_material" in c["field"]
            for c in rr.trace["assessment"]["checks"]
        )
        == 2
    )
    assert all(v["key"].endswith(".finish") for v in rr.trace["assessment"]["missing_inputs"])


@pytest.mark.parametrize("change", ["hash", "page", "field", "product"])
def test_invalid_component_review_does_not_release_any_value(case, change):
    meta = component_metadata(case)
    value = meta.value
    if change == "hash":
        value["source_sha256"] = "f" * 64
    elif change == "page":
        value["physical_page"] = 4
    elif change == "field":
        value["evidence"][0]["quote"] = "unrelated"
    else:
        value["product_id"] = 999
    meta.save()
    assert (
        assessment.component_values(
            case["p"], EvaluationContext.for_bid(case["bid"], read_only=True)
        )
        == {}
    )


def test_environment_known_upper_limits_do_not_resolve_lower_limit(case):
    p = case["p"]
    p.max_temp_c = 80
    p.max_rh = 100
    p.save()
    req = requirement(
        case,
        "ENVIRONMENT",
        {"max_temp_c": 60, "max_rh": 100, "min_temp_c": None, "interpretation_review": review()},
        item=case["one"],
    )
    rr = evaluate(case, req)
    assert rr.verdict == "NEEDS_CONFIRMATION"
    assert sum(c["status"] == "MET" for c in rr.trace["assessment"]["checks"]) >= 2
    assert any(m["key"] == "notice.min_temp_c" for m in rr.trace["assessment"]["missing_inputs"])


def sme(case, monkeypatch, *, until=None, holder=None):
    today = timezone.localdate()
    cert = Certificate.objects.create(
        cert_no="SYNTHETIC-SME",
        cert_type="SME",
        holder=holder or case["company"].name,
        valid_from=today - timedelta(days=5),
        valid_until=until or today + timedelta(days=30),
        source_document=case["doc"],
    )
    monkeypatch.setattr(
        formal_sources.SourceLocator,
        "manual_locations",
        lambda self, **kwargs: [
            {
                "document_id": case["doc"].pk,
                "document_sha256": case["doc"].sha256,
                "declared_page": 1,
                "quote": "SYNTHETIC-SME",
                "status": "MANUAL_REVIEWED_PAGE",
                "quote_status": "HUMAN_TRANSCRIBED_NOT_MACHINE_CHECKED",
                "source_verification": "VERIFIED",
                "record_value_consistency": "MATCHES_REVIEW",
                "fields": ["holder", "valid_from", "valid_until"],
            }
        ],
    )
    return cert


def test_sme_general_route_does_not_require_cooperative_or_special_entity(case, monkeypatch):
    sme(case, monkeypatch)
    req = requirement(
        case, "CERTIFICATION", {"cert_type": "SME", "interpretation_review": review()}
    )
    rr = evaluate(case, req)
    assert rr.verdict == "MET"
    a = rr.trace["assessment"]
    assert all(
        x["status"] == "NOT_NEEDED_FOR_GENERAL_ROUTE"
        for x in a["qualification_routes"]["exceptions"]
    )
    assert a["follow_up_tasks"][0]["state"] == "OPEN" and not a["final_bid_eligibility_verified"]
    assert not a["missing_inputs"]


@pytest.mark.parametrize(
    "kind,expected",
    [
        ("expired", "NEEDS_SUPPLEMENT"),
        ("wrong_holder", "NEEDS_CONFIRMATION"),
        ("absent", "NEEDS_CONFIRMATION"),
    ],
)
def test_sme_invalid_or_missing_evidence_is_not_met(case, monkeypatch, kind, expected):
    if kind != "absent":
        sme(
            case,
            monkeypatch,
            until=timezone.localdate() - timedelta(days=1) if kind == "expired" else None,
            holder="다른 합성기업" if kind == "wrong_holder" else None,
        )
    req = requirement(
        case, "CERTIFICATION", {"cert_type": "SME", "interpretation_review": review()}
    )
    assert evaluate(case, req).verdict == expected


def test_inputs_deduplicated_and_manual_assessment_not_reused(case):
    reqs = [requirement(case, "DIMENSION", {"dia": 200}, item=case["two"]) for _ in range(2)]
    service.evaluate_bid(case["bid"], rules_first=True)
    rows = list(RequirementEvaluation.objects.filter(requirement__in=reqs))
    requests = assessment.input_requests(rows)
    assert len(requests) == 1 and set(requests[0]["requirement_ids"]) == {r.pk for r in reqs}
    service.update_evaluation(rows[0], {"verdict": "MET"}, None)
    assert EvaluationSerializer(rows[0]).data["assessment"]["status"] == "MANUAL_REVIEW_REQUIRED"
    before = rows[0].snapshot()
    service.evaluate_bid(case["bid"], keep_modified=True, rules_first=True)
    rows[0].refresh_from_db()
    assert rows[0].snapshot() == before


def test_run_history_contains_assessment_and_does_not_modify_requirements(case):
    req = requirement(
        case,
        "MATERIAL",
        {"part": "gasket", "required": ["EPDM"], "interpretation_review": review()},
        item=case["one"],
    )
    before = copy.deepcopy(req.normalized)
    service.evaluate_bid(case["bid"], rules_first=True)
    ev = RequirementEvaluation.objects.get(requirement=req)
    assert ev.verdict == "NEEDS_SUPPLEMENT"
    assert ev.history.first().snapshot["rule_trace"]["assessment"]
    assert FreshnessReader().result(ev)["status"] == "CURRENT"
    req.refresh_from_db()
    assert req.normalized == before


def test_input_change_aborts_all_revalidated_results(case, monkeypatch):
    req = requirement(
        case, "FILTER_GRADE", {"class": "MERV 15", "standard": "ASHRAE52_2"}, item=case["one"]
    )
    service.evaluate_bid(case["bid"], rules_first=True)
    previous = RequirementEvaluation.objects.get(requirement=req).snapshot()
    history = EvaluationHistory.objects.count()
    original = service.rules.evaluate

    def changed(req, ctx):
        result = original(req, ctx)
        Product.objects.filter(pk=case["p"].pk).update(ashrae_merv=12)
        return result

    monkeypatch.setattr(service.rules, "evaluate", changed)
    with pytest.raises(InputsChanged):
        service.evaluate_bid(case["bid"], rules_first=True)
    assert RequirementEvaluation.objects.get(requirement=req).snapshot() == previous
    assert EvaluationHistory.objects.count() == history
