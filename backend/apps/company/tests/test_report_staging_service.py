"""Synthetic staging inputs; never imports corporate workbook data as fixtures."""

import hashlib
import io
import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Barrier
from unittest.mock import Mock

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import close_old_connections, connection, connections

from apps.company import report_staging as staging
from apps.company.models import (
    Certificate,
    Company,
    DeliveryRecord,
    Product,
    ReportRegisterRow,
    ReportRegisterVersion,
    TestReport,
)
from apps.company.tests.test_report_preview import register as register
from apps.llm.models import LLMCallLog

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def test_database_only():
    assert connection.settings_dict["NAME"].startswith("test_")


def evidence(cell, value):
    return {
        "cell": cell,
        "raw_value": value,
        "xml_value": None,
        "value": value,
        "value_type": "s",
        "number_format": "General",
        "formula": None,
        "cached_value": None,
    }


@pytest.fixture
def case(tmp_path, monkeypatch):
    path = tmp_path / "synthetic-only.xlsx"
    path.write_bytes(b"synthetic boundary input, reader is mocked")
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    sheets = []
    for name, numbers in (("성능", [4, 5]), ("재질", [3])):
        records = []
        for number in numbers:
            field = {
                **evidence(f"C{number}", "SYNTHETIC-ONLY"),
                "requested_cell": f"C{number}",
                "merged_range": None,
                "headers": [],
                "normalized": None,
            }
            records.append(
                {
                    "source": {"file_sha256": sha, "sheet": name, "row": number},
                    "fields": {"report_no": field},
                    "unmapped_cells": [],
                    "warnings": [],
                    "review": {
                        "ownership": "UNKNOWN",
                        "test_target": "UNKNOWN",
                        "original_report_verified": False,
                    },
                    "future_key": [None, False, 0, ""],
                }
            )
        sheets.append(
            {
                "name": name,
                "record_count": len(records),
                "records": records,
                "warnings": {},
                "missing": {},
                "duplicate_entry_numbers": [],
            }
        )
    preview = {
        "mode": "READ_ONLY_PREVIEW",
        "file": {"name": path.name, "sha256": sha, "date_system": "1900"},
        "sheets": sheets,
        "duplicate_report_numbers": [],
        "limitations": [],
    }
    reader = Mock(side_effect=lambda _: deepcopy(preview))
    monkeypatch.setattr(staging.report_preview, "preview_filtech_reports", reader)
    return path, sha, preview


def snapshot():
    return {
        "versions": list(ReportRegisterVersion.objects.order_by("pk").values()),
        "rows": list(ReportRegisterRow.objects.order_by("pk").values()),
    }


def apply(case):
    path, sha, _ = case
    return staging.stage_filtech_reports(path, apply=True, expected_sha256=sha)


def test_default_dry_run_has_no_writes_before_or_after_import(case):
    before = snapshot()
    result = staging.stage_filtech_reports(case[0])
    assert result["mode"] == "DRY_RUN" and result["would_create_rows"] == 3
    assert snapshot() == before
    apply(case)
    before = snapshot()
    assert staging.stage_filtech_reports(case[0])["reused_rows"] == 3
    assert snapshot() == before


def test_initial_import_preserves_full_payload_and_unknown_defaults(case):
    result = apply(case)
    assert result["created_versions"] == 1 and result["created_rows"] == 3
    assert result["sheet_counts"] == {"성능": 2, "재질": 1}
    version = ReportRegisterVersion.objects.get()
    assert version.source_metadata["parser"] == staging.parser_provenance()
    assert all("records" not in s for s in version.source_metadata["sheets"])
    incoming = {(s["name"], r["source"]["row"]): r for s in case[2]["sheets"] for r in s["records"]}
    for row in ReportRegisterRow.objects.all():
        assert row.payload == incoming[(row.sheet_name, row.row_number)]
        assert row.review_status == "PENDING" and row.ownership == row.test_target == "UNKNOWN"
        assert (
            row.is_lab_accredited
            is row.is_official_certification
            is row.original_report_verified
            is None
        )
        assert row.payload["review"]["original_report_verified"] is False
    assert ReportRegisterRow.objects.count() == 3  # All have the same report number.


def test_reapply_keeps_manual_review_state_timestamps_and_display_name(case):
    apply(case)
    row = ReportRegisterRow.objects.first()
    row.review_status = "NEEDS_CONFIRMATION"
    row.ownership = "THIRD_PARTY"
    row.test_target = "MEDIA"
    row.is_lab_accredited = False
    row.original_report_verified = True
    row.save()
    before = snapshot()
    result = apply(case)
    assert result["created_rows"] == result["created_versions"] == 0
    assert result["reused_rows"] == 3
    assert snapshot() == before
    renamed = case[0].with_name("renamed.xlsx")
    case[0].rename(renamed)
    case[2]["file"]["name"] = renamed.name
    assert (
        staging.stage_filtech_reports(renamed, apply=True, expected_sha256=case[1])["reused_rows"]
        == 3
    )
    assert snapshot() == before


@pytest.mark.parametrize("kind", ["parser", "fingerprint", "payload", "missing_row", "extra_row"])
def test_conflicts_never_rewrite_or_repair_existing_version(case, monkeypatch, kind):
    apply(case)
    before = snapshot()
    if kind == "parser":
        monkeypatch.setattr(staging.report_preview, "PARSER_VERSION", "different-reader")
    elif kind == "fingerprint":
        original = staging.parser_provenance()
        original["dependencies"]["openpyxl"] = "different"
        monkeypatch.setattr(staging, "parser_provenance", lambda: original)
    elif kind == "payload":
        case[2]["sheets"][0]["records"][0]["future_key"] = ["changed"]
    elif kind == "missing_row":
        ReportRegisterRow.objects.first().delete()
        before = snapshot()
    else:
        extra = deepcopy(case[2]["sheets"][0]["records"][0])
        extra["source"]["row"] = 9
        extra["fields"]["report_no"]["requested_cell"] = "C9"
        case[2]["sheets"][0]["records"].append(extra)
        case[2]["sheets"][0]["record_count"] += 1
    with pytest.raises(staging.StagingConflict):
        apply(case)
    assert snapshot() == before


@pytest.mark.parametrize(
    "bad",
    [
        "source",
        "fields",
        "review",
        "warnings",
        "unmapped_cells",
        "source_sha",
        "source_row",
        "duplicate",
        "json",
        "cell",
    ],
)
def test_invalid_preview_is_rejected_before_writes(case, bad):
    sheet = case[2]["sheets"][0]
    row = sheet["records"][0]
    if bad in {"source", "fields", "review"}:
        row[bad] = {}
    elif bad in {"warnings", "unmapped_cells"}:
        row.pop(bad)
    elif bad == "source_sha":
        row["source"]["file_sha256"] = "b" * 64
    elif bad == "source_row":
        row["source"]["row"] = True
    elif bad == "duplicate":
        sheet["records"].append(deepcopy(row))
        sheet["record_count"] += 1
    elif bad == "json":
        row["future_key"] = float("nan")
    else:
        row["fields"]["report_no"].pop("raw_value")
    with pytest.raises(staging.StagingError):
        apply(case)
    assert snapshot() == {"versions": [], "rows": []}


def test_mid_file_failure_rolls_back_version_and_preceding_rows(case, monkeypatch):
    original = ReportRegisterRow.save

    def fail_second(row, *args, **kwargs):
        if row.sheet_name == "성능" and row.row_number == 5:
            raise RuntimeError("synthetic failure")
        return original(row, *args, **kwargs)

    monkeypatch.setattr(ReportRegisterRow, "save", fail_second)
    with pytest.raises(RuntimeError, match="synthetic failure"):
        apply(case)
    assert snapshot() == {"versions": [], "rows": []}


def test_expected_sha_and_source_changes_are_blocked(case, monkeypatch):
    with pytest.raises(staging.StagingError, match="required"):
        staging.stage_filtech_reports(case[0], apply=True)
    with pytest.raises(staging.StagingError, match="mismatch"):
        staging.stage_filtech_reports(case[0], apply=True, expected_sha256="b" * 64)
    hashes = iter([case[1], case[1], case[1], "b" * 64])
    monkeypatch.setattr(staging, "_file_sha256", lambda _: next(hashes))
    with pytest.raises(staging.StagingError, match="source_changed"):
        apply(case)
    assert snapshot() == {"versions": [], "rows": []}


def test_real_reader_synthetic_workbook_roundtrip(register):
    sha = hashlib.sha256(register.read_bytes()).hexdigest()
    assert (
        staging.stage_filtech_reports(register, apply=True, expected_sha256=sha)["created_rows"]
        == 4
    )
    preview = staging.report_preview.preview_filtech_reports(register)
    expected = {(s["name"], r["source"]["row"]): r for s in preview["sheets"] for r in s["records"]}
    assert {
        (r.sheet_name, r.row_number): r.payload for r in ReportRegisterRow.objects.all()
    } == expected


def test_command_summary_only_and_no_formal_records_or_llm(case, monkeypatch):
    provider = Mock(side_effect=AssertionError("No LLM"))
    monkeypatch.setattr("apps.llm.services.get_provider_class", provider)
    formal = (Company, Product, TestReport, Certificate, DeliveryRecord, LLMCallLog)
    before = {m: list(m.objects.values()) for m in formal}
    stdout = io.StringIO()
    call_command("stage_filtech_reports", str(case[0]), stdout=stdout)
    assert json.loads(stdout.getvalue())["mode"] == "DRY_RUN"
    assert not ReportRegisterVersion.objects.exists()
    stdout = io.StringIO()
    call_command(
        "stage_filtech_reports", str(case[0]), apply=True, expected_sha256=case[1], stdout=stdout
    )
    assert "SYNTHETIC-ONLY" not in stdout.getvalue()
    assert {m: list(m.objects.values()) for m in formal} == before
    case[2]["sheets"][0]["records"][0]["future_key"] = ["PRIVATE RAW VALUE"]
    with pytest.raises(CommandError) as error:
        call_command("stage_filtech_reports", str(case[0]), apply=True, expected_sha256=case[1])
    assert "PRIVATE RAW VALUE" not in str(error.value)
    provider.assert_not_called()


@pytest.mark.django_db(transaction=True)
def test_concurrent_same_sha_imports_create_one_complete_version(case):
    barrier = Barrier(2)

    def worker():
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            return apply(case)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: worker(), range(2)))
    assert sum(r["created_versions"] for r in results) == 1
    assert sum(r["created_rows"] for r in results) == 3
    assert sum(r["reused_rows"] for r in results) == 3
    assert ReportRegisterVersion.objects.count() == 1 and ReportRegisterRow.objects.count() == 3
