"""HWP 5.0 text/table extractor using olefile + zlib (specs/06 §2.1). pyhwp (AGPL) is not used."""

import struct
import zlib

import olefile

from .base import (
    ParseError,
    ParseResult,
    UnsupportedFormat,
    normalize_text,
    rows_to_text,
    trim_rows,
)

HWPTAG_PARA_TEXT = 67
HWPTAG_CTRL_HEADER = 71
HWPTAG_LIST_HEADER = 72
HWPTAG_TABLE = 77

# Control characters occupying 8 WCHARs (inline/extended controls); 9 (tab) is kept as '\t'.
_EXTENDED_CONTROLS = set(range(1, 10)) | {11, 12} | set(range(14, 24))


def decode_para_text(data: bytes) -> str:
    out = []
    i = 0
    length = len(data) - len(data) % 2
    while i < length:
        code = data[i] | (data[i + 1] << 8)
        if code < 32:
            if code in _EXTENDED_CONTROLS:
                if code == 9:
                    out.append("\t")
                i += 16
                continue
            if code == 10:
                out.append("\n")
            # 0, 13 (paragraph end) and 24–31 are single-WCHAR controls with no text.
            i += 2
            continue
        out.append(chr(code))
        i += 2
    return "".join(out)


def _records(data: bytes):
    i = 0
    while i + 4 <= len(data):
        header = struct.unpack_from("<I", data, i)[0]
        i += 4
        tag, level, size = header & 0x3FF, (header >> 10) & 0x3FF, header >> 20
        if size == 0xFFF:
            size = struct.unpack_from("<I", data, i)[0]
            i += 4
        yield tag, level, data[i : i + size]
        i += size


class _Table:
    def __init__(self, level: int):
        self.level = level
        self.cells: list[tuple[int, int, list[str]]] = []

    def new_cell(self, body: bytes) -> None:
        col, row = struct.unpack_from("<HH", body, 8) if len(body) >= 12 else (0, len(self.cells))
        self.cells.append((row, col, []))

    def add_text(self, text: str) -> None:
        if not self.cells:
            self.cells.append((0, 0, []))
        self.cells[-1][2].append(text)

    def rows(self) -> list[list[str]]:
        by_row: dict[int, list[tuple[int, str]]] = {}
        for row, col, parts in self.cells:
            text = "\n".join(p.strip() for p in parts if p.strip())
            by_row.setdefault(row, []).append((col, text))
        rows = []
        for row in sorted(by_row):
            cells = [text for _, text in sorted(by_row[row])]
            rows.append(cells)
        return trim_rows(rows)


def _is_layout_table(rows: list[list[str]]) -> bool:
    """Many HWP notices wrap whole sections in a table; such cells hold multi-line prose."""
    return any(len(cell) > 200 for row in rows for cell in row)


def _table_lines(rows: list[list[str]]) -> list[str]:
    if _is_layout_table(rows):
        return [cell for row in rows for cell in row if cell]
    flat = [[cell.replace("\n", " ") for cell in row] for row in rows]
    return ["[표]", rows_to_text(flat), "[/표]"]


def parse(path: str) -> ParseResult:
    try:
        ole = olefile.OleFileIO(path)
    except OSError as exc:
        raise ParseError(
            "HWP 파일을 열 수 없습니다. 손상되었거나 HWP 5.0 형식이 아닙니다."
        ) from exc

    with ole:
        if not ole.exists("FileHeader"):
            raise ParseError("HWP 5.0 형식이 아닙니다.")
        flags = ole.openstream("FileHeader").read()[36]
        if flags & 0x02:
            raise UnsupportedFormat("암호가 설정된 HWP 문서는 지원하지 않습니다.")
        if flags & 0x04 or ole.exists("ViewText"):
            raise UnsupportedFormat(
                "배포용 HWP 문서는 지원하지 않습니다. 일반 문서로 저장 후 올려주세요."
            )
        compressed = bool(flags & 0x01)
        sections = sorted(
            (entry for entry in ole.listdir() if entry[0] == "BodyText"),
            key=lambda entry: int(entry[1].replace("Section", "") or 0),
        )

        lines: list[str] = []
        tables: list[dict] = []
        for entry in sections:
            data = ole.openstream(entry).read()
            if compressed:
                try:
                    data = zlib.decompress(data, -15)
                except zlib.error as exc:
                    raise ParseError("HWP 본문 압축을 해제하지 못했습니다.") from exc
            _parse_section(data, lines, tables)

    text = normalize_text("\n".join(lines))
    return ParseResult(text=text, pages=[text], tables=tables)


def _parse_section(data: bytes, lines: list[str], tables: list[dict]) -> None:
    stack: list[_Table] = []

    def close_until(level: int) -> None:
        while stack and level <= stack[-1].level:
            table = stack.pop()
            rows = table.rows()
            if not rows:
                continue
            tables.append({"page": None, "rows": rows})
            if stack:
                stack[-1].add_text("\n".join(_table_lines(rows)))
            else:
                lines.extend(_table_lines(rows))

    for tag, level, body in _records(data):
        close_until(level)
        if tag == HWPTAG_CTRL_HEADER and body[:4] == b" lbt":  # 'tbl ' stored little-endian
            stack.append(_Table(level))
        elif tag == HWPTAG_LIST_HEADER and stack and level == stack[-1].level + 1:
            stack[-1].new_cell(body)
        elif tag == HWPTAG_PARA_TEXT:
            text = decode_para_text(body)
            if stack:
                stack[-1].add_text(text)
            else:
                lines.append(text)
    close_until(0)
