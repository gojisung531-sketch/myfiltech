"""Staging storage boundaries, using synthetic JSON and an isolated test DB only."""

from copy import deepcopy

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.models.deletion import ProtectedError

from apps.bids.models import BidNotice, BidRequirement
from apps.company.models import (
    Certificate,
    Company,
    Product,
    ReportRegisterRow,
    ReportRegisterVersion,
    TestReport,
)
from apps.evaluation.context import EvaluationContext
from apps.evaluation.evidence import company_evidence

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def isolated_test_database():
    assert connection.settings_dict["NAME"].startswith("test_")
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_database()")
        assert cursor.fetchone()[0] == connection.settings_dict["NAME"]


@pytest.fixture
def version():
    return ReportRegisterVersion.objects.create(
        sha256="a" * 64, display_name="boundary-only.xlsx", parser_version="synthetic-reader-v1"
    )


def payload_for(version, sheet="성능", row=4):
    """No real company identifiers, workbook contents or product seed files."""
    return {
        "source": {"file_sha256": version.sha256, "sheet": sheet, "row": row},
        "fields": {
            "report_no": {
                "cell": f"C{row}",
                "raw_value": "BOUNDARY-ONLY",
                "value": "BOUNDARY-ONLY",
            },
            "model": {"cell": f"J{row}", "raw_value": "TEST-MEDIA", "value": "TEST-MEDIA"},
            "test_standard": {"cell": f"I{row}", "value": "ISO 29463-3:2011"},
            "airflow": {
                "cell": f"AH{row}",
                "requested_cell": f"AH{row}",
                "raw_value": 0.95,
                "xml_value": "0.95",
                "value": 0.95,
                "number_format": "0.0%",
                "formula": {"text": "1-0.05", "attributes": {}},
                "cached_value": 0.95,
                "unit": {"cell": f"AI{row}", "raw_value": "ft3/m", "value": "ft3/m"},
                "normalized": None,
                "headers": [{"cell": "AH1", "value": "TEST CONDITION"}],
            },
            "media_pressure_drop_lab": {
                "cell": f"X{row}",
                "raw_value": 10,
                "number_format": "0.00",
                "unit": {"cell": f"Y{row}", "raw_value": "mmH2O@32LPM"},
                "normalized": None,
            },
            "converted_example": {
                "raw_value": 2,
                "normalized": {"value": 120, "unit": "m³/h", "formula": "value * 60"},
            },
        },
        "unmapped_cells": [{"cell": f"BJ{row}", "raw_value": "boundary annotation"}],
        "warnings": [{"code": "unsupported_unit", "field": "airflow", "cell": f"AH{row}"}],
        "review": {
            "ownership": "UNKNOWN",
            "test_target": "UNKNOWN",
            "original_report_verified": False,
        },
        "extra_future_key": {"untouched": [None, False, 0, ""]},
    }


def store_row(version, sheet="성능", row=4, payload=None, **values):
    return ReportRegisterRow.objects.create(
        file_version=version,
        sheet_name=sheet,
        row_number=row,
        payload=payload_for(version, sheet, row) if payload is None else payload,
        **values,
    )


def test_sha_identity_survives_rename_and_rejects_second_parser_version(version):
    renamed, created = ReportRegisterVersion.objects.get_or_create(
        sha256=version.sha256,
        defaults={"display_name": "renamed.xlsx", "parser_version": version.parser_version},
    )
    assert not created and renamed.pk == version.pk
    assert renamed.display_name == "boundary-only.xlsx"
    with pytest.raises(IntegrityError), transaction.atomic():
        ReportRegisterVersion.objects.create(
            sha256=version.sha256, display_name="renamed.xlsx", parser_version="synthetic-reader-v2"
        )
    version.refresh_from_db()
    assert version.parser_version == "synthetic-reader-v1"


def test_duplicate_source_coordinate_is_rejected_by_db(version):
    original = store_row(version)
    with pytest.raises(IntegrityError), transaction.atomic():
        store_row(version)
    original.refresh_from_db()
    assert ReportRegisterRow.objects.count() == 1
    assert original.payload == payload_for(version)


def test_same_report_number_is_preserved_in_other_rows_and_sheets(version):
    rows = [store_row(version), store_row(version, row=5), store_row(version, sheet="재질")]
    assert len({r.pk for r in rows}) == 3
    assert [r.payload["fields"]["report_no"]["value"] for r in ReportRegisterRow.objects.all()] == [
        "BOUNDARY-ONLY"
    ] * 3
    assert not Product.objects.exists()
    assert not TestReport.objects.exists()
    assert not Certificate.objects.exists()


def test_missing_identifiers_are_not_fabricated(version):
    payload = payload_for(version)
    for name in ("report_no", "model"):
        payload["fields"][name].update(value=None, raw_value=None)
    payload["fields"]["entry_no"] = {"value": None}
    stored = store_row(version, payload=payload)
    stored.refresh_from_db()
    assert stored.payload == payload
    assert stored.payload["fields"]["report_no"]["value"] is None
    assert stored.payload["fields"]["model"]["value"] is None


def test_new_file_version_keeps_old_row_at_same_coordinate(version):
    original = store_row(version)
    before = deepcopy(original.payload)
    revision = ReportRegisterVersion.objects.create(
        sha256="b" * 64, display_name=version.display_name, parser_version=version.parser_version
    )
    revised = store_row(revision)
    original.refresh_from_db()
    assert original.payload == before
    assert revised.pk != original.pk and ReportRegisterRow.objects.count() == 2


def test_json_roundtrip_keeps_merged_evidence_conditions_and_unknown_units(version):
    payload = payload_for(version, "재질", 24)
    payload["fields"]["report_no"].update(
        cell="E23", requested_cell="E24", merged_range="E23:E24", number_format="General"
    )
    stored = store_row(version, sheet="재질", row=24, payload=deepcopy(payload))
    stored.full_clean()
    stored.refresh_from_db()
    assert stored.payload == payload
    assert stored.payload["fields"]["report_no"]["cell"] == "E23"
    assert stored.payload["source"]["row"] == 24
    assert stored.payload["fields"]["test_standard"]["value"] == "ISO 29463-3:2011"
    assert stored.payload["fields"]["airflow"]["normalized"] is None


def test_unknown_defaults_are_distinct_from_explicit_false(version):
    row = store_row(version)
    row.refresh_from_db()
    assert row.review_status == "PENDING"
    assert row.ownership == row.test_target == "UNKNOWN"
    fields = ("is_lab_accredited", "is_official_certification", "original_report_verified")
    assert all(getattr(row, name) is None for name in fields)
    assert row.payload["review"]["original_report_verified"] is False
    for name in fields:
        setattr(row, name, False)
    row.save(update_fields=list(fields))
    row.refresh_from_db()
    assert all(getattr(row, name) is False for name in fields)


def test_json_defaults_are_not_shared():
    first, second = ReportRegisterVersion(), ReportRegisterVersion()
    first.source_metadata["changed"] = True
    assert second.source_metadata == {}
    a, b = ReportRegisterRow(), ReportRegisterRow()
    a.payload["changed"] = []
    assert b.payload == {}


def test_file_version_with_rows_cannot_be_deleted(version):
    store_row(version)
    with pytest.raises(ProtectedError):
        version.delete()
    assert ReportRegisterRow.objects.count() == ReportRegisterVersion.objects.count() == 1


@pytest.mark.parametrize("sheet,row", [("", 4), ("성능", 0), ("성능", 1048577)])
def test_invalid_coordinate_is_rejected_by_db(version, sheet, row):
    with pytest.raises(IntegrityError), transaction.atomic():
        store_row(version, sheet=sheet, row=row)


@pytest.mark.parametrize(
    "source_change", [{"sheet": "other"}, {"row": 5}, {"file_sha256": "b" * 64}]
)
def test_model_validation_rejects_contradictory_source(version, source_change):
    payload = payload_for(version)
    payload["source"].update(source_change)
    row = ReportRegisterRow(file_version=version, sheet_name="성능", row_number=4, payload=payload)
    with pytest.raises(ValidationError, match="출처"):
        row.full_clean()


def test_sha_requires_canonical_lowercase_hex():
    with pytest.raises(IntegrityError), transaction.atomic():
        ReportRegisterVersion.objects.create(
            sha256="A" * 64, display_name="boundary.xlsx", parser_version="synthetic-reader-v1"
        )


@pytest.mark.parametrize("payload", [[], {"source": []}])
def test_model_validation_rejects_malformed_source(version, payload):
    row = ReportRegisterRow(file_version=version, sheet_name="성능", row_number=4, payload=payload)
    with pytest.raises(ValidationError) as error:
        row.full_clean()
    assert "payload" in error.value.message_dict


def test_invalid_file_reference_is_a_validation_error(version):
    row = ReportRegisterRow(
        file_version_id=version.pk + 10000000,
        sheet_name="성능",
        row_number=4,
        payload=payload_for(version),
    )
    with pytest.raises(ValidationError) as error:
        row.full_clean()
    assert "file_version" in error.value.message_dict


def test_staging_is_excluded_from_empty_evaluation_context(version):
    store_row(version)
    assert not Company.objects.exists()
    assert not any(model.objects.exists() for model in (Product, TestReport, Certificate))
    ctx = EvaluationContext.for_bid(BidNotice())
    assert ctx.products == ctx.test_reports == ctx.certificates == []
    assert Company.objects.count() == 1  # Company.load(), not automatic report promotion.
    assert not any(model.objects.exists() for model in (Product, TestReport, Certificate))


def test_staging_does_not_update_existing_evidence_or_appear_in_context(version):
    product = Product.objects.create(model_no="TEST-MEDIA", initial_dp_pa=123)
    formal = TestReport.objects.create(
        report_no="BOUNDARY-ONLY", product=product, standard="EXISTING"
    )
    cert = Certificate.objects.create(cert_no="TEST-CERT", name="EXISTING")
    before = {model: list(model.objects.values()) for model in (Product, TestReport, Certificate)}
    row = store_row(
        version, ownership="FILTECH", test_target="FINISHED_PRODUCT", is_official_certification=True
    )
    assert {model: list(model.objects.values()) for model in before} == before
    ctx = EvaluationContext.for_bid(BidNotice())
    assert [p.pk for p in ctx.products] == [product.pk]
    assert [r.pk for r in ctx.test_reports] == [formal.pk]
    assert [c.pk for c in ctx.certificates] == [cert.pk]
    assert ctx.reports_for(product) == [formal]
    evidence = company_evidence(BidRequirement(category="TEST_STANDARD"), ctx)
    assert len(evidence["test_reports"]) == 1
    assert evidence["test_reports"][0]["standard"] == "EXISTING"
    assert row.payload["fields"]["test_standard"]["value"] == "ISO 29463-3:2011"
