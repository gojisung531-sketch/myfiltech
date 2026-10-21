from pathlib import Path

from . import hwp, hwpx, office, pdf
from .base import ParseError, ParseResult, UnsupportedFormat

EXTENSION_FORMATS = {
    ".txt": "TXT",
    ".docx": "DOCX",
    ".doc": "DOC",
    ".hwp": "HWP",
    ".hwpx": "HWPX",
    ".pdf": "PDF",
    ".xls": "XLS",
    ".xlsx": "XLSX",
}


def detect_format(filename: str) -> str | None:
    return EXTENSION_FORMATS.get(Path(filename).suffix.lower())


def parse_file(path: str, file_format: str, *, min_chars_per_page: int = 30) -> ParseResult:
    if file_format == "PDF":
        return pdf.parse(path, min_chars_per_page=min_chars_per_page)
    parsers = {
        "TXT": office.parse_txt,
        "DOCX": office.parse_docx,
        "DOC": office.parse_doc,
        "HWP": hwp.parse,
        "HWPX": hwpx.parse,
        "XLS": office.parse_xls,
        "XLSX": office.parse_xlsx,
    }
    parser = parsers.get(file_format)
    if parser is None:
        raise UnsupportedFormat(f"지원하지 않는 형식입니다: {file_format}")
    return parser(path)


__all__ = [
    "EXTENSION_FORMATS",
    "ParseError",
    "ParseResult",
    "UnsupportedFormat",
    "detect_format",
    "parse_file",
]
