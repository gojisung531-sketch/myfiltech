"""HWPX (OWPML zip) extractor (specs/06 §2)."""

import re
import zipfile

from lxml import etree

from .base import ParseError, ParseResult, normalize_text, rows_to_text, trim_rows


def _local(tag) -> str:
    return etree.QName(tag).localname if isinstance(tag, str) else ""


def _paragraph_text(para) -> str:
    """Text of a paragraph, excluding text that sits inside tables within it."""
    return "".join(
        node.text
        for node in para.iter()
        if _local(node.tag) == "t" and node.text and not _inside_table_below(node, para)
    )


def _inside_table_below(node, root) -> bool:
    for ancestor in node.iterancestors():
        if ancestor is root:
            return False
        if _local(ancestor.tag) == "tbl":
            return True
    return False


def _table_rows(tbl) -> list[list[str]]:
    rows = []
    for tr in (c for c in tbl if _local(c.tag) == "tr"):
        cells = []
        for tc in (c for c in tr if _local(c.tag) == "tc"):
            cells.append(" ".join(t.text for t in tc.iter() if _local(t.tag) == "t" and t.text))
        rows.append(cells)
    return trim_rows(rows)


def parse(path: str) -> ParseResult:
    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        raise ParseError("HWPX 파일을 열 수 없습니다.") from exc

    with archive:
        names = sorted(
            (n for n in archive.namelist() if re.match(r"Contents/section\d+\.xml$", n)),
            key=lambda n: int(re.search(r"(\d+)", n).group(1)),
        )
        if not names:
            raise ParseError("HWPX 본문(section)을 찾을 수 없습니다.")
        lines: list[str] = []
        tables: list[dict] = []
        for name in names:
            root = etree.fromstring(archive.read(name))
            for para in (c for c in root if _local(c.tag) == "p"):
                text = _paragraph_text(para)
                if text.strip():
                    lines.append(text)
                for tbl in (n for n in para.iter() if _local(n.tag) == "tbl"):
                    if any(_local(a.tag) == "tbl" for a in tbl.iterancestors()):
                        continue  # nested tables are included in the outer cell text
                    rows = _table_rows(tbl)
                    if rows:
                        tables.append({"page": None, "rows": rows})
                        lines.extend(["[표]", rows_to_text(rows), "[/표]"])

    text = normalize_text("\n".join(lines))
    return ParseResult(text=text, pages=[text], tables=tables)
