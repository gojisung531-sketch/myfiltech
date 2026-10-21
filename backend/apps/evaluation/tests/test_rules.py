"""Rule scenarios R1–R20 (specs/12 §4): reference date 2026-10-05, initial-data company."""

from datetime import date

import pytest

from apps.bids.models import BidItem, BidNotice, BidRequirement
from apps.company.models import Product
from apps.evaluation import rules
from apps.evaluation.context import EvaluationContext

pytestmark = pytest.mark.django_db


@pytest.fixture
def bid(company_data):
    return BidNotice.objects.create(title="GT 흡기 필터 구매", buyer_org="가상발전")


def run(bid, category, normalized, *, product=None, text="", item_dims=None, mandatory=True):
    item = None
    if product:
        item = BidItem.objects.create(
            bid=bid,
            item_no=str(bid.items.count() + 1),
            name=product,
            matched_product=Product.objects.get(model_no=product),
            **(item_dims or {}),
        )
    requirement = BidRequirement.objects.create(
        bid=bid,
        item=item,
        category=category,
        title=text or category,
        requirement_text=text,
        normalized=normalized,
        is_mandatory=mandatory,
    )
    ctx = EvaluationContext.for_bid(bid)
    ctx.reference_date = date(2026, 10, 5)
    return rules.evaluate(requirement, ctx)


def expect(result, verdict, risk):
    assert result is not None
    assert (result.verdict, result.risk_level) == (verdict, risk), result.rationale


def labels(result):
    return " ".join(e["label"] for e in result.evidences)


def test_r1_dimension_exact(bid):
    r = run(bid, "DIMENSION", {"w": 592, "h": 592, "d": 292}, product="FT-VB500")
    expect(r, "MET", "LOW")
    assert "FT-VB500" in labels(r)


def test_r2_dimension_same_nominal_family(bid):
    r = run(bid, "DIMENSION", {"w": 610, "h": 610, "d": 305}, product="FT-VB500")
    expect(r, "NEEDS_SUPPLEMENT", "MEDIUM")
    assert "공칭" in r.rationale
    assert any("제작 가능" in a for a in r.action_items)


def test_r3_iso16890_epm1(bid):
    r = run(bid, "FILTER_GRADE", {"standard": "ISO16890", "class": "ePM1 80%"}, product="FT-VB500")
    expect(r, "MET", "LOW")
    assert "AFT-2025-0402" in labels(r)


def test_r4_en779_f9_obsolete(bid):
    r = run(bid, "FILTER_GRADE", {"standard": "EN779", "class": "F9"}, product="FT-VB500")
    expect(r, "MET", "MEDIUM")
    assert "AFT-2017-0730" in labels(r)
    assert "폐지" in r.rationale


def test_r5_ashrae_missing(bid):
    r = run(bid, "FILTER_GRADE", {"standard": "ASHRAE52_2", "class": "MERV 14"}, product="FT-VB500")
    expect(r, "NEEDS_SUPPLEMENT", "MEDIUM")
    assert "동등으로 판정하지 않습니다" in r.rationale  # reference map is narrative only


def test_r6_initial_dp_same_airflow(bid):
    r = run(
        bid,
        "PRESSURE_DROP",
        {"metric": "initial_dp", "operator": "<=", "value": 150, "at_airflow_m3h": 4250},
        product="FT-VB500",
    )
    expect(r, "MET", "LOW")
    assert "130 Pa" in r.company_value
    assert "AFT-2025-0613" in labels(r)


def test_r7_initial_dp_interpolated(bid):
    r = run(
        bid,
        "PRESSURE_DROP",
        {"metric": "initial_dp", "operator": "<", "value": 100, "at_airflow_m3h": 2990},
        product="FT-VB500",
    )
    expect(r, "MET", "MEDIUM")
    assert "보간" in r.rationale
    assert r.trace["interpolation"].endswith("= 87.9 Pa")  # 58 + 865/1275 × 44 = 87.85


def test_r8_final_dp(bid):
    r = run(
        bid,
        "PRESSURE_DROP",
        {"metric": "final_dp", "operator": ">", "value": 625},
        product="FT-VB500",
    )
    expect(r, "NEEDS_SUPPLEMENT", "MEDIUM")
    assert "600 Pa" in r.rationale


def test_r9_en1822_e11(bid):
    r = run(bid, "FILTER_GRADE", {"standard": "EN1822", "class": "E11"}, product="FT-EP700")
    expect(r, "MET", "LOW")
    assert "AFT-2025-0921" in labels(r)


def test_r10_frame_sus304_option(bid):
    r = run(bid, "MATERIAL", {"part": "frame", "required": ["SUS304"]}, product="FT-EP700")
    expect(r, "NEEDS_SUPPLEMENT", "MEDIUM")
    assert "주문제작" in r.rationale
    assert "SUS304 프레임 사양 아님" in r.rationale


def test_r11_ul900_listing(bid):
    r = run(
        bid,
        "FIRE_RATING",
        {"standard": "UL900", "class": ""},
        product="FT-VB500",
        text="UL 900 Listing 필수",
    )
    expect(r, "NEEDS_SUPPLEMENT", "MEDIUM")
    assert "AFT-2024-0822" in labels(r)


def test_r12_iso14001_expired(bid):
    expect(run(bid, "CERTIFICATION", {"cert_type": "ISO14001"}), "NEEDS_SUPPLEMENT", "HIGH")


def test_r13_iso9001(bid):
    r = run(bid, "CERTIFICATION", {"cert_type": "ISO9001"})
    expect(r, "MET", "LOW")
    assert "GQ-24-08812" in labels(r)


def test_r14_direct_production_code(bid):
    r = run(bid, "CERTIFICATION", {"cert_type": "DIRECT_PRODUCTION", "product_code": "4016150501"})
    expect(r, "NEEDS_CONFIRMATION", "HIGH")
    assert "DP-2025-0203-117" in labels(r)


def test_r15_track_record_amount_unknown(bid):
    r = run(
        bid,
        "TRACK_RECORD",
        {
            "period_years": 10,
            "min_amount_krw": 112140000,
            "grade": {"standard": "EN779", "class": "F9"},
        },
    )
    expect(r, "NEEDS_CONFIRMATION", "MEDIUM")
    assert "2023-10" in labels(r)


def test_r16_pulse_f9_record_missing(bid):
    r = run(
        bid,
        "TRACK_RECORD",
        {
            "period_years": 10,
            "product_types": ["CARTRIDGE_PULSE"],
            "grade": {"standard": "EN779", "class": "F9"},
        },
    )
    expect(r, "NEEDS_SUPPLEMENT", "HIGH")


def test_r17_conical_dimension(bid):
    r = run(bid, "DIMENSION", {"dia": 445, "dia2": 324, "len": 660}, product="FT-CP200")
    expect(r, "NEEDS_SUPPLEMENT", "HIGH")
    assert "Ø324/Ø215" in r.company_value


def test_r18_delivery_without_lead_time(bid):
    expect(run(bid, "DELIVERY", {"days_after_contract": 150}), "NEEDS_CONFIRMATION", "LOW")


def test_r19_humidity(bid):
    r = run(bid, "ENVIRONMENT", {"max_rh": 100}, product="FT-HP900")
    expect(r, "NEEDS_SUPPLEMENT", "MEDIUM")
    assert "90" in r.rationale


def test_r20_company_issued_bond(bid):
    r = run(
        bid, "SUBMISSION_DOC", {"doc": "하자이행증권", "timing": "계약 시", "issuer_type": "SURETY"}
    )
    expect(r, "MET", "LOW")
    assert r.action_items


# ---- other branches --------------------------------------------------------------------


def test_dimension_from_item_and_range(bid):
    r = run(
        bid,
        "DIMENSION",
        {},
        product="FT-VB500",
        item_dims={"width_mm": 592, "height_mm": 592, "depth_mm": 280, "depth_mm_max": 300},
    )
    expect(r, "MET", "LOW")


def test_dimension_without_product(bid):
    expect(run(bid, "DIMENSION", {"w": 592, "h": 592, "d": 292}), "NEEDS_SUPPLEMENT", "HIGH")


def test_bid_level_requirement_uses_single_matched_product(bid):
    BidItem.objects.create(
        bid=bid,
        item_no="1",
        name="V-bank",
        matched_product=Product.objects.get(model_no="FT-VB500"),
    )
    expect(run(bid, "DIMENSION", {"w": 592, "h": 592, "d": 292}), "MET", "LOW")


def test_filter_type(bid):
    expect(run(bid, "FILTER_TYPE", {"type": "V_BANK"}, product="FT-VB500"), "MET", "LOW")
    other = run(bid, "FILTER_TYPE", {"type": "V_BANK"}, product="FT-CP200")
    expect(other, "NEEDS_SUPPLEMENT", "MEDIUM")
    assert "FT-VB500" in other.rationale
    expect(
        run(bid, "FILTER_TYPE", {"type": "DEMISTER"}, product="FT-CP200"),
        "NEEDS_SUPPLEMENT",
        "HIGH",
    )


def test_grade_shortfall_and_equivalent_wording(bid):
    expect(
        run(bid, "FILTER_GRADE", {"standard": "EN1822", "class": "H13"}, product="FT-EP700"),
        "NEEDS_SUPPLEMENT",
        "HIGH",
    )
    r = run(
        bid,
        "FILTER_GRADE",
        {"standard": "ASHRAE52_2", "class": "MERV 15"},
        product="FT-VB500",
        text="MERV 15 또는 동등 이상",
    )
    expect(r, "NEEDS_CONFIRMATION", "MEDIUM")
    assert "EN 779 F9" in r.rationale


def test_efficiency(bid):
    r = run(
        bid,
        "EFFICIENCY",
        {"metric": "avg_eff_0_4um", "operator": ">=", "value": 95.4, "test_standard": "EN779"},
        product="FT-VB500",
    )
    expect(r, "MET", "MEDIUM")  # 96 %, obsolete EN 779 report
    low = run(
        bid,
        "EFFICIENCY",
        {
            "metric": "average_efficiency_0.4um",
            "operator": ">=",
            "value": 97,
            "test_standard": "EN779:2012",
        },
        product="FT-VB500",
    )
    expect(low, "NEEDS_SUPPLEMENT", "HIGH")
    other = run(
        bid,
        "EFFICIENCY",
        {"metric": "avg_eff_0_4um", "operator": ">=", "value": 95, "test_standard": "EN779"},
        product="FT-CP200",
    )
    expect(other, "NEEDS_SUPPLEMENT", "MEDIUM")
    assert (
        run(bid, "EFFICIENCY", {"metric": "dust_holding", "value": 450}, product="FT-VB500") is None
    )


def test_pressure_outside_curve_and_failure(bid):
    out = run(
        bid,
        "PRESSURE_DROP",
        {"metric": "initial_dp", "operator": "<=", "value": 200, "at_airflow_m3h": 9000},
        product="FT-VB500",
    )
    expect(out, "NEEDS_CONFIRMATION", "MEDIUM")
    fail = run(
        bid,
        "PRESSURE_DROP",
        {"metric": "initial_dp", "operator": "<=", "value": 120, "at_airflow_m3h": 4250},
        product="FT-VB500",
    )
    expect(fail, "NEEDS_SUPPLEMENT", "HIGH")


def test_airflow(bid):
    expect(run(bid, "AIRFLOW", {"value": 4000}, product="FT-VB500"), "MET", "LOW")
    expect(run(bid, "AIRFLOW", {"value": 5000}, product="FT-VB500"), "NEEDS_SUPPLEMENT", "MEDIUM")
    total = run(bid, "AIRFLOW", {"value": 1764000}, product="FT-CP200")
    expect(total, "NEEDS_CONFIRMATION", "LOW")


def test_material(bid):
    expect(
        run(bid, "MATERIAL", {"part": "gasket", "required": ["EPDM"]}, product="FT-CP200"),
        "MET",
        "LOW",
    )
    liner = run(
        bid,
        "MATERIAL",
        {"part": "liner", "required": ["Galvanized with Powder Coated", "Stainless Steel"]},
        product="FT-CP200",
    )
    expect(liner, "MET", "LOW")  # 아연도강판 ≈ Galvanized
    banned = run(bid, "MATERIAL", {"part": "frame", "forbidden": ["ABS"]}, product="FT-VB500")
    expect(banned, "NEEDS_SUPPLEMENT", "HIGH")
    assert (
        run(bid, "MATERIAL", {"part": "media", "required": ["PTFE 멤브레인"]}, product="FT-VB500")
        is None
    )


def test_test_standard(bid):
    expect(run(bid, "TEST_STANDARD", {"standard": "ISO29461"}), "MET", "LOW")
    expect(run(bid, "TEST_STANDARD", {"standard": "EN779"}), "MET", "MEDIUM")
    expect(run(bid, "TEST_STANDARD", {"standard": "ASHRAE52_2"}), "NEEDS_SUPPLEMENT", "MEDIUM")
    aged = run(bid, "TEST_STANDARD", {"standard": "EN779", "max_age_years": 3})
    expect(aged, "NEEDS_SUPPLEMENT", "MEDIUM")


def test_delivery_with_lead_time(bid):
    from apps.core.app_settings import set_setting

    set_setting("company.standard_lead_time_days", 120)
    r = run(bid, "DELIVERY", {"days_after_contract": 150})
    expect(r, "MET", "LOW")
    assert r.evidences
    expect(run(bid, "DELIVERY", {"days_after_contract": 90}), "NEEDS_SUPPLEMENT", "MEDIUM")


def test_submission_docs(bid):
    reports = run(bid, "SUBMISSION_DOC", {"doc": "EN 1822 시험성적서 원본", "timing": "납품 시"})
    expect(reports, "MET", "LOW")
    expect(
        run(bid, "SUBMISSION_DOC", {"doc": "ASHRAE 52.2 공인 성적서"}), "NEEDS_SUPPLEMENT", "MEDIUM"
    )
    expect(run(bid, "SUBMISSION_DOC", {"doc": "ISO 14001 인증서 사본"}), "NEEDS_SUPPLEMENT", "HIGH")
    expect(run(bid, "SUBMISSION_DOC", {"doc": "치수 및 외관검사 성적서"}), "MET", "LOW")
    expect(run(bid, "SUBMISSION_DOC", {"doc": "실적증명서"}), "MET", "LOW")
    assert run(bid, "SUBMISSION_DOC", {"doc": "기타 서류", "issuer_type": "AUTHORITY"}) is None


def test_placeholder_and_unruled(bid):
    r = run(bid, "SUBMISSION_DOC", {"placeholder": True})
    expect(r, "NEEDS_CONFIRMATION", "MEDIUM")
    assert r.trace["question"]
    assert run(bid, "WARRANTY", {"months": 24}) is None
