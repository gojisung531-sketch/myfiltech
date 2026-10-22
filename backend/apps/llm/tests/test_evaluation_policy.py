"""B5A synthetic regressions. Provider transport is replaced; no company source fixtures."""

import json
from datetime import date
from io import StringIO
from unittest.mock import Mock

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.bids.models import BidNotice, BidRequirement
from apps.company.models import Certificate, Company, DeliveryRecord, Product, TestReport
from apps.core.app_settings import get_setting, set_setting
from apps.core.evaluation_policy import EVIDENCE_GUIDANCE, VERDICT_DEFINITIONS
from apps.core.models import AppSetting, Job
from apps.evaluation import rules, service
from apps.evaluation.context import EvaluationContext
from apps.evaluation.evidence import product_evidence, record_evidence, report_evidence
from apps.llm import services
from apps.llm.management.commands.align_evaluation_policy import LEGACY_DEFINITIONS
from apps.llm.models import (
    LLMCallLog,
    LLMModelOption,
    LLMProviderConfig,
    LLMSettings,
    PromptTemplate,
)
from apps.llm.prompt_defaults import COMMON_SYSTEM, COMMON_SYSTEM_BASE

pytestmark = pytest.mark.django_db


def legacy_policy():
    set_setting("evaluation.verdict_definitions", LEGACY_DEFINITIONS)
    PromptTemplate.objects.filter(is_active=True).update(system_prompt=COMMON_SYSTEM_BASE)


def align(tmp_path, settings):
    settings.BACKEND_DIR = tmp_path
    backup = tmp_path / ".venv" / "before.json"
    out = StringIO()
    call_command("align_evaluation_policy", apply=True, backup=str(backup), stdout=out)
    return backup, json.loads(out.getvalue())


def test_alignment_preserves_old_versions_manual_metadata_and_unrelated_settings(
    tmp_path, settings
):
    legacy_policy()
    old = PromptTemplate.active("evaluation.judge")
    old.notes = "수동 검토 메모 보존"
    old.save()
    before = list(PromptTemplate.objects.order_by("pk").values())
    unrelated = list(AppSetting.objects.exclude(key="evaluation.verdict_definitions").values())
    protected = [list(m.objects.values()) for m in (LLMSettings, LLMModelOption, LLMProviderConfig)]
    backup, result = align(tmp_path, settings)
    saved = json.loads(backup.read_text(encoding="utf8"))
    assert saved["setting"]["value"] == LEGACY_DEFINITIONS
    assert len(saved["prompts"]) == len(result["prompts"]) == 9
    assert result["applied"]
    assert get_setting("evaluation.verdict_definitions") == VERDICT_DEFINITIONS
    for row in before:
        prior = PromptTemplate.objects.values().get(pk=row["id"])
        assert prior == {**row, "is_active": False}
        active = PromptTemplate.active(row["key"])
        assert active.version == row["version"] + 1
        assert active.system_prompt == COMMON_SYSTEM
        for field in (
            "user_prompt_template",
            "output_schema",
            "name",
            "description",
            "updated_by_id",
        ):
            assert getattr(active, field) == row[field]
    assert (
        list(AppSetting.objects.exclude(key="evaluation.verdict_definitions").values()) == unrelated
    )
    assert protected == [
        list(m.objects.values()) for m in (LLMSettings, LLMModelOption, LLMProviderConfig)
    ]
    assert not LLMCallLog.objects.exists() and not Job.objects.exists()
    count = PromptTemplate.objects.count()
    call_command("align_evaluation_policy", apply=True, backup=str(backup), stdout=StringIO())
    assert PromptTemplate.objects.count() == count  # no new backup/version on a no-op


@pytest.mark.parametrize(
    "fault", ["custom_setting", "custom_system", "custom_task", "missing_active", "existing_backup"]
)
def test_preflight_or_backup_failure_never_partially_applies(fault, tmp_path, settings):
    legacy_policy()
    settings.BACKEND_DIR = tmp_path
    backup = tmp_path / ".venv" / "before.json"
    if fault == "custom_setting":
        set_setting("evaluation.verdict_definitions", "수동 정책")
    if fault == "custom_system":
        PromptTemplate.objects.filter(key="evaluation.judge").update(system_prompt="수동 지시")
    if fault == "custom_task":
        PromptTemplate.objects.filter(key="evaluation.judge").update(
            user_prompt_template="수동 지시"
        )
    if fault == "missing_active":
        PromptTemplate.objects.filter(key="evaluation.judge").update(is_active=False)
    if fault == "existing_backup":
        backup.parent.mkdir()
        backup.write_text("preserve", encoding="utf8")
    before = list(PromptTemplate.objects.values())
    prior_value = get_setting("evaluation.verdict_definitions")
    with pytest.raises(CommandError):
        call_command("align_evaluation_policy", apply=True, backup=str(backup), stdout=StringIO())
    assert list(PromptTemplate.objects.values()) == before
    assert get_setting("evaluation.verdict_definitions") == prior_value


def test_backup_must_be_local_ignored_and_dry_run_is_read_only(tmp_path, settings):
    legacy_policy()
    settings.BACKEND_DIR = tmp_path
    before = list(PromptTemplate.objects.values())
    call_command("align_evaluation_policy", stdout=StringIO())
    with pytest.raises(CommandError):
        call_command("align_evaluation_policy", apply=True, backup=str(tmp_path / "public.json"))
    assert list(PromptTemplate.objects.values()) == before
    assert not (tmp_path / "public.json").exists()


def test_failed_version_creation_rolls_back_setting_and_activation(tmp_path, settings, monkeypatch):
    legacy_policy()
    before = list(PromptTemplate.objects.values())
    monkeypatch.setattr(PromptTemplate.objects, "create", Mock(side_effect=RuntimeError("abort")))
    with pytest.raises(RuntimeError, match="abort"):
        align(tmp_path, settings)
    assert list(PromptTemplate.objects.values()) == before
    assert get_setting("evaluation.verdict_definitions") == LEGACY_DEFINITIONS
    assert (tmp_path / ".venv" / "before.json").exists()


def test_new_version_uses_latest_number_and_preserves_manual_history(tmp_path, settings):
    legacy_policy()
    old = PromptTemplate.active("evaluation.judge")
    manual = PromptTemplate.objects.create(
        key=old.key,
        version=7,
        notes="수동 이력",
        system_prompt="수동 원문 보존",
        user_prompt_template="수동 텍스트",
        output_schema=old.output_schema,
    )
    before = dict(PromptTemplate.objects.values().get(pk=manual.pk))
    align(tmp_path, settings)
    assert PromptTemplate.active(old.key).version == 8
    assert PromptTemplate.objects.values().get(pk=manual.pk) == before


@pytest.mark.parametrize(
    "is_sme,until,expected",
    [
        (None, None, "NEEDS_CONFIRMATION"),
        (True, date(2027, 1, 1), "MET"),
        (False, None, "NEEDS_SUPPLEMENT"),
    ],
)
def test_stored_policy_reaches_real_request_and_rule_meanings_are_preserved(
    is_sme, until, expected, tmp_path, settings, fake_llm, monkeypatch
):
    legacy_policy()
    align(tmp_path, settings)
    bid = BidNotice.objects.create(title="합성 공고")
    req = BidRequirement.objects.create(
        bid=bid, category="CERTIFICATION", title="합성 자격", normalized={"cert_type": "SME"}
    )
    ctx = EvaluationContext(
        reference_date=date(2026, 1, 1),
        is_simulation=False,
        company=Company(is_sme=is_sme, sme_cert_valid_until=until),
    )
    result = rules.evaluate(req, ctx)
    assert result.verdict == expected
    fake_llm.responses.append({"results": []})
    decrypt_guard = Mock(side_effect=AssertionError("Real key decryption forbidden"))
    monkeypatch.setattr(LLMProviderConfig, "get_api_key", decrypt_guard)
    monkeypatch.setattr(services, "_provider_for", lambda *args: fake_llm(api_key="synthetic"))
    service._judge(bid, [(req, result)], ctx, None)
    request = fake_llm.requests[0]
    assert VERDICT_DEFINITIONS in request.system and VERDICT_DEFINITIONS in request.user
    assert EVIDENCE_GUIDANCE in request.system
    assert LEGACY_DEFINITIONS not in request.system + request.user
    assert expected in request.user
    decrypt_guard.assert_not_called()
    assert LLMCallLog.objects.get().prompt_version == 2
    assert not Job.objects.exists()


def test_structured_records_do_not_invent_original_pages_or_quotes():
    evidence = [
        product_evidence(Product(pk=1, model_no="SYNTHETIC", name="합성", dimension_text="610mm")),
        report_evidence(TestReport(pk=2, report_no="SYNTHETIC"), "계산 요약"),
        record_evidence(DeliveryRecord(pk=3), "계산 요약"),
        rules._cert_evidence(Certificate(pk=4, cert_type="ISO9001")),
    ]
    assert all(e["page"] == 0 and e["quote"] == "" for e in evidence)


def test_request_source_keeps_verified_page_and_marks_unknown_page():
    from apps.bids.models import BidAttachment
    from apps.documents.models import Document

    bid = BidNotice.objects.create(title="합성 출처")
    document = Document.objects.create(owner_type="BID", original_filename="synthetic.pdf")
    attachment = BidAttachment.objects.create(bid=bid, document=document)
    req = BidRequirement.objects.create(
        bid=bid,
        category="OTHER",
        title="합성 요구",
        source_attachment=attachment,
        source_page=7,
        source_quote="합성 원문",
    )
    ctx = EvaluationContext(date(2026, 1, 1), False, Company())
    source = service._requirement_payload(req, None, ctx)["source"]
    assert source["id"] == attachment.pk and source["page"] == 7
    assert source["quote"] == "합성 원문"
    req.source_page = None
    assert service._requirement_payload(req, None, ctx)["source"]["page"] == 0
    req.source_quote = ""
    assert service._requirement_payload(req, None, ctx)["source"] is None


def test_gets_do_not_run_paid_work_or_overwrite_manual_results(admin_client, monkeypatch):
    from apps.evaluation.models import RequirementEvaluation

    bid = BidNotice.objects.create(title="합성 조회")
    req = BidRequirement.objects.create(bid=bid, category="OTHER", title="합성")
    evaluation = RequirementEvaluation.objects.create(
        requirement=req, verdict="NEEDS_SUPPLEMENT", is_modified=True, auto_answer="수동 답변"
    )
    provider = Mock(side_effect=AssertionError("GET must never construct a provider"))
    monkeypatch.setattr(services, "_provider_for", provider)
    before = list(RequirementEvaluation.objects.values())
    for _ in range(2):
        for url in (
            "/api/system/status",
            "/api/settings/app",
            "/api/settings/prompts",
            f"/api/bids/{bid.pk}/evaluations",
            "/api/report-register-rows",
        ):
            assert admin_client.get(url).status_code == 200
    assert list(RequirementEvaluation.objects.values()) == before
    evaluation.refresh_from_db()
    assert evaluation.is_modified and evaluation.auto_answer == "수동 답변"
    assert not Job.objects.exists() and not LLMCallLog.objects.exists()
    provider.assert_not_called()


def test_fresh_context_reads_latest_formal_data_and_never_promotes_pending_rows():
    from apps.company.models import ReportRegisterRow, ReportRegisterVersion

    bid = BidNotice.objects.create(title="합성 최신 입력")
    version = ReportRegisterVersion.objects.create(sha256="c" * 64)
    ReportRegisterRow.objects.create(file_version=version, sheet_name="합성", row_number=1)
    company = Company.load()
    company.is_sme = None
    company.save()
    before = EvaluationContext.for_bid(bid)
    company.is_sme = True
    company.save()
    after = EvaluationContext.for_bid(bid)
    assert before.company.is_sme is None and after.company.is_sme is True
    assert before.test_reports == after.test_reports == []
    assert not TestReport.objects.exists()
    assert ReportRegisterRow.objects.get().review_status == "PENDING"


def test_synthetic_rerun_keeps_manual_evaluation_and_history(monkeypatch):
    from apps.evaluation.models import EvaluationHistory, RequirementEvaluation

    bid = BidNotice.objects.create(title="합성 수동 보존")
    req = BidRequirement.objects.create(bid=bid, category="OTHER", title="합성")
    evaluation = RequirementEvaluation.objects.create(
        requirement=req, verdict="NEEDS_SUPPLEMENT", is_modified=True, auto_answer="담당자 답변"
    )
    EvaluationHistory.objects.create(evaluation=evaluation, snapshot=evaluation.snapshot())
    prior = list(RequirementEvaluation.objects.values()), list(EvaluationHistory.objects.values())
    judge = Mock(side_effect=AssertionError("Skipped manual row must not reach the judge"))
    monkeypatch.setattr(service, "_judge", judge)
    monkeypatch.setattr(service, "is_llm_configured", lambda: True)
    result = service.evaluate_bid(bid, keep_modified=True)
    assert result["skipped_modified"] == 1 and result["evaluated"] == 0
    assert prior == (
        list(RequirementEvaluation.objects.values()),
        list(EvaluationHistory.objects.values()),
    )
    judge.assert_not_called()
