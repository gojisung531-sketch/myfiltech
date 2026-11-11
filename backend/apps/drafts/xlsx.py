"""XLSX export of Compliance Matrix and checklist (specs/09 §6)."""

import math
import re
import unicodedata
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from apps.core.app_settings import get_setting

from .models import DraftType

XLSX_TYPES = (DraftType.COMPLIANCE_MATRIX, DraftType.BID_CHECKLIST)
VERDICT_COLORS = {"충족": "198754", "보완 필요": "FD7E14", "확인 필요": "0D6EFD"}
STATUS_LABELS = {"TODO": "미완료", "DONE": "완료", "NA": "해당 없음"}
CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

_thin = Side(style="thin", color="ADB5BD")
BORDER = Border(left=_thin, right=_thin, top=_thin, bottom=_thin)
HEAD_FILL = PatternFill("solid", fgColor="E9ECEF")
HIGH_FILL = PatternFill("solid", fgColor="DC3545")
WRAP = Alignment(wrap_text=True, vertical="top")


def safe_value(value):
    if not isinstance(value, str):
        return value
    value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", value)
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value


def _write(ws, row, column, value):
    return ws.cell(row=row, column=column, value=safe_value(value))


def _table(ws, start_row: int, columns: list[tuple[str, int]], rows: list[list]) -> int:
    ws.row_dimensions[start_row].height = 30
    for col, (label, width) in enumerate(columns, start=1):
        cell = _write(ws, start_row, col, label)
        cell.font = Font(name="맑은 고딕", size=10, bold=True)
        cell.fill = HEAD_FILL
        cell.border = BORDER
        cell.alignment = WRAP
        ws.column_dimensions[get_column_letter(col)].width = width
    for r, values in enumerate(rows, start=start_row + 1):
        for c, value in enumerate(values, start=1):
            cell = _write(ws, r, c, value)
            cell.font = Font(name="맑은 고딕", size=10)
            cell.border = BORDER
            cell.alignment = WRAP
        lines = []
        for value, (_, width) in zip(values, columns, strict=True):
            lengths = [
                sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in line)
                for line in str(value or "").splitlines() or [""]
            ]
            lines.append(sum(max(1, math.ceil(length / max(1, width - 2))) for length in lengths))
        ws.row_dimensions[r].height = min(409, max(28, max(lines, default=1) * 14 + 8))
    last = start_row + len(rows)
    ws.freeze_panes = ws.cell(row=start_row + 1, column=1)
    ws.auto_filter.ref = f"A{start_row}:{get_column_letter(len(columns))}{max(last, start_row)}"
    ws.sheet_view.showGridLines = False
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = f"{start_row}:{start_row}"
    return last


def _footer(ws, row: int, content: dict) -> None:
    _write(
        ws, row + 2, 1, content.get("notice") or get_setting("report.disclaimer") or ""
    ).font = Font(italic=True, color="6C757D", size=9)


def compliance_matrix_sheet(wb: Workbook, bid, content: dict) -> None:
    ws = wb.active
    ws.title = "Compliance Matrix"
    header = content.get("header") or {}
    meta = [
        ("공고", f"[{header.get('notice_no') or '-'}] {header.get('bid_title') or bid.title}"),
        ("수요기관", header.get("buyer_org") or "-"),
        (
            "작성",
            f"{header.get('company', '')} {header.get('prepared_by', '')} · {header.get('prepared_at', '')}",
        ),
    ]
    for r, (label, value) in enumerate(meta, start=1):
        ws.cell(row=r, column=1, value=label).font = Font(bold=True)
        _write(ws, r, 2, value).alignment = Alignment(wrap_text=False, vertical="center")
        ws.row_dimensions[r].height = 24
    columns = [
        ("No", 10), ("품목", 22), ("구분", 12), ("요구사항", 48), ("조항", 28),
        ("회사 값 / 미확정 후보", 48), ("최종 판정", 13), ("응답", 60), ("근거", 45), ("해석 제한", 36),
    ]  # fmt: skip
    rows = content.get("rows") or []
    values = [
        [
            r.get("no"),
            r.get("item"),
            r.get("category"),
            r.get("requirement"),
            r.get("clause"),
            r.get("offered"),
            r.get("compliance"),
            r.get("response"),
            r.get("evidence"),
            r.get("remark"),
        ]  # fmt: skip
        for r in rows
    ]
    start = len(meta) + 2
    last = _table(ws, start, columns, values)
    for i, row in enumerate(rows, start=start + 1):
        verdict = ws.cell(row=i, column=7)
        if row.get("compliance") in VERDICT_COLORS:
            verdict.font = Font(bold=True, color=VERDICT_COLORS[row["compliance"]])
        if row.get("risk") == "HIGH":
            ws.cell(row=i, column=1).fill = HIGH_FILL
            ws.cell(row=i, column=1).font = Font(bold=True, color="FFFFFF")
    _footer(ws, last, content)
    candidates = [
        [
            row["no"],
            row["requirement"],
            c["model_no"],
            c["comparison_label"],
            c["rationale"],
            c["scope_notice"],
            row["evidence"],
        ]
        for row in rows
        for c in row.get("candidate_comparisons", [])
    ]
    if candidates:
        detail = wb.create_sheet("후보 비교")
        _write(detail, 1, 1, "후보 기재값 비교 — 최종 공고 판정과 별개")
        detail.row_dimensions[1].height = 24
        _table(
            detail,
            3,
            [
                ("대응표 No", 10),
                ("요구사항", 48),
                ("제조사 모델", 24),
                ("후보 비교", 22),
                ("비교 이유", 65),
                ("범위", 40),
                ("근거", 50),
            ],
            candidates,
        )


def checklist_sheet(wb: Workbook, bid, content: dict) -> None:
    ws = wb.active
    ws.title = "입찰 체크리스트"
    _write(ws, 1, 1, f"[{bid.notice_no or '-'}] {bid.title}").font = Font(bold=True)
    ws.row_dimensions[1].height = 24
    columns = [
        ("섹션", 18),
        ("상태", 10),
        ("항목", 80),
        ("기한", 18),
        ("담당", 12),
        ("판정", 11),
        ("비고", 60),
    ]
    values = [
        [
            section.get("title"),
            STATUS_LABELS.get(item.get("status"), item.get("status")),
            item.get("text"),
            item.get("due"),
            item.get("owner"),
            item.get("verdict"),
            item.get("note"),
        ]
        for section in content.get("sections") or []
        for item in section.get("items") or []
    ]
    last = _table(ws, 3, columns, values)
    for r in range(4, last + 1):
        verdict = ws.cell(row=r, column=6)
        if verdict.value in VERDICT_COLORS:
            verdict.font = Font(bold=True, color=VERDICT_COLORS[verdict.value])
        if ws.cell(row=r, column=2).value == "완료":
            ws.cell(row=r, column=2).font = Font(color="198754")
    _footer(ws, last, content)


def render_xlsx(bid, doc_type: str, content: dict, version: int | None = None) -> bytes:
    wb = Workbook()
    if doc_type == DraftType.COMPLIANCE_MATRIX:
        compliance_matrix_sheet(wb, bid, content)
    else:
        checklist_sheet(wb, bid, content)
    if version:
        row = 4 if doc_type == DraftType.COMPLIANCE_MATRIX else 2
        _write(
            wb.active,
            row,
            2,
            f"저장 초안 v{version} · 판정 기준일 {content.get('analysis_context', {}).get('saved_evaluation_date', '미기록')} · 판정 재실행 없음",
        )
    wb.properties.subject = "직원 검토용 초안; 최종 공고 판정과 후보 비교 구분"
    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
