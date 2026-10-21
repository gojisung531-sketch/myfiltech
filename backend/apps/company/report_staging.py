"""Explicit, atomic staging of B1 rows. Never imports mapping, evaluation or LLM code."""

import hashlib
import json
import re
from copy import deepcopy
from pathlib import Path

import openpyxl
from django.core.exceptions import ValidationError
from django.db import DatabaseError, IntegrityError, connection, transaction
from openpyxl.utils.cell import coordinate_to_tuple

from apps.core import units

from . import report_preview
from .models import ReportRegisterRow, ReportRegisterVersion


class StagingError(ValueError):
    """Only safe codes/counts, never raw corporate values or database exceptions."""

    def __init__(self, code):
        self.code = code
        super().__init__(f"검토 대기 적재를 중단했습니다({code}). 자료는 저장하지 않았습니다.")


class StagingConflict(StagingError):
    def __init__(self, code, count=1):
        self.code, self.count = code, count
        ValueError.__init__(
            self, f"검토 대기 충돌({code}, {count}건). 기존 기록은 변경하지 않았습니다."
        )


def _file_sha256(path):
    try:
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()
    except OSError:
        raise StagingError("source_unreadable") from None


def _assert_unchanged(path, sha256):
    if _file_sha256(path) != sha256:
        raise StagingError("source_changed")


def parser_provenance():
    files = {
        "apps/company/report_preview.py": Path(report_preview.__file__),
        "apps/core/units.py": Path(units.__file__),
    }
    # Git checkout line endings do not change the meaning of the reader.
    fingerprints = {
        name: hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        for name, path in files.items()
    }
    return {
        "version": report_preview.PARSER_VERSION,
        "source_sha256": fingerprints,
        "dependencies": {"openpyxl": openpyxl.__version__},
    }


def _valid_cell(address):
    if not isinstance(address, str) or not re.fullmatch(r"[A-Z]{1,3}[1-9][0-9]*", address):
        return False
    row, col = coordinate_to_tuple(address)
    return 1 <= row <= 1048576 and 1 <= col <= 16384


def _validate_evidence(value):
    keys = {
        "cell",
        "raw_value",
        "xml_value",
        "value",
        "value_type",
        "number_format",
        "formula",
        "cached_value",
    }
    if not isinstance(value, dict) or not keys <= value.keys() or not _valid_cell(value["cell"]):
        raise StagingError("invalid_cell_evidence")
    if not isinstance(value["number_format"], str):
        raise StagingError("invalid_cell_format")
    formula = value["formula"]
    if formula is not None and (
        not isinstance(formula, dict)
        or not {"text", "attributes"} <= formula.keys()
        or not isinstance(formula["attributes"], dict)
        or formula["text"] is not None
        and not isinstance(formula["text"], str)
    ):
        raise StagingError("invalid_formula_evidence")


def _validate_preview(preview, sha256):
    try:
        encoded = json.dumps(preview, ensure_ascii=False, allow_nan=False)
        if json.loads(encoded) != preview:
            raise StagingError("lossy_json_payload")
    except (TypeError, ValueError, OverflowError):
        raise StagingError("invalid_json_payload") from None
    if not isinstance(preview, dict) or not isinstance(preview.get("file"), dict):
        raise StagingError("invalid_preview")
    if preview["file"].get("sha256") != sha256 or preview.get("mode") != "READ_ONLY_PREVIEW":
        raise StagingError("preview_sha_or_mode_mismatch")
    if not isinstance(preview["file"].get("name"), str) or not preview["file"]["name"].strip():
        raise StagingError("missing_file_name")
    sheets = preview.get("sheets")
    if not isinstance(sheets, list) or not sheets:
        raise StagingError("missing_sheets")
    rows, names = {}, set()
    for sheet in sheets:
        if not isinstance(sheet, dict) or sheet.get("name") not in {"성능", "재질"}:
            raise StagingError("unsupported_sheet")
        name = sheet["name"]
        if name in names:
            raise StagingError("duplicate_sheet")
        names.add(name)
        records = sheet.get("records")
        if (
            not isinstance(records, list)
            or type(sheet.get("record_count")) is not int
            or sheet["record_count"] != len(records)
        ):
            raise StagingError("record_count_mismatch")
        for record in records:
            if not isinstance(record, dict):
                raise StagingError("invalid_row")
            source, fields = record.get("source"), record.get("fields")
            if (
                not isinstance(source, dict)
                or not source
                or not isinstance(fields, dict)
                or not fields
            ):
                raise StagingError("missing_source_or_fields")
            number = source.get("row")
            if (
                source.get("file_sha256") != sha256
                or source.get("sheet") != name
                or type(number) is not int
                or not 1 <= number <= 1048576
            ):
                raise StagingError("invalid_source_coordinate")
            coordinate = (name, number)
            if coordinate in rows:
                raise StagingError("duplicate_source_coordinate")
            for field_name, field in fields.items():
                if not isinstance(field_name, str) or not field_name:
                    raise StagingError("invalid_field_name")
                _validate_evidence(field)
                if (
                    not {"requested_cell", "merged_range", "headers", "normalized"} <= field.keys()
                    or not _valid_cell(field["requested_cell"])
                    or coordinate_to_tuple(field["requested_cell"])[0] != number
                ):
                    raise StagingError("invalid_field_coordinate")
                if (
                    not isinstance(field["headers"], list)
                    or field["normalized"] is not None
                    and not isinstance(field["normalized"], dict)
                ):
                    raise StagingError("invalid_field_structure")
                for header in field["headers"]:
                    _validate_evidence(header)
                if "unit" in field:
                    _validate_evidence(field["unit"])
            for key in ("unmapped_cells", "warnings"):
                if not isinstance(record.get(key), list):
                    raise StagingError("missing_row_structure")
            for cell in record["unmapped_cells"]:
                _validate_evidence(cell)
            if not all(
                isinstance(w, dict) and isinstance(w.get("code"), str) for w in record["warnings"]
            ):
                raise StagingError("invalid_warnings")
            if not isinstance(record.get("review"), dict) or not record["review"]:
                raise StagingError("missing_review")
            rows[coordinate] = record  # Keep the original object, including unknown keys.
    if not rows:
        raise StagingError("empty_register")
    return rows


def _metadata(preview):
    keys = {
        "name",
        "declared_dimension",
        "merged_ranges",
        "stored_cell_count",
        "record_count",
        "report_number_anchor_count",
        "model_present_count",
        "missing",
        "warnings",
        "sheet_warnings",
    }
    return {
        "file": deepcopy(preview["file"]),
        "parser": parser_provenance(),
        "limitations": deepcopy(preview.get("limitations", [])),
        "sheets": [
            {
                **{k: deepcopy(v) for k, v in s.items() if k in keys},
                "duplicate_entry_number_groups": len(s.get("duplicate_entry_numbers", [])),
            }
            for s in preview["sheets"]
        ],
        "duplicate_report_number_groups": len(preview.get("duplicate_report_numbers", [])),
    }


def _compare_existing(version, rows, metadata, *, lock=False):
    if (
        version.parser_version != report_preview.PARSER_VERSION
        or version.source_metadata.get("parser") != metadata["parser"]
    ):
        raise StagingConflict("parser_mismatch")
    queryset = version.rows.all()
    if lock:
        queryset = queryset.select_for_update()
    stored = {(r.sheet_name, r.row_number): r for r in queryset}
    if stored.keys() != rows.keys():
        raise StagingConflict("coordinate_set_mismatch", len(stored.keys() ^ rows.keys()))
    changed = sum(stored[key].payload != payload for key, payload in rows.items())
    if changed:
        raise StagingConflict("payload_mismatch", changed)


def _summary(preview, version_id, *, apply, reused):
    count = sum(s["record_count"] for s in preview["sheets"])
    return {
        "mode": "APPLY" if apply else "DRY_RUN",
        "file_sha256": preview["file"]["sha256"],
        "parser_version": report_preview.PARSER_VERSION,
        "version_id": version_id,
        "sheet_counts": {s["name"]: s["record_count"] for s in preview["sheets"]},
        "created_versions": int(apply and not reused),
        "created_rows": count if apply and not reused else 0,
        "reused_versions": int(reused),
        "reused_rows": count if reused else 0,
        "would_create_versions": int(not apply and not reused),
        "would_create_rows": count if not apply and not reused else 0,
        "conflicts": 0,
    }


def stage_filtech_reports(path, *, apply=False, expected_sha256=None):
    """Default read-only plan; apply writes only staging tables in one transaction."""
    if apply and expected_sha256 is None:
        raise StagingError("expected_sha256_required")
    if expected_sha256 is not None and not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise StagingError("invalid_expected_sha256")
    path = Path(path).resolve()
    sha256 = _file_sha256(path)
    if expected_sha256 is not None and sha256 != expected_sha256:
        raise StagingError("expected_sha256_mismatch")
    try:
        preview = report_preview.preview_filtech_reports(path)
    except (report_preview.PreviewError, OSError, ValueError):
        raise StagingError("preview_failed") from None
    rows = _validate_preview(preview, sha256)
    metadata = _metadata(preview)
    _assert_unchanged(path, sha256)
    if not apply:
        existing = ReportRegisterVersion.objects.filter(sha256=sha256).first()
        if existing:
            _compare_existing(existing, rows, metadata)
        return _summary(
            preview, existing.pk if existing else None, apply=False, reused=existing is not None
        )
    if connection.vendor != "postgresql":
        raise StagingError("postgresql_required")
    try:
        with transaction.atomic():
            # Same-SHA CLI executions serialize, including when the version is absent.
            lock_key = int(sha256[:16], 16)
            if lock_key >= 2**63:
                lock_key -= 2**64
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(%s)", [lock_key])
            _assert_unchanged(path, sha256)
            existing = (
                ReportRegisterVersion.objects.select_for_update().filter(sha256=sha256).first()
            )
            if existing:
                _compare_existing(existing, rows, metadata, lock=True)
                _assert_unchanged(path, sha256)
                return _summary(preview, existing.pk, apply=True, reused=True)
            version = ReportRegisterVersion(
                sha256=sha256,
                display_name=preview["file"]["name"],
                parser_version=report_preview.PARSER_VERSION,
                source_metadata=metadata,
            )
            version.full_clean()
            version.save(force_insert=True)
            for (sheet, number), payload in rows.items():
                row = ReportRegisterRow(
                    file_version=version, sheet_name=sheet, row_number=number, payload=payload
                )
                row.full_clean()
                row.save(force_insert=True)
            _assert_unchanged(path, sha256)
            return _summary(preview, version.pk, apply=True, reused=False)
    except IntegrityError:
        raise StagingConflict("database_constraint") from None
    except ValidationError:
        raise StagingError("model_validation_failed") from None
    except DatabaseError:
        raise StagingError("database_operation_failed") from None
