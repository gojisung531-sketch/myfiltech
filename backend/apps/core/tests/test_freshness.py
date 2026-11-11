"""Isolated provenance checks. Synthetic company/result data never enter the dev DB."""

import copy
import hashlib
from datetime import date

import pytest
from django.core.files.base import ContentFile

from apps.bids.models import BidAttachment, BidItem, BidNotice, BidRequirement
from apps.company.models import Certificate, Company, DeliveryRecord, Product, TestReport
from apps.core.app_settings import set_setting
from apps.core.freshness import FreshnessReader, InputsChanged, capture_inputs, digest
from apps.core.models import AnalysisRun, Job
from apps.documents.models import Document, DocumentMetadata
from apps.drafts import generators
from apps.drafts.models import DraftDocument
from apps.drafts.service import generate_draft, save_draft
from apps.evaluation import service
from apps.evaluation.models import EvaluationHistory, RequirementEvaluation
from apps.llm.models import LLMCallLog, LLMProviderConfig

pytestmark = pytest.mark.django_db


@pytest.fixture
def case(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("No LLM, key decryption or extraction allowed")

    from apps.documents import pipeline
    from apps.llm import services

    monkeypatch.setattr(services, "run_task", forbidden)
    monkeypatch.setattr(service, "run_task", forbidden)
    monkeypatch.setattr(generators, "run_task", forbidden)
    monkeypatch.setattr(pipeline, "run_pipeline", forbidden)
    monkeypatch.setattr(LLMProviderConfig, "get_api_key", forbidden)
    set_setting("evaluation.use_llm", False)
    company = Company.objects.create(name="Synthetic source holder")
    document = Document(
        owner_type="COMPANY",
        file_format="TXT",
        extracted_text="Synthetic source",
        sha256=hashlib.sha256(b"source").hexdigest(),
    )
    document.file.save("source.txt", ContentFile(b"source"), save=False)
    document.save()
    company.source_documents.add(document)
    meta = DocumentMetadata.objects.create(
        document=document, key="test", value={"value": 1}, source="MANUAL"
    )
    product = Product.objects.create(
        model_no="SYNTHETIC-ONE",
        width_mm=592,
        height_mm=592,
        depth_mm=292,
        source_document=document,
    )
    other = Product.objects.create(model_no="SYNTHETIC-TWO", width_mm=600)
    cert = Certificate.objects.create(
        cert_no="SYNTHETIC-CERT",
        cert_type="ISO9001",
        valid_until=date(2030, 1, 1),
        source_document=document,
    )
    report = TestReport.objects.create(
        report_no="SYNTHETIC-REPORT", product=product, source_document=document
    )
    delivery = DeliveryRecord.objects.create(
        delivered_ym="2026-01", client="Synthetic", source_document=document
    )
    delivery.products.add(product)
    bid = BidNotice.objects.create(title="Synthetic bid")
    attachment = BidAttachment.objects.create(bid=bid, document=document)
    item = BidItem.objects.create(
        bid=bid, item_no="1", matched_product=product, source_attachment=attachment
    )
    req = BidRequirement.objects.create(
        bid=bid,
        item=item,
        category="DIMENSION",
        title="Dimensions",
        normalized={"w": 592, "h": 592, "d": 292},
        source_attachment=attachment,
        source_quote="Synthetic source",
    )
    return {
        "bid": bid,
        "company": company,
        "document": document,
        "meta": meta,
        "product": product,
        "other": other,
        "cert": cert,
        "report": report,
        "delivery": delivery,
        "item": item,
        "req": req,
    }


def analyzed(case):
    service.evaluate_bid(case["bid"], rules_first=True)
    return RequirementEvaluation.objects.get(requirement=case["req"])


def fresh(obj):
    obj.refresh_from_db()
    return FreshnessReader().result(obj)


def test_new_execution_preserves_inputs_and_analysis_time(case):
    evaluation = analyzed(case)
    result = fresh(evaluation)
    assert result["status"] == "CURRENT" and not result["requires_review"]
    run = evaluation.analysis_run
    assert run.state == "COMPLETED" and digest(run.inputs) == run.input_hash
    assert result["analysis_at"] == str(run.started_at)
    assert run.inputs["components"]["company"][0]["name"] == case["company"].name
    assert run.inputs["components"]["source_files"][0]["actual_sha256"] == case["document"].sha256
    run.inputs["components"]["company"][0]["name"] = "Edited history"
    with pytest.raises(ValueError, match="immutable"):
        run.save()


@pytest.mark.parametrize(
    "change,component",
    [
        ("add_certificate", "certificates"),
        ("edit_certificate", "certificates"),
        ("delete_certificate", "certificates"),
        ("edit_company", "company"),
        ("edit_product", "products"),
        ("deactivate_product", "products"),
        ("delete_report", "test_reports"),
        ("edit_delivery", "deliveries"),
        ("delivery_link", "delivery_products"),
        ("source_unlink", "company_sources"),
        ("edit_document", "documents"),
        ("source_bytes", "source_files"),
        ("delete_source_file", "source_files"),
        ("add_metadata", "metadata"),
        ("edit_metadata", "metadata"),
        ("delete_metadata", "metadata"),
        ("edit_requirement", "requirements"),
        ("product_selection", "items"),
        ("edit_policy", "settings"),
    ],
)
def test_formal_input_changes_are_detected_without_recomputing(case, change, component):
    evaluation = analyzed(case)
    before = list(RequirementEvaluation.objects.values()), list(EvaluationHistory.objects.values())
    if change == "add_certificate":
        Certificate.objects.create(cert_no="SYNTHETIC-ADDED")
    elif change == "edit_certificate":
        case["cert"].scope = "Revised"
        case["cert"].save()
    elif change == "delete_certificate":
        case["cert"].delete()
    elif change == "edit_company":
        case["company"].phone = "Synthetic new phone"
        case["company"].save()
    elif change in ["edit_product", "deactivate_product"]:
        case["product"].width_mm = 600
        case["product"].is_active = change != "deactivate_product"
        case["product"].save()
    elif change == "delete_report":
        case["report"].delete()
    elif change == "edit_delivery":
        case["delivery"].notes = "Revised"
        case["delivery"].save()
    elif change == "delivery_link":
        case["delivery"].products.add(case["other"])
    elif change == "source_unlink":
        case["company"].source_documents.clear()
    elif change == "edit_document":
        case["document"].extracted_text += " revised"
        case["document"].save()
    elif change == "source_bytes":
        with open(case["document"].file.path, "wb") as stream:
            stream.write(b"revised raw bytes")
    elif change == "delete_source_file":
        case["document"].file.storage.delete(case["document"].file.name)
    elif change == "add_metadata":
        DocumentMetadata.objects.create(document=case["document"], key="new", value="new")
    elif change == "edit_metadata":
        case["meta"].value = {"value": 2}
        case["meta"].save()
    elif change == "delete_metadata":
        case["meta"].delete()
    elif change == "edit_requirement":
        case["req"].normalized = {"w": 600}
        case["req"].save()
    elif change == "product_selection":
        case["item"].matched_product = case["other"]
        case["item"].save()
    else:
        set_setting("evaluation.dimension_tolerance_mm", 4)
    result = fresh(evaluation)
    assert result["status"] == "STALE" and component in [r["component"] for r in result["reasons"]]
    assert before == (
        list(RequirementEvaluation.objects.values()),
        list(EvaluationHistory.objects.values()),
    )


def test_legacy_results_and_partial_old_hashes_stay_unknown(case):
    evaluation = RequirementEvaluation.objects.create(
        requirement=case["req"], verdict="NEEDS_CONFIRMATION", decided_by="RULE"
    )
    draft = DraftDocument.objects.create(
        bid=case["bid"],
        doc_type="BID_CHECKLIST",
        title="Old",
        content={"analysis_context": {"input_sha256": "0" * 64}},
    )
    for obj in [evaluation, draft]:
        result = fresh(obj)
        assert result["status"] == "UNKNOWN" and result["analysis_at"] is None
        assert (
            result["analysis_run_id"] is None
            and result["reasons"][0]["code"] == "LEGACY_INPUTS_UNKNOWN"
        )
    assert AnalysisRun.objects.count() == 0


def test_draft_has_own_inputs_and_tracks_upstream_manual_edits(case):
    evaluation = analyzed(case)
    draft = generate_draft(case["bid"], "COMPLIANCE_MATRIX", allow_llm=False)
    assert fresh(evaluation)["status"] == fresh(draft)["status"] == "CURRENT"
    assert evaluation.analysis_run_id != draft.analysis_run_id
    service.update_evaluation(evaluation, {"rationale": "Staff correction"}, None)
    assert fresh(evaluation)["manual_modified"] and fresh(evaluation)["requires_review"]
    result = fresh(draft)
    assert result["status"] == "STALE" and any(
        r["code"] == "EVALUATIONS_CHANGED" for r in result["reasons"]
    )
    assert DraftDocument.objects.get(pk=draft.pk).content == draft.content


def test_new_draft_over_unknown_evaluations_never_makes_them_current(case):
    RequirementEvaluation.objects.create(
        requirement=case["req"], verdict="NEEDS_CONFIRMATION", decided_by="RULE"
    )
    draft = generate_draft(case["bid"], "BID_CHECKLIST", allow_llm=False)
    assert fresh(draft)["status"] == "UNKNOWN"
    assert fresh(draft)["reasons"][0]["code"] == "UPSTREAM_INPUTS_UNKNOWN"


def test_changed_inputs_during_evaluation_refuse_all_results(case, monkeypatch):
    evaluation = analyzed(case)
    before = list(RequirementEvaluation.objects.values()), list(EvaluationHistory.objects.values())
    original = service.rules.evaluate

    def change(req, ctx):
        result = original(req, ctx)
        case["product"].width_mm = 601
        case["product"].save()
        return result

    monkeypatch.setattr(service.rules, "evaluate", change)
    with pytest.raises(InputsChanged):
        service.evaluate_bid(case["bid"], rules_first=True)
    assert before == (
        list(RequirementEvaluation.objects.values()),
        list(EvaluationHistory.objects.values()),
    )
    assert AnalysisRun.objects.latest("pk").state == "FAILED"
    assert fresh(evaluation)["status"] == "STALE"


def test_manual_evaluation_edit_during_execution_survives(case, monkeypatch):
    evaluation = analyzed(case)
    history_count = EvaluationHistory.objects.count()
    original = service.rules.evaluate

    def change(req, ctx):
        result = original(req, ctx)
        service.update_evaluation(evaluation, {"rationale": "Concurrent staff work"}, None)
        return result

    monkeypatch.setattr(service.rules, "evaluate", change)
    with pytest.raises(InputsChanged):
        service.evaluate_bid(case["bid"], rules_first=True)
    evaluation.refresh_from_db()
    assert evaluation.rationale == "Concurrent staff work" and evaluation.is_modified
    assert EvaluationHistory.objects.count() == history_count + 1


def test_atomic_result_failure_preserves_previous_evaluations_and_history(case, monkeypatch):
    analyzed(case)
    BidRequirement.objects.create(bid=case["bid"], title="Second", category="WARRANTY")
    before = list(RequirementEvaluation.objects.values()), list(EvaluationHistory.objects.values())
    original = service.save_evaluation
    calls = []

    def fail_second(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("Synthetic save failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(service, "save_evaluation", fail_second)
    with pytest.raises(RuntimeError):
        service.evaluate_bid(case["bid"], rules_first=True)
    assert before == (
        list(RequirementEvaluation.objects.values()),
        list(EvaluationHistory.objects.values()),
    )


def test_manual_product_selection_and_result_are_kept_on_explicit_reanalysis(case):
    evaluation = analyzed(case)
    case["item"].matched_product = case["other"]
    case["item"].save()
    service.update_evaluation(evaluation, {"auto_answer": "Manual answer"}, None)
    old_run = evaluation.analysis_run_id
    service.evaluate_bid(case["bid"], keep_modified=True, rules_first=True)
    evaluation.refresh_from_db()
    case["item"].refresh_from_db()
    assert evaluation.auto_answer == "Manual answer" and evaluation.analysis_run_id == old_run
    assert (
        case["item"].matched_product_id == case["other"].pk
        and fresh(evaluation)["status"] == "STALE"
    )


def test_manual_final_draft_is_versioned_and_concurrent_edit_is_preserved(case, monkeypatch):
    analyzed(case)
    draft = generate_draft(case["bid"], "BID_CHECKLIST", allow_llm=False)
    save_draft(draft, status="FINAL", title="Staff title")
    next_draft = generate_draft(case["bid"], "BID_CHECKLIST", allow_llm=False)
    assert next_draft.version == 2 and draft.pk != next_draft.pk
    original = generators.GENERATORS["BID_CHECKLIST"]

    def change(*args, **kwargs):
        result = original(*args, **kwargs)
        save_draft(next_draft, title="Concurrent title")
        return result

    monkeypatch.setitem(generators.GENERATORS, "BID_CHECKLIST", change)
    with pytest.raises(InputsChanged):
        generate_draft(case["bid"], "BID_CHECKLIST", allow_llm=False)
    next_draft.refresh_from_db()
    draft.refresh_from_db()
    assert next_draft.title == "Concurrent title" and next_draft.is_modified
    assert draft.title == "Staff title" and draft.status == "FINAL"
    assert DraftDocument.objects.count() == 2


def test_draft_input_change_during_generation_is_rejected(case, monkeypatch):
    analyzed(case)
    draft = generate_draft(case["bid"], "BID_CHECKLIST", allow_llm=False)
    before = list(DraftDocument.objects.values())
    original = generators.GENERATORS["BID_CHECKLIST"]

    def change(*args, **kwargs):
        result = original(*args, **kwargs)
        Certificate.objects.create(cert_no="CONCURRENT-NEW")
        return result

    monkeypatch.setitem(generators.GENERATORS, "BID_CHECKLIST", change)
    with pytest.raises(InputsChanged):
        generate_draft(case["bid"], "BID_CHECKLIST", allow_llm=False)
    assert list(DraftDocument.objects.values()) == before and fresh(draft)["status"] == "STALE"


def test_revert_keeps_original_input_identity_and_old_history_stays_unknown(case):
    evaluation = analyzed(case)
    original_run = evaluation.analysis_run_id
    service.update_evaluation(evaluation, {"auto_answer": "Manual"}, None)
    case["product"].width_mm = 603
    case["product"].save()
    service.revert_evaluation(evaluation, None)
    assert evaluation.analysis_run_id == original_run and fresh(evaluation)["status"] == "STALE"
    old = evaluation.snapshot()
    old.pop("analysis_run_id")
    EvaluationHistory.objects.create(evaluation=evaluation, snapshot=old)
    service.revert_evaluation(evaluation, None)
    assert evaluation.analysis_run_id is None and fresh(evaluation)["status"] == "UNKNOWN"


def test_unrelated_jobs_provider_keys_and_review_register_are_not_analysis_inputs(case):
    from apps.company.models import ReportRegisterRow, ReportRegisterVersion

    evaluation = analyzed(case)
    Job.objects.create(type="SYNTHETIC_PENDING")
    LLMProviderConfig.objects.filter(provider="ANTHROPIC").update(
        api_key_encrypted="UNREAD-CIPHERTEXT"
    )
    version = ReportRegisterVersion.objects.create(
        sha256="a" * 64, display_name="staging", parser_version="test"
    )
    ReportRegisterRow.objects.create(file_version=version, sheet_name="A", row_number=1)
    assert fresh(evaluation)["status"] == "CURRENT"
    assert "UNREAD-CIPHERTEXT" not in str(capture_inputs(case["bid"].pk, "EVALUATION"))


def test_corrupt_or_incomplete_run_provenance_cannot_claim_current(case):
    evaluation = analyzed(case)
    run = evaluation.analysis_run
    AnalysisRun.objects.filter(pk=run.pk).update(outputs={})
    assert fresh(evaluation)["status"] == "UNKNOWN"
    broken = copy.deepcopy(run.inputs)
    broken["schema"] = "unknown"
    AnalysisRun.objects.filter(pk=run.pk).update(inputs=broken)
    assert fresh(evaluation)["status"] == "UNKNOWN"


def test_gets_do_not_write_or_recompute_and_comparison_separates_time_contexts(
    case, manager_client
):
    evaluation = analyzed(case)
    draft = generate_draft(case["bid"], "BID_CHECKLIST", allow_llm=False)
    case["product"].width_mm = 605
    case["product"].save()
    models = [AnalysisRun, RequirementEvaluation, EvaluationHistory, DraftDocument, Job, LLMCallLog]
    before = {m._meta.label: list(m.objects.order_by("pk").values()) for m in models}
    for _ in range(2):
        summary = manager_client.get(f"/api/bids/{case['bid'].pk}/freshness")
        assert summary.status_code == 200 and summary.data["evaluations"]["status"] == "STALE"
        result = manager_client.get(f"/api/bids/{case['bid'].pk}/evaluations").data["results"][0]
        assert result["freshness"]["status"] == "STALE"
        comparison = manager_client.get(f"/api/bids/{case['bid'].pk}/comparison").data
        assert comparison["legacy_flat_fields_mix_time_contexts"] is True
        row = comparison["rows"][0]
        assert row["temporal_alignment"] == "SEPARATE_CURRENT_REFERENCE_AND_STORED_RESULT"
        assert "freshness" in row["stored_result"] and "verdict" not in row["current_reference"]
        content = manager_client.get(f"/api/bids/{case['bid'].pk}/drafts/BID_CHECKLIST").data
        assert content["freshness"]["status"] == "STALE" and content["content"] == draft.content
    assert before == {m._meta.label: list(m.objects.order_by("pk").values()) for m in models}
    assert fresh(evaluation)["status"] == "STALE"


def test_partial_execution_does_not_claim_all_requirements_current(case):
    BidRequirement.objects.create(bid=case["bid"], title="Not evaluated", category="WARRANTY")
    service.evaluate_bid(case["bid"], requirement_ids=[case["req"].pk], rules_first=True)
    summary = FreshnessReader().evaluations(case["bid"].pk)
    assert summary["status"] == "UNKNOWN" and summary["missing_evaluations"] == 1


def test_unmarked_result_edit_is_not_claimed_current(case):
    evaluation = analyzed(case)
    RequirementEvaluation.objects.filter(pk=evaluation.pk).update(rationale="Unmarked edit")
    result = fresh(evaluation)
    assert result["status"] == "UNKNOWN" and result["reasons"][0]["code"] == "UNTRACKED_RESULT_EDIT"


def test_empty_company_get_does_not_initialize_company(case, manager_client):
    case["company"].delete()
    before = AnalysisRun.objects.count()
    for path in ["freshness", "comparison"]:
        assert manager_client.get(f"/api/bids/{case['bid'].pk}/{path}").status_code == 200
    assert Company.objects.count() == 0 and AnalysisRun.objects.count() == before


def test_requirement_addition_and_deletion_are_reported(case):
    other = BidRequirement.objects.create(bid=case["bid"], title="Other", category="WARRANTY")
    evaluation = analyzed(case)
    other_id = other.pk
    other.delete()
    result = fresh(evaluation)
    assert result["status"] == "STALE"
    reason = next(r for r in result["reasons"] if r["component"] == "requirements")
    assert reason["deleted_ids"] == [other_id]
    added = BidRequirement.objects.create(bid=case["bid"], title="Added", category="WARRANTY")
    reason = next(r for r in fresh(evaluation)["reasons"] if r["component"] == "requirements")
    assert reason["added_ids"] == [added.pk]


def test_input_change_inside_result_commit_rolls_back_all_results(case, monkeypatch):
    analyzed(case)
    before = list(RequirementEvaluation.objects.values()), list(EvaluationHistory.objects.values())
    original = service.save_evaluation

    def save_and_change(*args, **kwargs):
        result = original(*args, **kwargs)
        product = Product.objects.get(pk=case["product"].pk)
        product.width_mm = 666
        product.save()
        return result

    monkeypatch.setattr(service, "save_evaluation", save_and_change)
    with pytest.raises(InputsChanged):
        service.evaluate_bid(case["bid"], rules_first=True)
    assert before == (
        list(RequirementEvaluation.objects.values()),
        list(EvaluationHistory.objects.values()),
    )


@pytest.mark.parametrize("policy", ["prompt", "model_settings"])
def test_prompt_and_model_parameter_changes_are_tracked(case, policy):
    from apps.llm.models import LLMSettings, PromptTemplate

    config = LLMSettings.load()
    template = PromptTemplate.objects.filter(key="evaluation.judge", is_active=True).first()
    assert template
    evaluation = analyzed(case)
    if policy == "prompt":
        template.system_prompt += "\nSynthetic policy change"
        template.save()
        component = "prompts"
    else:
        config.temperature = 0.8
        config.save()
        component = "llm_settings"
    result = fresh(evaluation)
    assert result["status"] == "STALE" and component in [r["component"] for r in result["reasons"]]


def test_reference_day_change_requires_refresh(case, monkeypatch):
    from django.utils import timezone

    evaluation = analyzed(case)
    monkeypatch.setattr(timezone, "localdate", lambda *args, **kwargs: date(2031, 1, 1))
    result = fresh(evaluation)
    assert result["status"] == "STALE" and "reference" in [
        r["component"] for r in result["reasons"]
    ]
