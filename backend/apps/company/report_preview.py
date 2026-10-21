"""Read-only, sparse preview of the Filtech report register, never an ORM importer.

This intentionally supports the two observed register layouts, not arbitrary Excel
tables. Cell evidence is register evidence, not verification of a report PDF.
"""

import hashlib
import math
import posixpath
import re
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

from openpyxl.styles.numbers import BUILTIN_FORMATS, is_date_format
from openpyxl.utils.cell import coordinate_to_tuple, range_boundaries
from openpyxl.utils.datetime import MAC_EPOCH, WINDOWS_EPOCH, from_excel

from apps.core.units import to_m3h, to_pa

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"

# (source column, semantic field, adjacent unit column). No product mapping.
PERFORMANCE = [
    ("A", "entry_no", None),
    ("B", "issue_date", None),
    ("C", "report_no", None),
    ("D", "lab_name", None),
    ("E", "customer", None),
    ("F", "use", None),
    ("G", "filter_construction", None),
    ("H", "sample_dimension", None),
    ("I", "test_standard", None),
    ("J", "model", None),
    ("K", "media_material", None),
    ("L", "media_grammage", "M"),
    ("N", "media_thickness", "O"),
    ("P", "media_mpps_efficiency", "Q"),
    ("R", "media_air_permeability_tds", "S"),
    ("T", "media_air_permeability_lab", "U"),
    ("V", "media_pressure_drop_tds", "W"),
    ("X", "media_pressure_drop_lab", "Y"),
    ("Z", "pleat_height", "AA"),
    ("AB", "pleat_count", "AC"),
    ("AD", "pleat_width", "AE"),
    ("AF", "pack_count", "AG"),
    ("AH", "airflow", "AI"),
    ("AJ", "filtration_area", "AK"),
    ("AL", "filtration_velocity", "AM"),
    ("AN", "result_class", None),
    ("AO", "ashrae_e1", None),
    ("AP", "ashrae_e2", None),
    ("AQ", "ashrae_e3", None),
    ("AR", "initial_dp", "AS"),
    ("AT", "final_dp", "AU"),
    ("AV", "dust_holding_capacity", "AW"),
    ("AX", "en779_initial_arrestance", None),
    ("AY", "en779_average_arrestance", None),
    ("AZ", "en779_initial_efficiency", None),
    ("BA", "en779_average_efficiency", None),
    ("BB", "en1822_element_mpps_efficiency", None),
    ("BC", "en1822_element_minimum_efficiency", None),
    ("BD", "en1822_media_untreated_efficiency", None),
    ("BE", "en1822_media_discharged_efficiency", None),
    ("BF", "mpps_size", "BG"),
    ("BH", "notes", None),
]
MATERIAL = [
    ("B", "entry_no", None),
    ("C", "issue_date", None),
    ("D", "lab_name", None),
    ("E", "report_no", None),
    ("F", "sample_name", None),
    ("G", "sample_dimension", None),
    ("H", "test_standard", None),
    ("I", "result_class", None),
    ("J", "use", None),
    ("K", "notes", None),
    ("L", "material", None),
    ("M", "burst_strength", None),
    ("N", "mass_per_area", None),
    ("O", "thickness", None),
    ("P", "air_permeability", None),
    ("Q", "water_repellency_grade", None),
]
EFFICIENCIES = {name for _, name, _ in PERFORMANCE if "efficiency" in name} | {
    "ashrae_e1",
    "ashrae_e2",
    "ashrae_e3",
    "en779_initial_arrestance",
    "en779_average_arrestance",
}
MATERIAL_UNITS = {"M": "kPa", "N": "g/m²", "O": "mm", "P": "mm/s", "Q": "급"}


class PreviewError(ValueError):
    """The register cannot be interpreted without guessing its layout or values."""


def _json_value(value):
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, timedelta):
        return {"seconds": value.total_seconds(), "type": "duration"}
    return value


def _cell(element, strings, formats, epoch):
    address = element.get("r")
    kind = element.get("t", "n")
    style = int(element.get("s", "0"))
    number_format = formats[style]
    xml_value = element.findtext(NS + "v")
    formula_element = element.find(NS + "f")
    formula = None
    if formula_element is not None:
        formula = {"text": formula_element.text, "attributes": dict(formula_element.attrib)}
    value = xml_value if xml_value != "" else None
    if kind == "s" and value is not None:
        value = strings[int(xml_value)]
    elif kind == "inlineStr":
        value = "".join(t.text or "" for t in element.findall(".//" + NS + "t"))
    elif kind == "b" and value is not None:
        value = xml_value == "1"
    elif kind == "n" and value is not None:
        value = float(xml_value)
        if not math.isfinite(value):
            raise PreviewError("유한하지 않은 수치 셀이 있습니다.")
        if value.is_integer():
            value = int(value)
    raw_value = value
    value_type = kind
    if kind == "n" and value is not None and is_date_format(number_format):
        value = from_excel(value, epoch)
        value_type = type(value).__name__
    return {
        "cell": address,
        "raw_value": raw_value,
        "xml_value": xml_value,
        "value": _json_value(value),
        "value_type": value_type,
        "number_format": number_format,
        "formula": formula,
        "cached_value": _json_value(value) if formula is not None else None,
    }


def _sparse_sheet(archive, member, strings, formats, epoch):
    cells, merges, declared_dimension = {}, [], None
    stored_cells = 0
    sheet_data = None
    with archive.open(member) as stream:
        for event, element in ET.iterparse(stream, events=("start", "end")):
            if event == "start":
                if element.tag == NS + "sheetData":
                    sheet_data = element
                continue
            if element.tag == NS + "dimension":
                declared_dimension = element.get("ref")
            elif element.tag == NS + "row":
                for item in element.findall(NS + "c"):
                    cell = _cell(item, strings, formats, epoch)
                    cells[cell["cell"]] = cell
                    stored_cells += 1
                element.clear()
                if sheet_data is not None:
                    sheet_data.clear()
            elif element.tag == NS + "mergeCell":
                merges.append(element.get("ref"))
    shared_sources = {
        cell["formula"]["attributes"].get("si"): address
        for address, cell in cells.items()
        if cell["formula"] is not None
        and cell["formula"]["attributes"].get("t") == "shared"
        and cell["formula"]["text"] is not None
    }
    for cell in cells.values():
        formula = cell["formula"]
        if formula is not None and formula["attributes"].get("t") == "shared":
            formula["shared_source_cell"] = shared_sources.get(formula["attributes"].get("si"))
    return cells, merges, declared_dimension, stored_cells


def _has_value(cell):
    return (
        cell["value"] is not None
        and str(cell["value"]).strip() != ""
        or cell["formula"] is not None
    )


def _evidence(cells, merges, address):
    row, col = coordinate_to_tuple(address)
    anchor, merged_range = address, None
    for merged in merges:
        left, top, right, bottom = range_boundaries(merged)
        if left <= col <= right and top <= row <= bottom:
            anchor, merged_range = merged.split(":")[0], merged
            break
    cell = dict(
        cells.get(
            anchor,
            {
                "cell": anchor,
                "raw_value": None,
                "xml_value": None,
                "value": None,
                "value_type": "n",
                "number_format": "General",
                "formula": None,
                "cached_value": None,
            },
        )
    )
    cell.update(requested_cell=address, merged_range=merged_range)
    return cell


def _warning(record, code, field, cell):
    record["warnings"].append({"code": code, "field": field, "cell": cell})


def _percent_format(number_format):
    # Excel's escaped/quoted literal percent signs do not scale the stored number.
    return "%" in re.sub(r'"[^"]*"|\\.', "", number_format)


def _normalize(record, name, field):
    value = field["value"]
    unit = field.get("unit", {}).get("value")
    field["normalized"] = None
    if value is None or str(value).strip() == "":
        return
    numeric = isinstance(value, (int, float)) and not isinstance(value, bool)
    if name in EFFICIENCIES:
        if not numeric:
            _warning(record, "non_numeric_efficiency", name, field["cell"])
        elif _percent_format(field["number_format"]):
            if 0 <= value <= 1:
                field["normalized"] = {
                    "value": value * 100,
                    "unit": "%",
                    "formula": "value * 100 (Excel percent format)",
                }
            else:
                _warning(record, "percent_out_of_range", name, field["cell"])
        elif unit == "%" and 1 < value <= 100:
            field["normalized"] = {
                "value": value,
                "unit": "%",
                "formula": "value (explicit percent unit)",
            }
        else:
            _warning(record, "ambiguous_percent_scale", name, field["cell"])
    elif name in {"airflow", "initial_dp", "final_dp"}:
        if not numeric:
            _warning(record, "non_numeric_measurement", name, field["cell"])
            return
        if value < 0:
            _warning(record, "negative_measurement", name, field["cell"])
            return
        if not unit:
            _warning(record, "missing_unit", name, field["cell"])
            return
        try:
            converter, target = (to_m3h, "m³/h") if name == "airflow" else (to_pa, "Pa")
            factor = converter(1, str(unit))
            field["normalized"] = {
                "value": value * factor,
                "unit": target,
                "formula": f"value * {factor}",
            }
        except KeyError:
            _warning(record, "unsupported_unit", name, field["cell"])
    elif name in {"media_pressure_drop_tds", "media_pressure_drop_lab"}:
        # Compound labels contain different test conditions. Do not strip them.
        _warning(record, "conditioned_unit_not_normalized", name, field["cell"])


def _records(sheet, cells, merges, sha256):
    performance = sheet == "성능"
    specs, header_end = (PERFORMANCE, 3) if performance else (MATERIAL, 2)
    expected = (
        {
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
        }
        if performance
        else {
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
        }
    )
    if any(
        _evidence(cells, merges, address)["value"] != text for address, text in expected.items()
    ):
        raise PreviewError("관리대장 헤더가 지원하는 배치와 다릅니다. 원본 구조를 확인하세요.")
    data_rows = sorted(
        {
            coordinate_to_tuple(address)[0]
            for address, cell in cells.items()
            if coordinate_to_tuple(address)[0] > header_end and _has_value(cell)
        }
    )
    records = []
    for row in data_rows:
        record = {
            "source": {"file_sha256": sha256, "sheet": sheet, "row": row},
            "fields": {},
            "unmapped_cells": [],
            "warnings": [],
            "review": {
                "ownership": "UNKNOWN",
                "test_target": "UNKNOWN",
                "product_link": "NOT_ATTEMPTED",
                "lab_accreditation": None,
                "is_official_certification": None,
                "original_report_verified": False,
            },
        }
        consumed = set()
        for col, name, unit_col in specs:
            address = f"{col}{row}"
            field = _evidence(cells, merges, address)
            consumed.add(address)
            headers = [_evidence(cells, merges, f"{col}{r}") for r in range(1, header_end + 1)]
            field["headers"] = list({h["cell"]: h for h in headers if _has_value(h)}.values())
            if unit_col:
                field["unit"] = _evidence(cells, merges, f"{unit_col}{row}")
                consumed.add(f"{unit_col}{row}")
            elif not performance and col in MATERIAL_UNITS:
                header = _evidence(cells, merges, f"{col}2")
                field["unit"] = {**header, "value": MATERIAL_UNITS[col], "origin": "header"}
            _normalize(record, name, field)
            record["fields"][name] = field
            if field["formula"] is not None and field["value"] is None:
                _warning(record, "formula_cache_missing", name, field["cell"])
            elif field["formula"] is not None:
                _warning(record, "formula_cached_unverified", name, field["cell"])
            if field["value_type"] == "e":
                _warning(record, "excel_error", name, field["cell"])
        for name in ("report_no", "issue_date", "lab_name", "test_standard") + (
            ("model", "airflow", "initial_dp") if performance else ()
        ):
            field = record["fields"][name]
            if field["value"] is None or str(field["value"]).strip() == "":
                _warning(record, "missing_value", name, field["cell"])
        issued = record["fields"]["issue_date"]
        if issued["value"] is not None and issued["value_type"] not in {"datetime", "date", "d"}:
            _warning(record, "unparsed_issue_date", "issue_date", issued["cell"])
        if performance and not any(_has_value(record["fields"][name]) for name in EFFICIENCIES):
            _warning(record, "missing_efficiency_results", None, None)
        for address, cell in cells.items():
            if (
                coordinate_to_tuple(address)[0] == row
                and address not in consumed
                and _has_value(cell)
            ):
                record["unmapped_cells"].append(cell)
                _warning(record, "unmapped_cell", None, address)
        records.append(record)
    return records


def preview_filtech_reports(path: str | Path) -> dict:
    """Return JSON-compatible cell evidence. No DB, network, LLM or workbook writes."""
    path = Path(path).resolve()
    if path.suffix.lower() != ".xlsx":
        raise PreviewError("XLSX 관리대장만 지원합니다.")
    with path.open("rb") as stream:
        sha256 = hashlib.file_digest(stream, "sha256").hexdigest()
    result = {
        "file": {"name": path.name, "sha256": sha256},
        "mode": "READ_ONLY_PREVIEW",
        "limitations": [
            "관리대장 셀은 원본 성적서 PDF 근거를 대신하지 않습니다.",
            "소유·용도·시험대상·공인시험·공식인증 여부는 확정하지 않습니다.",
            "SHEET/Model은 당사 완제품 모델로 간주하지 않습니다.",
            "수식 캐시는 재계산하거나 검증하지 않습니다.",
        ],
        "sheets": [],
        "duplicate_report_numbers": [],
    }
    try:
        with ZipFile(path) as archive:
            workbook = ET.fromstring(archive.read("xl/workbook.xml"))
            properties = workbook.find(NS + "workbookPr")
            epoch = (
                MAC_EPOCH
                if properties is not None and properties.get("date1904") in {"1", "true"}
                else WINDOWS_EPOCH
            )
            result["file"]["date_system"] = "1904" if epoch == MAC_EPOCH else "1900"
            rels = {
                e.get("Id"): e.get("Target")
                for e in ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            }
            strings = []
            if "xl/sharedStrings.xml" in archive.namelist():
                with archive.open("xl/sharedStrings.xml") as stream:
                    for _, element in ET.iterparse(stream):
                        if element.tag == NS + "si":
                            strings.append("".join(t.text or "" for t in element.iter(NS + "t")))
                            element.clear()
            styles = ET.fromstring(archive.read("xl/styles.xml"))
            custom_formats = {
                int(e.get("numFmtId")): e.get("formatCode")
                for e in styles.findall(NS + "numFmts/" + NS + "numFmt")
            }
            formats = [
                custom_formats.get(
                    int(e.get("numFmtId", "0")),
                    BUILTIN_FORMATS.get(int(e.get("numFmtId", "0")), "General"),
                )
                for e in styles.find(NS + "cellXfs")
            ]
            for sheet in workbook.find(NS + "sheets"):
                name = sheet.get("name")
                target = rels[sheet.get(REL)]
                member = posixpath.normpath(
                    target.lstrip("/") if target.startswith("/") else "xl/" + target
                )
                cells, merges, dimension, stored = _sparse_sheet(
                    archive, member, strings, formats, epoch
                )
                records = _records(name, cells, merges, sha256) if name in {"성능", "재질"} else []
                counts = Counter(w["code"] for r in records for w in r["warnings"])
                missing = Counter(
                    w["field"]
                    for r in records
                    for w in r["warnings"]
                    if w["code"] == "missing_value"
                )
                result["sheets"].append(
                    {
                        "name": name,
                        "declared_dimension": dimension,
                        "merged_ranges": merges,
                        "stored_cell_count": stored,
                        "record_count": len(records),
                        "report_number_anchor_count": len(
                            {
                                r["fields"]["report_no"]["cell"]
                                for r in records
                                if r["fields"]["report_no"]["value"] is not None
                            }
                        ),
                        "model_present_count": sum(
                            bool(r["fields"].get("model", {}).get("value")) for r in records
                        ),
                        "missing": dict(missing),
                        "warnings": dict(counts),
                        "sheet_warnings": (
                            ["ownership_and_test_target_unverified"]
                            + (
                                ["model_column_absent"]
                                if name == "재질"
                                else ["sheet_model_not_verified_product"]
                            )
                            if name in {"성능", "재질"}
                            else ["unsupported_sheet"]
                        ),
                        "records": records,
                    }
                )
    except PreviewError:
        raise
    except (
        BadZipFile,
        ET.ParseError,
        KeyError,
        IndexError,
        TypeError,
        OverflowError,
        ValueError,
        AttributeError,
    ) as exc:
        raise PreviewError("XLSX 구조 또는 셀 값을 읽을 수 없습니다.") from exc
    groups = defaultdict(list)
    for sheet in result["sheets"]:
        for record in sheet["records"]:
            field = record["fields"]["report_no"]
            if field["value"] is not None and str(field["value"]).strip():
                groups[str(field["value"]).strip()].append(record)
    for number, records in groups.items():
        if len(records) > 1:
            result["duplicate_report_numbers"].append(
                {
                    "report_no": number,
                    "occurrences": [
                        {**r["source"], "cell": r["fields"]["report_no"]["cell"]} for r in records
                    ],
                }
            )
            for record in records:
                _warning(
                    record,
                    "duplicate_report_no",
                    "report_no",
                    record["fields"]["report_no"]["cell"],
                )
    for sheet in result["sheets"]:
        entry_groups = defaultdict(list)
        for record in sheet["records"]:
            field = record["fields"]["entry_no"]
            if _has_value(field):
                entry_groups[str(field["value"]).strip()].append(record)
        sheet["duplicate_entry_numbers"] = []
        for number, records in entry_groups.items():
            if len(records) > 1:
                sheet["duplicate_entry_numbers"].append(
                    {
                        "entry_no": number,
                        "occurrences": [
                            {**r["source"], "cell": r["fields"]["entry_no"]["cell"]}
                            for r in records
                        ],
                    }
                )
                for record in records:
                    _warning(
                        record,
                        "duplicate_entry_no",
                        "entry_no",
                        record["fields"]["entry_no"]["cell"],
                    )
        sheet["warnings"] = dict(
            Counter(w["code"] for r in sheet["records"] for w in r["warnings"])
        )
    with path.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != sha256:
            raise PreviewError("읽는 동안 원본 파일이 변경되었습니다. 다시 확인하세요.")
    return result
