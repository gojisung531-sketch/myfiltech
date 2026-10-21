import re
from dataclasses import dataclass


@dataclass
class MetaValue:
    value: object
    raw: str = ""
    unit: str = ""
    confidence: float = 1.0
    page: int | None = None
    quote: str = ""


def one_line(text: str | None) -> str:
    """Join wrapped cell lines with spaces."""
    return re.sub(r"\s*\n\s*", " ", text or "").strip()


def glued(text: str | None) -> str:
    """Join wrapped lines without spaces (names broken mid-word, e.g. '가상남부발전(\\n주)')."""
    return re.sub(r"\s*\n\s*", "", text or "").strip()


def blank_if_dash(text: str | None) -> str:
    text = one_line(text)
    return "" if text in ("-", "–", "—") else text


def parse_date(text: str | None) -> str | None:
    match = re.search(r"(\d{4})[-./]\s*(\d{1,2})[-./]\s*(\d{1,2})", text or "")
    if not match:
        return None
    year, month, day = (int(g) for g in match.groups())
    return f"{year:04d}-{month:02d}-{day:02d}"


def key_values(tables: list[dict]) -> dict[str, tuple[str, int | None]]:
    """Label → (value, page) from two-column label/value tables."""
    result: dict[str, tuple[str, int | None]] = {}
    for table in tables:
        for row in table["rows"]:
            if len(row) >= 2 and row[0] and row[0] not in result:
                result[one_line(row[0])] = (row[1], table.get("page"))
    return result


def lookup(kv: dict, *prefixes: str) -> tuple[str, int | None] | None:
    """Find a value whose label equals or starts with one of `prefixes`."""
    for prefix in prefixes:
        if prefix in kv:
            return kv[prefix]
    for prefix in prefixes:
        for label, item in kv.items():
            if label.startswith(prefix):
                return item
    return None


def find_table(tables: list[dict], first_cell: str) -> dict | None:
    for table in tables:
        if table["rows"] and one_line(table["rows"][0][0]).startswith(first_cell):
            return table
    return None


def table_dict(table: dict | None) -> dict[str, str]:
    """{label: value} from a table whose first row is a header (항목 | 조건/결과)."""
    if not table:
        return {}
    return {one_line(r[0]): one_line(r[1]) for r in table["rows"][1:] if len(r) >= 2}


def notes_from_text(text: str) -> list[str]:
    """'※' remarks except the generic PoC disclaimer."""
    return [
        line.strip()
        for line in text.splitlines()
        if line.strip().startswith("※") and "PoC" not in line and "가상 자료이며" not in line
    ]
