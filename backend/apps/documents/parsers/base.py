import re
from dataclasses import dataclass, field


class ParseError(Exception):
    """Parsing failed; message is user-facing Korean."""


class UnsupportedFormat(ParseError):
    pass


@dataclass
class ParseResult:
    text: str
    pages: list[str] = field(default_factory=list)
    tables: list[dict] = field(default_factory=list)  # [{"page": int|None, "rows": [[str]]}]
    warnings: list[str] = field(default_factory=list)
    is_scanned: bool = False

    @property
    def page_count(self) -> int | None:
        return len(self.pages) or None


def clean_cell(value) -> str:
    if value is None:
        return ""
    return re.sub(r"[ \t]+", " ", str(value)).strip()


def trim_rows(rows: list[list]) -> list[list[str]]:
    """Clean cells, drop trailing empty cells and fully empty rows."""
    result = []
    for row in rows:
        cells = [clean_cell(c) for c in row]
        while cells and not cells[-1]:
            cells.pop()
        if any(cells):
            result.append(cells)
    return result


def rows_to_text(rows: list[list[str]]) -> str:
    return "\n".join(" | ".join(cells) for cells in rows)


def normalize_text(text: str) -> str:
    """Collapse runs of spaces and blank lines (specs/06 §2.3); keeps page breaks."""
    pages = []
    for page in text.split("\f"):
        lines = [re.sub(r"[ \t ]+", " ", line).rstrip() for line in page.splitlines()]
        page_text = "\n".join(lines)
        page_text = re.sub(r"\n{3,}", "\n\n", page_text).strip()
        pages.append(page_text)
    return "\f".join(pages)
