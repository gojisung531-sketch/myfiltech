import pytest

from apps.bids.models import BidItem, BidNotice, BidRequirement
from apps.company.models import Product
from apps.evaluation.context import EvaluationContext
from apps.evaluation.matching import compute_fit, match_items, score_item_product

pytestmark = pytest.mark.django_db

NOMINAL = {"24": [592, 594, 595, 610], "12": [287, 292, 295, 305]}


def score(item, model_no, requirements=(), context=""):
    product = Product.objects.get(model_no=model_no)
    return score_item_product(
        item, product, list(requirements), tolerance=3, nominal=NOMINAL, context_text=context
    )


def test_exact_v_bank_match(company_data):
    item = BidItem(
        name="GT 흡기 최종단 V-bank 필터",
        filter_type="V_BANK",
        width_mm=592,
        height_mm=592,
        depth_mm=292,
    )
    grade = BidRequirement(
        category="FILTER_GRADE", normalized={"standard": "ISO16890", "class": "ePM1 80%"}
    )
    match = score(item, "FT-VB500", [grade])
    assert match.parts == {"type": 1.0, "dimension": 1.0, "grade": 1.0, "application": 1.0}
    assert match.score == 1.0
    assert "등급 충족" in match.reason


def test_nominal_family_and_grade_shortfall(company_data):
    item = BidItem(
        name="Final Filter", filter_type="V_BANK", width_mm=610, height_mm=610, depth_mm=305
    )
    grade = BidRequirement(
        category="FILTER_GRADE", normalized={"standard": "EN1822", "class": "H13"}
    )
    match = score(item, "FT-EP700", [grade])
    assert match.parts["dimension"] == 0.5  # same 24"/12" nominal family, different actual size
    assert match.parts["grade"] == 0.0  # E12 < H13
    assert "공칭 동일군" in match.reason


def test_cross_system_grade_and_range_depth(company_data):
    item = BidItem(
        name="HEPA",
        filter_type="V_BANK",
        width_mm=610,
        height_mm=610,
        depth_mm=400,
        depth_mm_max=600,
    )
    grade = BidRequirement(category="FILTER_GRADE", normalized={"standard": "EN779", "class": "F9"})
    match = score(item, "FT-VB500", [grade])
    assert match.parts["grade"] == 1.0  # VB500 carries an EN779 F9 class
    assert match.parts["dimension"] == pytest.approx(
        1 / 3
    )  # 592~610 nominal (0.5 each); depth 292 outside 400–600
    t9 = BidRequirement(category="FILTER_GRADE", normalized={"standard": "ISO29461", "class": "T9"})
    assert score(item, "FT-CP200", [t9]).parts["grade"] in (0.0, 0.5)


def test_type_mismatch_and_hvac_domain(company_data):
    item = BidItem(
        name="데미스터",
        spec_text="594*594*50 데미스터용 역사 공조",
        width_mm=594,
        height_mm=594,
        depth_mm=50,
    )
    match = score(item, "FT-VB500")
    assert match.parts["type"] == 0.0
    assert match.parts["application"] == 0.0  # 공조/역사 vs GT 흡기 제품
    assert match.score < 0.6


def test_match_items_and_fit(company_data):
    bid = BidNotice.objects.create(title="[울산] GT Pulse Filter 구매", buyer_org="한국동서발전")
    cylinder = BidItem.objects.create(
        bid=bid,
        item_no="1",
        name="Pulse Cartridge",
        filter_type="CARTRIDGE_PULSE",
        diameter_mm=324,
        length_mm=660,
    )
    BidItem.objects.create(
        bid=bid,
        item_no="2",
        name="Pulse Cartridge cone",
        filter_type="CARTRIDGE_PULSE",
        diameter_mm=445,
        diameter2_mm=324,
        length_mm=660,
    )
    BidRequirement.objects.create(
        bid=bid, category="CERTIFICATION", title="ISO 9001", normalized={"cert_type": "ISO9001"}
    )
    BidRequirement.objects.create(
        bid=bid, category="TEST_STANDARD", title="EN779", normalized={"standard": "EN779"}
    )
    BidRequirement.objects.create(
        bid=bid, category="TEST_STANDARD", title="ASHRAE", normalized={"standard": "ASHRAE52_2"}
    )

    ctx = EvaluationContext.for_bid(bid)
    match_items(bid, ctx)
    cylinder.refresh_from_db()
    assert cylinder.matched_product.model_no == "FT-CP200"
    assert cylinder.product_matches.count() == 3
    assert [m.rank for m in cylinder.product_matches.all()] == [1, 2, 3]

    fit = compute_fit(bid, ctx)
    b = fit["breakdown"]
    assert b["product_type"]["ratio"] == 1.0
    assert b["power_plant"]["ratio"] == 1.0  # keywords: 발전, GT
    assert b["qualification"]["ratio"] == 1.0  # ISO 9001 valid
    assert b["spec_coverage"]["ratio"] == 0.5  # EN779 yes, ASHRAE 52.2 no
    assert fit["score"] == 40 + 15 + 25 + 10


def test_blocking_qualification_zeroes_component(company_data):
    bid = BidNotice.objects.create(title="공조 필터", buyer_org="공항공사")
    BidRequirement.objects.create(
        bid=bid, category="CERTIFICATION", title="ISO 14001", normalized={"cert_type": "ISO14001"}
    )
    fit = compute_fit(bid)
    assert fit["breakdown"]["qualification"]["ratio"] == 0.0
    assert fit["breakdown"]["product_type"]["ratio"] == 0.0  # no items
    assert fit["breakdown"]["spec_coverage"]["ratio"] == 1.0  # no test-standard requirement
    assert fit["is_power_plant"] is False
