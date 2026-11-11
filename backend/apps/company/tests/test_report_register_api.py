"""Synthetic admin read contracts. No corporate fixture or workbook parsing."""

import json
from copy import deepcopy
from unittest.mock import Mock

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.company.models import (
    Certificate,
    Company,
    DeliveryRecord,
    Product,
    ReportRegisterRow,
    ReportRegisterVersion,
    TestReport,
)
from apps.evaluation.models import RequirementEvaluation
from apps.llm.models import LLMCallLog

pytestmark = pytest.mark.django_db
VERSIONS = "/api/report-register-versions"
ROWS = "/api/report-register-rows"


@pytest.fixture
def register_data():
    version = ReportRegisterVersion.objects.create(
        sha256="a" * 64,
        display_name="synthetic.xlsx",
        parser_version="synthetic-reader",
        source_metadata={"private_path": "C:/PRIVATE-VERSION", "sheets": [{"record_count": 999}]},
    )
    empty = ReportRegisterVersion.objects.create(
        sha256="b" * 64, display_name="empty.xlsx", parser_version="synthetic-reader"
    )
    rows = []
    for index in range(27):
        sheet, number = ("성능", index + 4) if index < 25 else ("재질", index - 22)
        values = {
            "report_no": "SYNTHETIC-DUP" if index < 2 else f"BOUNDARY-{index}",
            "model": "MEDIA-ONE" if index == 1 else None,
            "sample_name": "SUBJECT-ONE" if index == 25 else "",
            "test_standard": "ISO-BOUNDARY" if index == 3 else "STD-COMMON",
            "lab_name": "LAB-UNIQUE" if index == 2 else "LAB-COMMON",
            "issue_date": "2024-01-02T00:00:00",
        }
        fields = {
            name: {
                "value": value,
                "raw_value": "RAW-ONLY",
                "cell": f"C{number}",
                "formula": {"text": "FORMULA-ONLY"},
            }
            for name, value in values.items()
        }
        if sheet == "재질":
            fields.pop("model")  # Absent key and JSON null both remain unavailable.
        payload = {
            "source": {"file_sha256": version.sha256, "sheet": sheet, "row": number},
            "fields": fields,
            "unmapped_cells": [{"value": "UNMAPPED-ONLY"}],
            "warnings": [{"code": "WARNING-ONLY"}, {"code": "WARNING-ONLY"}, {"code": "A-WARNING"}],
            "review": {"ownership": "UNKNOWN", "original_report_verified": False},
        }
        row = ReportRegisterRow(
            file_version=version, sheet_name=sheet, row_number=number, payload=payload
        )
        if index == 1:
            row.review_status = "NEEDS_CONFIRMATION"
            row.ownership = "THIRD_PARTY"
            row.test_target = "MEDIA"
            row.is_lab_accredited = False
        rows.append(row)
    ReportRegisterRow.objects.bulk_create(rows)
    return version, empty, rows


def paths(data):
    version, _, rows = data
    return (VERSIONS, f"{VERSIONS}/{version.pk}", ROWS, f"{ROWS}/{rows[0].pk}")


def test_all_paths_require_admin(register_data, admin_client, manager_client, api_client):
    for path in paths(register_data):
        assert api_client.get(path).status_code == 401
        assert manager_client.get(path).status_code == 403
        assert admin_client.get(path).status_code == 200
        assert admin_client.head(path).status_code == 200
        assert admin_client.options(path).status_code == 200


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_admin_write_methods_are_not_available(register_data, admin_client, method):
    for path in paths(register_data):
        response = getattr(admin_client, method)(path, {"ownership": "FILTECH"}, format="json")
        assert response.status_code == 405
        assert set(response["Allow"].split(", ")) == {"GET", "HEAD", "OPTIONS"}


def test_version_fields_and_aggregates_use_current_database(register_data, admin_client):
    version, empty, _ = register_data
    listing = admin_client.get(VERSIONS).data
    assert listing["count"] == 2
    assert [v["id"] for v in listing["results"]] == [version.pk, empty.pk]
    assert listing["results"][0]["row_count"] == 27
    assert set(listing["results"][0]) == {
        "id",
        "sha256",
        "display_name",
        "parser_version",
        "row_count",
        "created_at",
        "updated_at",
    }
    detail = admin_client.get(f"{VERSIONS}/{version.pk}").data
    assert detail["row_count"] == 27
    assert detail["sheet_counts"] == {"성능": 25, "재질": 2}
    assert detail["review_status_counts"] == {"NEEDS_CONFIRMATION": 1, "PENDING": 26}
    assert "PRIVATE-VERSION" not in json.dumps(detail)
    assert "source_metadata" not in detail
    zero = admin_client.get(f"{VERSIONS}/{empty.pk}").data
    assert zero["row_count"] == 0 and zero["sheet_counts"] == zero["review_status_counts"] == {}


def test_row_list_detail_and_pagination_preserve_null_and_duplicate_values(
    register_data, admin_client
):
    version, _, rows = register_data
    first = admin_client.get(ROWS).data
    assert first["count"] == 27 and len(first["results"]) == 20
    assert first["previous"] is None
    second = admin_client.get(first["next"]).data
    assert len(second["results"]) == 7 and second["next"] is None
    all_ids = [r["id"] for r in first["results"] + second["results"]]
    assert all_ids == [
        r.pk
        for r in sorted(rows, key=lambda r: (r.file_version_id, r.sheet_name, r.row_number, r.pk))
    ]
    item = first["results"][0]
    assert "payload" not in item
    assert set(item) == {
        "id",
        "file_version",
        "source",
        "summary",
        "review",
        "warning_count",
        "warning_codes",
        "created_at",
        "updated_at",
    }
    assert item["source"] == {"file_sha256": version.sha256, "sheet": "성능", "row": 4}
    assert item["summary"]["model"] is None and item["summary"]["sample_name"] == ""
    assert item["review"]["original_report_verified"] is None
    assert item["warning_count"] == 3 and item["warning_codes"] == ["A-WARNING", "WARNING-ONLY"]
    assert admin_client.get(ROWS, {"q": "SYNTHETIC-DUP"}).data["count"] == 2
    detail = admin_client.get(f"{ROWS}/{rows[1].pk}").data
    assert detail["payload"] == rows[1].payload
    assert detail["review"]["ownership"] == "THIRD_PARTY"
    assert detail["payload"]["review"]["ownership"] == "UNKNOWN"
    assert detail["review"]["is_lab_accredited"] is False
    assert detail["review"]["original_report_verified"] is None
    assert detail["payload"]["review"]["original_report_verified"] is False


@pytest.mark.parametrize(
    "term,count",
    [
        ("media-one", 1),
        ("SUBJECT-ONE", 1),
        ("ISO-BOUNDARY", 1),
        ("LAB-UNIQUE", 1),
        ("no-match", 0),
        ("RAW-ONLY", 0),
        ("FORMULA-ONLY", 0),
        ("UNMAPPED-ONLY", 0),
        ("WARNING-ONLY", 0),
        ("2024-01-02", 0),
        ("null", 0),
    ],
)
def test_search_uses_only_five_summary_values(register_data, admin_client, term, count):
    response = admin_client.get(ROWS, {"q": term})
    assert response.status_code == 200 and response.data["count"] == count


def test_filters_and_combinations(register_data, admin_client):
    version, empty, _ = register_data
    for filters, count in [
        ({"file_version": version.pk}, 27),
        ({"file_version": empty.pk}, 0),
        ({"sheet_name": "재질"}, 2),
        ({"review_status": "NEEDS_CONFIRMATION"}, 1),
        ({"ownership": "THIRD_PARTY"}, 1),
        ({"test_target": "MEDIA"}, 1),
        (
            {
                "file_version": version.pk,
                "sheet_name": "성능",
                "ownership": "THIRD_PARTY",
                "q": "MEDIA-ONE",
            },
            1,
        ),
    ]:
        result = admin_client.get(ROWS, filters)
        assert result.status_code == 200 and result.data["count"] == count


@pytest.mark.parametrize(
    "params",
    [
        {"file_version": "abc"},
        {"file_version": "0"},
        {"file_version": "9" * 30},
        {"review_status": "APPROVED"},
        {"ownership": "ANY"},
        {"test_target": "PRODUCT"},
        {"sheet_name": ""},
        {"page": "bad"},
        {"page": "0"},
        {"page_size": "0"},
        {"q": "x" * 201},
    ],
)
def test_bad_filters_have_uniform_400(register_data, admin_client, params):
    response = admin_client.get(ROWS, params)
    assert response.status_code == 400
    assert response.data["code"] == "invalid" and "errors" in response.data


def test_404_and_version_bad_page(register_data, admin_client):
    for url in (f"{VERSIONS}/999999", f"{ROWS}/999999", f"{ROWS}?page=999999"):
        assert admin_client.get(url).status_code == 404
    assert admin_client.get(VERSIONS, {"page_size": "bad"}).status_code == 400


def test_bounded_queries_sql_pagination_and_payload_projection(register_data, admin_client):
    version, _, _ = register_data
    ReportRegisterRow.objects.bulk_create(
        [
            ReportRegisterRow(
                file_version=version, sheet_name="성능", row_number=100 + i, payload={}
            )
            for i in range(180)
        ]
    )
    for url, size in ((ROWS, 1), (ROWS, 20), (ROWS, 300), (VERSIONS, 20)):
        with CaptureQueriesContext(connection) as queries:
            response = admin_client.get(url, {"page_size": size})
        assert response.status_code == 200
        assert len(queries) == 2  # count + SQL-limited page; no per-row FK queries.
        assert len(response.data["results"]) == (min(size, 200) if url == ROWS else 2)
        if url == ROWS:
            assert '"company_reportregisterrow"."payload",' not in queries[-1]["sql"]
            assert "LIMIT" in queries[-1]["sql"]


def test_reads_are_side_effect_free_and_formal_api_excludes_staging(
    register_data, admin_client, monkeypatch
):
    forbidden = Mock(side_effect=AssertionError("Read endpoint must not call services"))
    for target in (
        "apps.company.report_preview.preview_filtech_reports",
        "apps.company.report_staging.stage_filtech_reports",
        "apps.company.mapping.apply",
        "apps.company.models.Company.load",
        "apps.llm.services.get_provider_class",
    ):
        monkeypatch.setattr(target, forbidden)
    models = (
        ReportRegisterVersion,
        ReportRegisterRow,
        Company,
        Product,
        TestReport,
        Certificate,
        DeliveryRecord,
        RequirementEvaluation,
        LLMCallLog,
    )
    before = {m: deepcopy(list(m.objects.order_by("pk").values())) for m in models}
    for path in paths(register_data):
        assert admin_client.get(path).status_code == 200
    for path in (
        "/api/products",
        "/api/test-reports",
        "/api/certificates",
        "/api/delivery-records",
    ):
        assert admin_client.get(path).data["count"] == 0
    assert {m: list(m.objects.order_by("pk").values()) for m in models} == before
    forbidden.assert_not_called()
