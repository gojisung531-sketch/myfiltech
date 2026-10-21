"""Initial company data must load exactly as specs/12-initial-data.md §2.2 (rules only)."""

from datetime import date

import pytest

from apps.company.models import Certificate, Company, DeliveryRecord, Product, TestReport
from apps.documents.loader import load_company
from apps.documents.models import Document

pytestmark = pytest.mark.django_db

PRODUCTS = {
    # model: (type, w, h, d, airflow, initial_dp, final_dp, grades)
    "FT-PF100": ("PANEL", 592, 592, 48, 3400, 45, 200, {"iso16890_class": "ISO Coarse 65%"}),
    "FT-BG300": ("POCKET_BAG", 592, 592, 600, 3400, 95, 450, {"iso16890_class": "ISO ePM1 60%"}),
    "FT-VB500": (
        "V_BANK",
        592,
        592,
        292,
        4250,
        130,
        600,
        {"iso16890_class": "ISO ePM1 85%", "iso29461_class": "T9", "en779_class": "F9"},
    ),
    "FT-EP700": ("V_BANK", 592, 592, 292, 4250, 190, 600, {"en1822_class": "E12"}),
    "FT-HP900": ("MINI_PLEAT_HEPA", 610, 610, 292, 3400, 250, 600, {"en1822_class": "H13"}),
}

REPORTS = {
    "AFT-2017-0730": ("FT-VB500", "EN779", "F9", "2017-07-30"),
    "AFT-2023-0211": ("FT-BG300", "ISO16890", "ISO ePM1 60%", "2023-02-11"),
    "AFT-2024-0517": ("FT-PF100", "ISO16890", "ISO Coarse 65%", "2024-05-17"),
    "AFT-2024-0822": ("FT-VB500", "UL900", "적합 (Class 1 상당)", "2024-08-22"),
    "AFT-2024-1105": ("FT-CP200", "ISO29461", "T7", "2024-11-05"),
    "AFT-2025-0402": ("FT-VB500", "ISO16890", "ISO ePM1 85%", "2025-04-02"),
    "AFT-2025-0613": ("FT-VB500", "ISO29461", "T9", "2025-06-13"),
    "AFT-2025-0921": ("FT-EP700", "EN1822", "E12", "2025-09-21"),
    "AFT-2026-0318": ("FT-HP900", "EN1822", "H13", "2026-03-18"),
}


def test_load_summary(company_data):
    assert company_data["created"] == 19
    assert company_data["failed"] == []
    assert Document.objects.filter(status=Document.Status.REVIEWED).count() == 19


def test_products(company_data):
    assert Product.objects.count() == 6
    for model, (kind, w, h, d, airflow, initial, final, grades) in PRODUCTS.items():
        p = Product.objects.get(model_no=model)
        assert (p.filter_type, p.width_mm, p.height_mm, p.depth_mm) == (kind, w, h, d), model
        assert (p.rated_airflow_m3h, p.initial_dp_pa, p.final_dp_pa) == (airflow, initial, final)
        for field, value in grades.items():
            assert getattr(p, field) == value, (model, field)
        assert len(p.airflow_dp_curve) >= 3


def test_special_product_details(company_data):
    cp = Product.objects.get(model_no="FT-CP200")
    assert cp.filter_type == "CARTRIDGE_PULSE"
    assert (cp.diameter_mm, cp.diameter2_mm, cp.length_mm) == (324, 215, 660)
    assert (cp.iso16890_class, cp.iso29461_class, cp.gasket) == ("ISO ePM1 55%", "T7", "EPDM")
    ep = Product.objects.get(model_no="FT-EP700")
    assert ep.frame_material == "ABS 수지"
    assert ep.frame_options == [{"material": "SUS304", "model": "FT-EP700S", "note": "주문제작"}]
    assert Product.objects.get(model_no="FT-HP900").max_rh == 90
    assert "UL 900 준용" in Product.objects.get(model_no="FT-VB500").fire_rating
    assert "자기소화성" in Product.objects.get(model_no="FT-PF100").fire_rating
    vb = Product.objects.get(model_no="FT-VB500")
    assert vb.airflow_dp_curve[:2] == [
        {"airflow_m3h": 2125, "dp_pa": 58},
        {"airflow_m3h": 3400, "dp_pa": 102},
    ]


def test_test_reports(company_data):
    assert TestReport.objects.count() == 9
    for number, (model, family, result, issued) in REPORTS.items():
        report = TestReport.objects.get(report_no=number)
        assert report.product.model_no == model, number
        assert (report.standard_family, report.result_class) == (family, result), number
        assert report.issue_date == date.fromisoformat(issued)
    en779 = TestReport.objects.get(report_no="AFT-2017-0730")
    assert en779.is_obsolete_standard and en779.is_official_certification
    ul = TestReport.objects.get(report_no="AFT-2024-0822")
    assert not ul.is_official_certification and not ul.is_obsolete_standard
    cp = TestReport.objects.get(report_no="AFT-2024-1105")
    assert (cp.results["0.4 µm 초기 효율"], cp.results["0.4 µm 컨디셔닝 후 효율"]) == (
        "68.5 %",
        "61.2 %",
    )
    hp = TestReport.objects.get(report_no="AFT-2026-0318")
    assert hp.results["누설 시험"] == "누설 없음 (스캔시험 적합)"
    assert TestReport.objects.get(report_no="AFT-2025-0613").initial_dp_pa == 130


def test_certificates(company_data):
    assert Certificate.objects.count() == 3
    reference = date(2026, 10, 5)
    iso9001 = Certificate.objects.get(cert_no="GQ-24-08812")
    assert (iso9001.cert_type, iso9001.valid_until) == ("ISO9001", date(2027, 8, 19))
    assert iso9001.status_on(reference) == "VALID"
    iso14001 = Certificate.objects.get(cert_no="GE-23-06120")
    assert iso14001.cert_type == "ISO14001"
    assert iso14001.status_on(reference) == "EXPIRED"
    direct = Certificate.objects.get(cert_no="DP-2025-0203-117")
    assert direct.cert_type == "DIRECT_PRODUCTION"
    assert direct.product_codes == ["4013xxxx"]
    assert direct.status_on(reference) == "VALID"


def test_delivery_records(company_data):
    assert DeliveryRecord.objects.count() == 10
    assert DeliveryRecord.objects.filter(is_power_plant=True).count() == 10
    first = DeliveryRecord.objects.get(delivered_ym="2021-11")
    assert first.client == "가상남부발전(주)"
    assert sorted(first.products.values_list("model_no", flat=True)) == ["FT-BG300", "FT-PF100"]
    assert first.plant_type == "CCPP"
    sus = DeliveryRecord.objects.get(delivered_ym="2025-06")
    assert sus.notes == "E12 동급, SUS304 프레임 사양 아님"
    vb = DeliveryRecord.objects.get(delivered_ym="2023-10")
    assert vb.quantity == [{"model": "FT-VB500", "qty": 560, "unit": "EA"}]
    assert DeliveryRecord.objects.get(delivered_ym="2025-12").quantity[0]["unit"] == "세트"
    assert DeliveryRecord.objects.get(delivered_ym="2026-04").plant_type == "CHP"
    assert all(r.amount_krw is None for r in DeliveryRecord.objects.all())


def test_company_contact_filled(company_data):
    company = Company.load()
    assert (company.name, company.phone, company.email) == (
        "(주)필텍",
        "031-000-0000",
        "sales@example.com",
    )


def test_reload_is_idempotent(company_data):
    second = load_company()
    assert (second["created"], second["skipped"]) == (0, 19)
    assert Product.objects.count() == 6


def test_update_mode_keeps_locked_metadata(company_data):
    document = Document.objects.get(original_filename="FT-VB500_기술사양서.pdf")
    row = document.metadata.get(key="initial_dp_pa")
    row.value, row.is_locked = 125, True
    row.save()
    summary = load_company(mode="update")
    assert summary["updated"] == 19
    assert Product.objects.get(model_no="FT-VB500").initial_dp_pa == 125
