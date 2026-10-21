"""Synthetic boundary inputs only; no company workbook or product fixtures."""

import hashlib
import io
import json
from datetime import datetime
from unittest.mock import Mock
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import openpyxl
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from openpyxl.utils.datetime import MAC_EPOCH, to_excel

from apps.company.report_preview import NS, PreviewError, preview_filtech_reports


@pytest.fixture
def register(tmp_path):
    """A tiny layout with two rows per sheet and ambiguous measurements."""
    path = tmp_path / "boundary-input.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "성능"
    headers = {
        "A2": "No.",
        "B2": "Issue date",
        "C2": "Report No.",
        "D2": "Laboratoy",
        "I2": "Test Standard",
        "J2": "Model",
        "AH2": "Air Flow Rate",
        "AR2": "Initial Pressrue",
        "AT2": "Final Pressure",
        "AO3": "E1",
        "AP3": "E2",
        "AQ3": "E3",
        "BB2": "Eff. at MPPS",
        "BC2": "Eff.95%min at MPPS",
        "P2": "MPPS Efficiency",
        "V2": "Pressure Drop (TDS)",
    }
    for cell, value in headers.items():
        ws[cell] = value
    ws["J1"] = "SHEET"
    ws.merge_cells("J1:Y1")
    for cell, value in {
        "A4": 1,
        "B4": datetime(2024, 2, 29),
        "C4": "BOUNDARY-ONLY",
        "D4": "Test lab",
        "I4": "TEST STANDARD",
        "J4": "TEST MEDIA",
        "AH4": 2,
        "AI4": "m3/min",
        "AR4": 3,
        "AS4": "mmAq",
        "AL4": "=AH4/2",
        "AO4": 0.95,
        "AP4": 95,
        "AQ4": 0.5,
        "P4": 0.8,
        "Q4": "%",
        "BB4": 0,
        "BC4": "=0.95",
        "V4": 12,
        "W4": "Pa@5cm/s",
        "BJ4": "unmapped annotation",
        "A7": 2,
        "AH7": 0,
        "AI7": "m3/h",
        "AR7": False,
    }.items():
        ws[cell] = value
    for cell in ("AO4", "AP4", "BB4"):
        ws[cell].number_format = "0.0%"
    ws["AQ4"].number_format = r"0.0\%"
    ws["BC4"].number_format = "0.00%"
    material = wb.create_sheet("재질")
    for cell, value in {
        "B2": "No.",
        "C2": "발급일자",
        "D2": "시험기관명",
        "E2": "발급번호",
        "F2": "시료명",
        "H2": "시험규격",
        "M2": "파열강도(kPa)",
        "N2": "질량(g/m²)",
        "O2": "두께(mm)",
        "P2": "공기투과도(mm/s)",
        "Q2": "발수도(급)",
        "B3": 1,
        "C3": datetime(2024, 1, 1),
        "D3": "Test lab",
        "E3": "BOUNDARY-ONLY",
        "F3": "Sample A",
        "F4": "Sample B",
        "O4": 0.6,
        "S3": "extra annotation",
    }.items():
        material[cell] = value
    for col in ("B", "C", "D", "E"):
        material.merge_cells(f"{col}3:{col}4")
    wb.save(path)
    wb.close()
    # Stored cells only, with a misleading maximum dimension and one style-only row.
    _patch_sheet(path, lambda root: _large_dimension_and_cache(root))
    return path


def _patch_sheet(path, change):
    with ZipFile(path) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    root = ET.fromstring(members["xl/worksheets/sheet1.xml"])
    change(root)
    members["xl/worksheets/sheet1.xml"] = ET.tostring(root)
    with ZipFile(path, "w") as archive:
        for name, value in members.items():
            archive.writestr(name, value)


def _large_dimension_and_cache(root):
    root.find(NS + "dimension").set("ref", "A1:BS1048576")
    data = root.find(NS + "sheetData")
    last = ET.SubElement(data, NS + "row", r="1048576")
    ET.SubElement(last, NS + "c", r="BS1048576", s="0")
    cached = root.find(f".//{NS}c[@r='AL4']/{NS}v")
    cached.text = "1"


def test_sparse_rows_provenance_and_merges(register, monkeypatch):
    before = hashlib.sha256(register.read_bytes()).hexdigest()
    monkeypatch.setattr(
        openpyxl, "load_workbook", Mock(side_effect=AssertionError("No dense loader"))
    )
    result = preview_filtech_reports(register)
    assert result["file"]["sha256"] == before == hashlib.sha256(register.read_bytes()).hexdigest()
    performance, material = result["sheets"]
    assert performance["declared_dimension"] == "A1:BS1048576"
    assert performance["stored_cell_count"] < 100
    assert [r["source"]["row"] for r in performance["records"]] == [4, 7]
    assert performance["model_present_count"] == 1
    first = performance["records"][0]
    assert first["source"] == {"file_sha256": before, "sheet": "성능", "row": 4}
    model = first["fields"]["model"]
    assert model["cell"] == "J4" and model["raw_value"] == "TEST MEDIA"
    assert [h["value"] for h in model["headers"]] == ["SHEET", "Model"]
    assert first["fields"]["issue_date"]["value"] == "2024-02-29T00:00:00"
    assert isinstance(first["fields"]["issue_date"]["raw_value"], int)
    assert first["unmapped_cells"][0]["cell"] == "BJ4"
    assert material["record_count"] == 2 and material["report_number_anchor_count"] == 1
    shared = material["records"][1]["fields"]["report_no"]
    assert (shared["requested_cell"], shared["cell"], shared["merged_range"]) == (
        "E4",
        "E3",
        "E3:E4",
    )
    assert shared["raw_value"] == "BOUNDARY-ONLY"
    assert material["records"][1]["fields"]["thickness"]["unit"]["cell"] == "O2"
    assert len(result["duplicate_report_numbers"]) == 1
    assert len(result["duplicate_report_numbers"][0]["occurrences"]) == 3
    assert len(material["duplicate_entry_numbers"]) == 1
    assert len(material["duplicate_entry_numbers"][0]["occurrences"]) == 2
    for sheet in result["sheets"]:
        for record in sheet["records"]:
            assert record["review"]["ownership"] == "UNKNOWN"
            assert record["review"]["test_target"] == "UNKNOWN"
            assert record["review"]["is_official_certification"] is None
            assert record["review"]["original_report_verified"] is False


def test_units_percent_scales_missing_and_formula_cache(register):
    sheet = preview_filtech_reports(register)["sheets"][0]
    first, missing = sheet["records"]
    fields = first["fields"]
    assert fields["airflow"]["normalized"]["value"] == 120
    assert fields["airflow"]["unit"]["cell"] == "AI4"
    assert fields["initial_dp"]["normalized"]["value"] == pytest.approx(29.41995)
    assert fields["ashrae_e1"]["raw_value"] == 0.95
    assert fields["ashrae_e1"]["normalized"]["value"] == 95
    assert fields["ashrae_e2"]["normalized"] is None  # 95 with % format is 9500%
    assert fields["ashrae_e3"]["normalized"] is None  # escaped percent is literal
    assert fields["media_mpps_efficiency"]["normalized"] is None  # .8 with unit % is ambiguous
    assert fields["en1822_element_mpps_efficiency"]["normalized"]["value"] == 0
    assert fields["en1822_element_minimum_efficiency"]["value"] is None
    assert fields["en1822_element_minimum_efficiency"]["formula"]["text"] == "0.95"
    assert fields["filtration_velocity"]["cached_value"] == 1
    assert fields["media_pressure_drop_tds"]["normalized"] is None
    codes = {w["code"] for w in first["warnings"]}
    assert {
        "ambiguous_percent_scale",
        "percent_out_of_range",
        "formula_cache_missing",
        "formula_cached_unverified",
        "conditioned_unit_not_normalized",
    } <= codes
    assert missing["fields"]["airflow"]["normalized"]["value"] == 0
    assert missing["fields"]["report_no"]["value"] is None
    assert missing["fields"]["initial_dp"]["normalized"] is None  # boolean is not pressure
    assert sheet["missing"]["report_no"] == sheet["missing"]["model"] == 1


@pytest.mark.parametrize(
    "value,unit,warning",
    [
        (10, "ft3/m", "unsupported_unit"),
        (10, None, "missing_unit"),
        (-1, "Pa", "negative_measurement"),
        ("<10", "Pa", "non_numeric_measurement"),
    ],
)
def test_uncertain_measurements_are_not_invented(register, value, unit, warning):
    def change(root):
        cell = root.find(f".//{NS}c[@r='AR4']")
        cell.clear()
        cell.set("r", "AR4")
        if isinstance(value, str):
            cell.set("t", "str")
        ET.SubElement(cell, NS + "v").text = str(value)
        unit_cell = root.find(f".//{NS}c[@r='AS4']")
        unit_cell.clear()
        unit_cell.set("r", "AS4")
        if unit:
            unit_cell.set("t", "str")
            ET.SubElement(unit_cell, NS + "v").text = unit

    _patch_sheet(register, change)
    record = preview_filtech_reports(register)["sheets"][0]["records"][0]
    assert record["fields"]["initial_dp"]["normalized"] is None
    assert any(w["code"] == warning and w["field"] == "initial_dp" for w in record["warnings"])


def test_1904_dates(register):
    with ZipFile(register) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    workbook = ET.fromstring(members["xl/workbook.xml"])
    workbook.find(NS + "workbookPr").set("date1904", "1")
    members["xl/workbook.xml"] = ET.tostring(workbook)
    with ZipFile(register, "w") as archive:
        for name, value in members.items():
            archive.writestr(name, value)

    def change(root):
        root.find(f".//{NS}c[@r='B4']/{NS}v").text = str(to_excel(datetime(2024, 2, 29), MAC_EPOCH))

    _patch_sheet(register, change)
    preview = preview_filtech_reports(register)
    assert preview["file"]["date_system"] == "1904"
    assert (
        preview["sheets"][0]["records"][0]["fields"]["issue_date"]["value"] == "2024-02-29T00:00:00"
    )


def test_shared_formulas_keep_anchor_and_cached_value(register):
    def change(root):
        anchor = root.find(f".//{NS}c[@r='AL4']/{NS}f")
        anchor.attrib.update(t="shared", si="0", ref="AL4:AL7")
        row = root.find(f".//{NS}row[@r='7']")
        follower = ET.SubElement(row, NS + "c", r="AL7")
        ET.SubElement(follower, NS + "f", t="shared", si="0")
        ET.SubElement(follower, NS + "v").text = "2"

    _patch_sheet(register, change)
    field = preview_filtech_reports(register)["sheets"][0]["records"][1]["fields"][
        "filtration_velocity"
    ]
    assert field["formula"]["shared_source_cell"] == "AL4"
    assert field["formula"]["text"] is None  # No invented or evaluated formula.
    assert field["cached_value"] == field["value"] == 2


def test_invalid_layout(tmp_path):
    path = tmp_path / "dates.xlsx"
    wb = openpyxl.Workbook()
    wb.active.title = "성능"
    wb.active["A2"] = "wrong layout"
    wb.save(path)
    with pytest.raises(PreviewError, match="헤더"):
        preview_filtech_reports(path)
    wb.close()


def test_command_is_db_free_summary_only_and_preserves_output(
    register, tmp_path, monkeypatch, django_db_blocker
):
    provider = Mock(side_effect=AssertionError("No LLM calls"))
    monkeypatch.setattr("apps.llm.services.get_provider_class", provider)
    output = tmp_path / "local-preview.json"
    stdout = io.StringIO()
    with django_db_blocker.block():
        call_command("preview_filtech_reports", str(register), output=str(output), stdout=stdout)
    summary = json.loads(stdout.getvalue())
    assert "BOUNDARY-ONLY" not in stdout.getvalue()
    assert "records" not in summary["sheets"][0]
    assert summary["sheets"][0]["record_count"] == 2
    assert json.loads(output.read_text(encoding="utf-8"))["mode"] == "READ_ONLY_PREVIEW"
    before = output.read_bytes()
    with pytest.raises(CommandError):
        call_command("preview_filtech_reports", str(register), output=str(output))
    assert output.read_bytes() == before
    with pytest.raises(CommandError, match="원본과 다른"):
        call_command("preview_filtech_reports", str(register), output=str(register))
    provider.assert_not_called()


def test_malformed_archive_and_numeric_cell(register, tmp_path):
    bad = tmp_path / "not-excel.xlsx"
    bad.write_bytes(b"invalid zip")
    with pytest.raises(PreviewError, match="읽을 수"):
        preview_filtech_reports(bad)

    def change(root):
        root.find(f".//{NS}c[@r='AH4']/{NS}v").text = "not-a-number"

    _patch_sheet(register, change)
    with pytest.raises(PreviewError, match="읽을 수"):
        preview_filtech_reports(register)
