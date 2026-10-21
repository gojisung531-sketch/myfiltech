"""Qualification rules against initial-data company data (specs/12 §4, R12–R16)."""

from datetime import date, datetime, timedelta

import pytest
from django.utils import timezone

from apps.bids.models import BidNotice, BidRequirement
from apps.company.models import Company
from apps.core.app_settings import set_setting
from apps.evaluation import rules
from apps.evaluation.context import EvaluationContext, reference_date

pytestmark = pytest.mark.django_db

REFERENCE = date(2026, 10, 5)


@pytest.fixture
def ctx(company_data):
    bid = BidNotice(title="t")
    context = EvaluationContext.for_bid(bid)
    context.reference_date = REFERENCE
    return context


def req(category, normalized, mandatory=True):
    return BidRequirement(
        category=category, title="t", normalized=normalized, is_mandatory=mandatory
    )


def test_r12_iso14001_expired(ctx):
    result = rules.evaluate(req("CERTIFICATION", {"cert_type": "ISO14001"}), ctx)
    assert (result.verdict, result.risk_level) == ("NEEDS_SUPPLEMENT", "HIGH")
    assert "2026-06-11" in result.rationale
    assert result.evidences[0]["type"] == "certificate"


def test_r13_iso9001_valid(ctx):
    result = rules.evaluate(req("CERTIFICATION", {"cert_type": "ISO9001"}), ctx)
    assert (result.verdict, result.risk_level) == ("MET", "LOW")


def test_r14_direct_production_code_mismatch(ctx):
    result = rules.evaluate(
        req("CERTIFICATION", {"cert_type": "DIRECT_PRODUCTION", "product_code": "4016150501"}), ctx
    )
    assert (result.verdict, result.risk_level) == ("NEEDS_CONFIRMATION", "HIGH")
    assert "4013xxxx" in result.rationale


def test_direct_production_code_and_note_match(ctx):
    cert = next(c for c in ctx.certificates if c.cert_type == "DIRECT_PRODUCTION")
    cert.product_codes = ["40161505"]
    result = rules.evaluate(
        req("CERTIFICATION", {"cert_type": "DIRECT_PRODUCTION", "product_code": "4016150501"}), ctx
    )
    assert result.verdict == "MET"
    noted = rules.evaluate(
        req(
            "CERTIFICATION",
            {
                "cert_type": "DIRECT_PRODUCTION",
                "product_code": "4016150501",
                "required_note": "미듐, 헤파필터에 한함",
            },
        ),
        ctx,
    )
    assert (noted.verdict, noted.risk_level) == ("NEEDS_CONFIRMATION", "HIGH")


def test_missing_certificate_type(ctx):
    result = rules.evaluate(req("CERTIFICATION", {"cert_type": "ISO45001"}, mandatory=False), ctx)
    assert (result.verdict, result.risk_level) == ("NEEDS_SUPPLEMENT", "MEDIUM")


def test_sme_and_g2b_depend_on_company_info(ctx):
    sme = rules.evaluate(req("CERTIFICATION", {"cert_type": "SME"}), ctx)
    assert (sme.verdict, sme.risk_level) == ("NEEDS_CONFIRMATION", "HIGH")
    g2b = rules.evaluate(
        req("CERTIFICATION", {"cert_type": "G2B_ITEM", "product_code": "4016150501"}), ctx
    )
    assert g2b.verdict == "NEEDS_CONFIRMATION"

    ctx.company.is_sme = True
    ctx.company.g2b_registered_items = [{"code": "4016150501", "name": "공기여과기"}]
    assert rules.evaluate(req("CERTIFICATION", {"cert_type": "SME"}), ctx).verdict == "MET"
    assert (
        rules.evaluate(
            req("CERTIFICATION", {"cert_type": "G2B_ITEM", "product_code": "4016150501"}), ctx
        ).verdict
        == "MET"
    )
    ctx.company.sme_cert_valid_until = date(2026, 1, 1)
    assert (
        rules.evaluate(req("CERTIFICATION", {"cert_type": "SME"}), ctx).verdict
        == "NEEDS_SUPPLEMENT"
    )


def test_unknown_certification_defers_to_llm(ctx):
    assert rules.evaluate(req("CERTIFICATION", {"cert_type": "OTHER"}), ctx) is None


def test_r15_f9_gt_record_without_amount(ctx):
    result = rules.evaluate(
        req(
            "TRACK_RECORD",
            {
                "period_years": 10,
                "min_amount_krw": 112140000,
                "grade": {"standard": "EN779", "class": "F9"},
                "power_plant_only": True,
            },
        ),
        ctx,
    )
    assert (result.verdict, result.risk_level) == ("NEEDS_CONFIRMATION", "MEDIUM")
    assert {e["label"][:7] for e in result.evidences} == {"2023-10", "2024-11"}


def test_r16_pulse_cartridge_f9_record_missing(ctx):
    result = rules.evaluate(
        req(
            "TRACK_RECORD",
            {
                "period_years": 10,
                "product_types": ["CARTRIDGE_PULSE"],
                "grade": {"standard": "EN779", "class": "F9"},
            },
        ),
        ctx,
    )
    assert (result.verdict, result.risk_level) == ("NEEDS_SUPPLEMENT", "HIGH")


def test_track_record_met_and_period_cutoff(ctx):
    met = rules.evaluate(req("TRACK_RECORD", {"period_years": 3, "product_types": ["V_BANK"]}), ctx)
    assert met.verdict == "MET"
    ctx.reference_date = date(2040, 1, 1)
    old = rules.evaluate(req("TRACK_RECORD", {"period_years": 3, "product_types": ["V_BANK"]}), ctx)
    assert old.verdict == "NEEDS_SUPPLEMENT"


def test_unstructured_track_record_defers(ctx):
    assert rules.evaluate(req("TRACK_RECORD", {"spec_condition": "유사 실적"}), ctx) is None


def test_reference_date_modes():
    today = timezone.localdate()
    past = BidNotice(title="p", bid_close_at=timezone.make_aware(datetime(2023, 4, 5, 12, 0)))
    future = BidNotice(title="f", bid_close_at=timezone.now() + timedelta(days=10))
    assert reference_date(past) == (today, True)  # AUTO: past notice → today, simulation
    assert reference_date(future) == (timezone.localdate(future.bid_close_at), False)
    assert reference_date(past, "BID_CLOSE") == (date(2023, 4, 5), False)
    assert reference_date(future, "TODAY")[0] == today
    set_setting("evaluation.reference_date_mode", "BID_CLOSE")
    assert reference_date(past) == (date(2023, 4, 5), False)
    assert Company.load()  # context helpers load the singleton
