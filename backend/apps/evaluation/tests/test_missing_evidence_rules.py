"""Synthetic, database-free B4B boundaries; no company document fixtures or services."""

from datetime import date
from types import SimpleNamespace

import pytest

from apps.company.models import Certificate, Company, Product, TestReport
from apps.core.defaults import APP_SETTING_DEFAULTS
from apps.evaluation import rules
from apps.evaluation.context import EvaluationContext

REFERENCE = date(2026, 1, 15)


@pytest.fixture(autouse=True)
def no_services(monkeypatch):
    monkeypatch.setattr(rules, "get_setting", lambda key: APP_SETTING_DEFAULTS[key].value)

    def forbidden(*args, **kwargs):
        pytest.fail("Rule units must not load company data or construct a DB context")

    monkeypatch.setattr(Company, "load", forbidden)
    monkeypatch.setattr(EvaluationContext, "for_bid", forbidden)


@pytest.fixture
def ctx():
    return EvaluationContext(
        reference_date=REFERENCE, is_simulation=False, company=Company(is_sme=None)
    )


def requirement(category, norm=None, *, item=False, product=None, text="", mandatory=True):
    return SimpleNamespace(
        category=category,
        normalized=norm or {},
        item_id=1 if item else None,
        item=SimpleNamespace(matched_product=product) if item else None,
        bid=None,
        title=text or category,
        requirement_text=text,
        is_mandatory=mandatory,
    )


def product(pk=1):
    return Product(pk=pk, model_no=f"SYNTHETIC-{pk}", name="합성 제품")


def report(pk=1, **overrides):
    values = {
        "pk": pk,
        "product_id": 1,
        "report_no": f"SYNTHETIC-REPORT-{pk}",
        "standard": "EN 1822",
        "standard_family": "EN1822",
        "issue_date": date(2025, 1, 1),
        "lab_name": "합성 시험기관",
        "lab_accreditation": "KOLAS",
    }
    return TestReport(**(values | overrides))


def standard_req(**norm):
    return requirement("TEST_STANDARD", {"standard": "EN1822", **norm})


@pytest.mark.parametrize("mandatory,risk", [(True, "HIGH"), (False, "MEDIUM")])
def test_unregistered_certificate_is_unknown(ctx, mandatory, risk):
    result = rules.evaluate(
        requirement("CERTIFICATION", {"cert_type": "ISO9001"}, mandatory=mandatory), ctx
    )
    assert (result.verdict, result.risk_level) == ("NEEDS_CONFIRMATION", risk)
    assert "보유하고 있지" not in result.rationale
    assert any("등록" in action or "원본" in action for action in result.action_items)


@pytest.mark.parametrize(
    "sme,until,expected",
    [
        (None, None, "NEEDS_CONFIRMATION"),
        (True, None, "NEEDS_CONFIRMATION"),
        (False, None, "NEEDS_SUPPLEMENT"),
        (True, date(2025, 12, 31), "NEEDS_SUPPLEMENT"),
        (True, REFERENCE, "MET"),
    ],
)
def test_sme_unknown_expired_and_explicit_negative_are_distinct(ctx, sme, until, expected):
    ctx.company.is_sme = sme
    ctx.company.sme_cert_valid_until = until
    result = rules.evaluate(requirement("CERTIFICATION", {"cert_type": "SME"}), ctx)
    assert result.verdict == expected
    if expected == "NEEDS_CONFIRMATION":
        assert result.risk_level == "HIGH"
        assert "유효합니다" not in result.rationale


@pytest.mark.parametrize(
    "until,expected",
    [
        (None, "NEEDS_CONFIRMATION"),
        (date(2025, 1, 1), "NEEDS_SUPPLEMENT"),
        (date(2027, 1, 1), "MET"),
    ],
)
def test_registered_certificate_validity_boundaries(ctx, until, expected):
    ctx.certificates = [Certificate(pk=1, cert_type="ISO9001", valid_until=until)]
    result = rules.evaluate(requirement("CERTIFICATION", {"cert_type": "ISO9001"}), ctx)
    assert result.verdict == expected


def test_unregistered_standard_is_not_a_test_order(ctx):
    result = rules.evaluate(standard_req(), ctx)
    assert result.verdict == "NEEDS_CONFIRMATION"
    assert "보유하고 있지" not in result.rationale
    assert not any("시험 의뢰" in action for action in result.action_items)
    assert any("등록" in action or "원본" in action for action in result.action_items)


@pytest.mark.parametrize("other_product", [None, 2])
def test_unmatched_item_cannot_borrow_company_report(ctx, other_product):
    ctx.test_reports = [report(product_id=other_product)]
    req = requirement("TEST_STANDARD", {"standard": "EN1822"}, item=True)
    result = rules.evaluate(req, ctx)
    assert result.verdict == "NEEDS_CONFIRMATION"
    assert result.evidences == []


def test_matched_item_excludes_other_product_but_company_requirement_can_use_it(ctx):
    ctx.test_reports = [report(product_id=2)]
    req = requirement("TEST_STANDARD", {"standard": "EN1822"}, item=True, product=product())
    assert rules.evaluate(req, ctx).verdict == "NEEDS_CONFIRMATION"
    assert rules.evaluate(standard_req(), ctx).verdict == "MET"


@pytest.mark.parametrize("max_age", [0, 5])
def test_missing_issue_date_never_proves_validity(ctx, max_age):
    ctx.test_reports = [report(issue_date=None)]
    result = rules.evaluate(standard_req(max_age_years=max_age), ctx)
    assert result.verdict == "NEEDS_CONFIRMATION"
    assert any("발행일" in action for action in result.action_items)


def test_known_old_report_is_still_insufficient(ctx):
    ctx.test_reports = [report(issue_date=date(2010, 1, 1))]
    result = rules.evaluate(standard_req(max_age_years=5), ctx)
    assert result.verdict == "NEEDS_SUPPLEMENT"
    assert "유효 기간" in result.rationale


def test_age_limit_uses_existing_setting(ctx, monkeypatch):
    monkeypatch.setattr(rules, "get_setting", lambda key: 5)
    ctx.test_reports = [report(issue_date=date(2010, 1, 1))]
    assert rules.evaluate(standard_req(), ctx).verdict == "NEEDS_SUPPLEMENT"


def test_different_standard_is_not_company_nonownership(ctx):
    ctx.test_reports = [report(standard_family="EN779", standard="EN779")]
    result = rules.evaluate(standard_req(), ctx)
    assert result.verdict == "NEEDS_CONFIRMATION"
    assert not result.evidences


@pytest.mark.parametrize("dated,expected", [(False, "NEEDS_CONFIRMATION"), (True, "MET")])
def test_obsolete_standard_preserves_warning_but_not_unknown_date(ctx, dated, expected):
    ctx.test_reports = [report(is_obsolete_standard=True, issue_date=REFERENCE if dated else None)]
    result = rules.evaluate(standard_req(), ctx)
    assert result.verdict == expected
    assert result.risk_level == "MEDIUM"


def test_unknown_issue_date_must_not_be_discarded_as_old(ctx):
    ctx.test_reports = [report(issue_date=date(2010, 1, 1)), report(2, issue_date=None)]
    assert rules.evaluate(standard_req(max_age_years=5), ctx).verdict == "NEEDS_CONFIRMATION"


def test_known_usable_report_is_not_hidden_by_unknown_report(ctx):
    ctx.test_reports = [report(issue_date=None), report(2)]
    result = rules.evaluate(standard_req(max_age_years=5), ctx)
    assert result.verdict == "MET"
    assert [e["id"] for e in result.evidences] == [2]


@pytest.mark.parametrize(
    "accreditation,expected",
    [
        ("", "NEEDS_CONFIRMATION"),
        ("미확인", "NEEDS_CONFIRMATION"),
        ("KOLAS 미확인", "NEEDS_CONFIRMATION"),
        ("국가공인", "NEEDS_CONFIRMATION"),
        ("not accredited", "NEEDS_SUPPLEMENT"),
        ("KOLAS 미인정", "NEEDS_SUPPLEMENT"),
        ("KOLAS", "MET"),
    ],
)
def test_lab_information_unknown_negative_and_supported(ctx, accreditation, expected):
    ctx.test_reports = [report(lab_accreditation=accreditation)]
    result = rules.evaluate(standard_req(lab_requirement="KOLAS"), ctx)
    assert result.verdict == expected


def test_unspecified_lab_requirement_does_not_invent_accreditation_condition(ctx):
    ctx.test_reports = [report(lab_accreditation="")]
    assert rules.evaluate(standard_req(), ctx).verdict == "MET"


def test_unrecognized_explicit_lab_condition_needs_confirmation(ctx):
    ctx.test_reports = [report()]
    assert (
        rules.evaluate(standard_req(lab_requirement="지정 시험소"), ctx).verdict
        == "NEEDS_CONFIRMATION"
    )


def test_select_eligible_report_not_latest_unverified_lab(ctx):
    ctx.test_reports = [
        report(lab_accreditation="KOLAS"),
        report(2, issue_date=REFERENCE, lab_accreditation=""),
    ]
    result = rules.evaluate(standard_req(lab_requirement="KOLAS"), ctx)
    assert result.verdict == "MET"
    assert [e["id"] for e in result.evidences] == [1]


def test_unknown_date_candidate_can_satisfy_lab_but_still_needs_date(ctx):
    ctx.test_reports = [report(lab_accreditation="비공인"), report(2, issue_date=None)]
    assert (
        rules.evaluate(standard_req(lab_requirement="국가공인"), ctx).verdict
        == "NEEDS_CONFIRMATION"
    )


def test_all_reports_have_known_failures(ctx):
    ctx.test_reports = [report(issue_date=date(2010, 1, 1)), report(2, lab_accreditation="비공인")]
    assert (
        rules.evaluate(standard_req(max_age_years=5, lab_requirement="국가공인"), ctx).verdict
        == "NEEDS_SUPPLEMENT"
    )


@pytest.mark.parametrize("doc", ["시험성적서", "실적증명서"])
def test_missing_submission_is_unknown(ctx, doc):
    result = rules.evaluate(requirement("SUBMISSION_DOC", {"doc": doc}), ctx)
    assert result.verdict == "NEEDS_CONFIRMATION"
    assert "보유하고 있지" not in result.rationale
    assert any("등록" in action or "원본" in action for action in result.action_items)


@pytest.mark.parametrize("matched", [False, True])
def test_item_submission_cannot_borrow_other_products_report(ctx, matched):
    ctx.test_reports = [report(product_id=2)]
    req = requirement(
        "SUBMISSION_DOC",
        {"doc": "EN1822 시험성적서"},
        item=True,
        product=product() if matched else None,
    )
    result = rules.evaluate(req, ctx)
    assert result.verdict == "NEEDS_CONFIRMATION"
    assert not any(e.get("type") == "test_report" for e in result.evidences)


def test_report_row_does_not_prove_original_submission(ctx):
    ctx.test_reports = [report()]
    req = requirement(
        "SUBMISSION_DOC",
        {"doc": "EN1822 시험성적서 원본", "timing": "납품 시"},
        item=True,
        product=product(),
    )
    result = rules.evaluate(req, ctx)
    assert result.verdict == "NEEDS_CONFIRMATION"
    assert result.evidences[0]["id"] == 1
    assert any("원본" in action for action in result.action_items)


def test_delivery_record_does_not_prove_period_amount_or_submission(ctx):
    ctx.delivery_records = [
        SimpleNamespace(
            pk=1,
            delivered_ym="2025-01",
            client="합성",
            project_name="합성",
            model_nos=[],
            products=SimpleNamespace(all=lambda: [product()]),
        )
    ]
    result = rules.evaluate(requirement("SUBMISSION_DOC", {"doc": "실적증명서"}), ctx)
    assert result.verdict == "NEEDS_CONFIRMATION"
    assert result.evidences[0]["type"] == "delivery_record"


def test_item_delivery_submission_uses_only_its_product_candidates(ctx):
    def record(pk, matched):
        return SimpleNamespace(
            pk=pk,
            delivered_ym="2025-01",
            client="합성",
            project_name="합성",
            model_nos=[],
            products=SimpleNamespace(all=lambda: [product(matched)]),
        )

    ctx.delivery_records = [record(1, 1), record(2, 2)]
    req = requirement("SUBMISSION_DOC", {"doc": "실적증명서"}, item=True, product=product())
    result = rules.evaluate(req, ctx)
    assert result.verdict == "NEEDS_CONFIRMATION"
    assert [e["id"] for e in result.evidences] == [1]
    ctx.delivery_records = [record(2, 2)]
    assert rules.evaluate(req, ctx).evidences == []


@pytest.mark.parametrize("text", ["UL 900 Listing", "방염 시험"])
def test_missing_fire_report_needs_registration_first(ctx, text):
    req = requirement("FIRE_RATING", item=True, product=product(), text=text)
    result = rules.evaluate(req, ctx)
    assert result.verdict == "NEEDS_CONFIRMATION"
    assert not any("시험 의뢰" in action for action in result.action_items)


def test_unmatched_fire_product_needs_confirmation(ctx):
    assert (
        rules.evaluate(requirement("FIRE_RATING", text="UL900", item=True), ctx).verdict
        == "NEEDS_CONFIRMATION"
    )


@pytest.mark.parametrize(
    "official,text,expected",
    [
        (True, "UL900 Listing", "MET"),
        (False, "UL900 Listing", "NEEDS_SUPPLEMENT"),
        (False, "UL900 시험", "MET"),
    ],
)
def test_existing_fire_positive_and_explicit_nonofficial_branches_remain(
    ctx, official, text, expected
):
    ctx.test_reports = [
        report(standard_family="UL900", standard="UL900", is_official_certification=official)
    ]
    req = requirement("FIRE_RATING", item=True, product=product(), text=text)
    assert rules.evaluate(req, ctx).verdict == expected


def test_generated_submission_and_supported_certificate_still_met(ctx):
    assert (
        rules.evaluate(requirement("SUBMISSION_DOC", {"doc": "치수 외관검사 성적서"}), ctx).verdict
        == "MET"
    )
    ctx.certificates = [Certificate(pk=1, cert_type="ISO9001", valid_until=date(2027, 1, 1))]
    assert (
        rules.evaluate(requirement("SUBMISSION_DOC", {"doc": "ISO9001 인증서"}), ctx).verdict
        == "MET"
    )


def test_rule_inputs_remain_unsaved_and_unchanged(ctx):
    r = report()
    ctx.test_reports = [r]
    before = (r.__dict__.copy(), ctx.company.__dict__.copy())
    assert rules.evaluate(standard_req(), ctx).verdict == "MET"
    assert (r.__dict__, ctx.company.__dict__) == before
    assert r._state.adding and ctx.company._state.adding
