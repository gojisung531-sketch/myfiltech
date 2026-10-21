from datetime import timedelta

import pytest
from django.utils import timezone

from apps.company.models import Certificate, Product

pytestmark = pytest.mark.django_db


def test_company_singleton(admin_client, manager_client):
    assert manager_client.get("/api/company").status_code == 200
    assert manager_client.put("/api/company", {"name": "x"}, format="json").status_code == 403
    res = admin_client.put(
        "/api/company",
        {"name": "(주)필텍", "is_sme": True, "g2b_registered_items": [{"code": "4016150501"}]},
        format="json",
    )
    assert res.status_code == 200
    assert admin_client.get("/api/company").data["g2b_registered_items"] == [{"code": "4016150501"}]


def test_product_crud_and_permissions(admin_client, manager_client):
    payload = {"model_no": "FT-NEW1", "name": "신규", "filter_type": "PANEL", "width_mm": 592}
    assert manager_client.post("/api/products", payload, format="json").status_code == 403
    res = admin_client.post("/api/products", payload, format="json")
    assert res.status_code == 201 and res.data["filter_type_label"] == "패널형"
    product_id = res.data["id"]
    res = admin_client.patch(f"/api/products/{product_id}", {"initial_dp_pa": 40}, format="json")
    assert res.data["initial_dp_pa"] == 40
    detail = manager_client.get(f"/api/products/{product_id}").data
    assert detail["test_reports"] == [] and detail["delivery_records"] == []
    assert admin_client.delete(f"/api/products/{product_id}").status_code == 204


def test_lists_after_initial_load(company_data, manager_client):
    assert manager_client.get("/api/products").data["count"] == 6
    vb = Product.objects.get(model_no="FT-VB500")
    detail = manager_client.get(f"/api/products/{vb.id}").data
    assert len(detail["test_reports"]) == 4
    assert {r["delivered_ym"] for r in detail["delivery_records"]} == {"2023-10", "2024-11"}
    assert manager_client.get(f"/api/test-reports?product={vb.id}").data["count"] == 4
    assert manager_client.get("/api/test-reports?standard_family=EN1822").data["count"] == 2
    assert manager_client.get("/api/products?q=HEPA").data["count"] == 1
    assert manager_client.get("/api/delivery-records?q=SUS304").data["count"] == 1
    assert manager_client.get(f"/api/delivery-records?product={vb.id}").data["count"] == 2


def test_certificate_status(admin_client):
    today = timezone.localdate()
    for no, days in (("A", -1), ("B", 30), ("C", 400)):
        Certificate.objects.create(cert_no=no, valid_until=today + timedelta(days=days))
    Certificate.objects.create(cert_no="D")
    rows = {r["cert_no"]: r for r in admin_client.get("/api/certificates").data["results"]}
    assert {k: v["status"] for k, v in rows.items()} == {
        "A": "EXPIRED",
        "B": "EXPIRING",
        "C": "VALID",
        "D": "UNKNOWN",
    }
    assert rows["A"]["status_label"] == "만료"
    for status, expected in (("EXPIRED", "A"), ("EXPIRING", "B"), ("VALID", "C"), ("UNKNOWN", "D")):
        res = admin_client.get(f"/api/certificates?status={status}").data["results"]
        assert [r["cert_no"] for r in res] == [expected]


def test_certificate_date_validation(admin_client):
    res = admin_client.post(
        "/api/certificates",
        {"cert_no": "X", "valid_from": "2026-01-01", "valid_until": "2025-01-01"},
        format="json",
    )
    assert res.status_code == 400


def test_delivery_record_products(admin_client):
    product = Product.objects.create(model_no="FT-A")
    res = admin_client.post(
        "/api/delivery-records",
        {
            "delivered_ym": "2026-01",
            "client": "가상발전",
            "model_nos": ["FT-A"],
            "products": [product.id],
            "is_power_plant": True,
            "plant_type": "CCPP",
        },
        format="json",
    )
    assert res.status_code == 201
    assert res.data["products"] == [product.id] and res.data["plant_type_label"] == "복합화력"
    assert admin_client.get("/api/delivery-records?is_power_plant=false").data["count"] == 0
