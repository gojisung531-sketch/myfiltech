import pdfplumber
from pdfminer.pdfparser import PDFSyntaxError

from .base import ParseError, ParseResult, normalize_text, trim_rows


def _is_upright_glyph(obj) -> bool:
    """Drop rotated characters — diagonal watermarks such as 'SAMPLE · 가상 자료' (specs/06 §2)."""
    if obj.get("object_type") != "char":
        return True
    _, b, c, *_ = obj.get("matrix", (1, 0, 0, 1, 0, 0))
    return abs(b) < 1e-3 and abs(c) < 1e-3


def parse(path: str, min_chars_per_page: int = 30) -> ParseResult:
    try:
        pdf = pdfplumber.open(path)
    except (PDFSyntaxError, ValueError, OSError) as exc:
        raise ParseError(
            "PDF 파일을 열 수 없습니다. 손상되었거나 암호가 걸려 있을 수 있습니다."
        ) from exc

    pages: list[str] = []
    tables: list[dict] = []
    with pdf:
        for number, page in enumerate(pdf.pages, start=1):
            clean = page.filter(_is_upright_glyph)
            pages.append(normalize_text(clean.extract_text() or ""))
            for table in clean.extract_tables():
                rows = trim_rows(table)
                if rows:
                    tables.append({"page": number, "rows": rows})

    total_chars = sum(len(p.replace(" ", "").replace("\n", "")) for p in pages)
    is_scanned = bool(pages) and total_chars < min_chars_per_page * len(pages)
    warnings = ["텍스트가 거의 없는 스캔 PDF입니다."] if is_scanned else []
    return ParseResult(
        text="\f".join(pages), pages=pages, tables=tables, warnings=warnings, is_scanned=is_scanned
    )
