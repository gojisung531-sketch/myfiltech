"""Read-only evidence anchors. Never run a parser, repair quotes, or save a result.

HWP anchors address the stored extracted text, not HWP physical pages/paragraphs.
PDF page counts and workbook cells are inspected in the unchanged original bytes.
"""

import hashlib
import re
from zipfile import BadZipFile

import openpyxl
import pdfplumber
from pdfminer.pdfdocument import PDFPasswordIncorrect
from pdfminer.pdfparser import PDFSyntaxError
from pdfplumber.utils.exceptions import PdfminerException

from .models import Document, DocumentMetadata


def text_digest(text):
    return hashlib.sha256(text.encode("utf8")).hexdigest()


def _compact(text):
    indexes = [i for i, char in enumerate(text) if not char.isspace()]
    return "".join(text[i] for i in indexes), indexes


def quote_spans(text, quote):
    """All occurrences, ignoring only whitespace. Offsets remain in original text.

    Always search whitespace-normalized text, even when one literal hit exists:
    otherwise a second differently wrapped hit would be hidden.
    """
    normalized, offsets = _compact(text)
    needle, _ = _compact(quote)
    if not needle:
        return []
    result = []
    offset = 0
    while (found := normalized.find(needle, offset)) >= 0:
        start, end = offsets[found], offsets[found + len(needle) - 1] + 1
        result.append(
            (start, end, "EXACT" if text[start:end] == quote else "WHITESPACE_NORMALIZED")
        )
        offset = found + 1
    return result


def _text_candidate(text, start, end, mode):
    heading = None
    line_offset = 0
    for index, source_line in enumerate(text.splitlines(keepends=True), 1):
        if line_offset > start:
            break
        line = source_line.rstrip("\r\n")
        if "|" not in line and re.fullmatch(r"\s*\d+(?:\.\d+)*\.?\s+[^\d\s].{1,100}", line):
            heading = {
                "text": line,
                "extracted_line": index,
                "method": "NEAREST_NUMBERED_TEXT_LINE",
                "section_scope_verified": False,
            }
        line_offset += len(source_line)
    blocks = list(re.finditer(r"\S[\s\S]*?(?=\n\s*\n|\Z)", text))
    block = next(((i, m) for i, m in enumerate(blocks, 1) if m.start() <= start < m.end()), None)
    value = {
        "text_sha256": text_digest(text),
        "start": start,
        "end": end,
        "offset_unit": "UNICODE_CODE_POINT",
        "end_exclusive": True,
        "start_utf16": len(text[:start].encode("utf-16-le")) // 2,
        "end_utf16": len(text[:end].encode("utf-16-le")) // 2,
        "extracted_line_start": text.count("\n", 0, start) + 1,
        "extracted_line_end": text.count("\n", 0, end) + 1,
        "section_heading": heading,
        "extracted_block": {"index": block[0], "start": block[1].start(), "end": block[1].end()}
        if block
        else None,
        "original_hwp_section": None,
        "original_hwp_paragraph": None,
    }
    markers = list(re.finditer(r"\bPAGE\s*\n\s*\d+\s*/\s*\d+", text[:start]))
    value["unverified_printed_marker"] = markers[-1].group() if markers else None
    return {
        "kind": "EXTRACTED_TEXT_RANGE",
        "value": value,
        "matched_text": text[start:end],
        "match_mode": mode,
    }


class SourceLocator:
    """Per-response cache; never cache current files/metadata across requests."""

    def __init__(self):
        self.documents = {}
        self.files = {}
        self.manual_sources = None
        self.manual_rows = None
        self.manual_cache = {}

    def document(self, pk):
        if type(pk) is not int or pk <= 0:
            return None
        if pk not in self.documents:
            self.documents[pk] = Document.objects.filter(pk=pk).first() if pk else None
        return self.documents[pk]

    def file_info(self, document):
        if document.pk not in self.files:
            info = {"status": "NO_FILE", "sha256": None, "pdf_pages": None}
            if document.file:
                try:
                    with document.file.open("rb") as stream:
                        info["sha256"] = hashlib.file_digest(stream, "sha256").hexdigest()
                    info["status"] = (
                        "VERIFIED"
                        if info["sha256"] == document.sha256
                        else "SOURCE_CHANGED"
                        if document.sha256
                        else "NO_RECORDED_HASH"
                    )
                    if document.file_format == "PDF" and info["status"] == "VERIFIED":
                        with document.file.open("rb") as stream, pdfplumber.open(stream) as pdf:
                            info["pdf_pages"] = len(pdf.pages)  # no text extraction/OCR
                except (
                    OSError,
                    ValueError,
                    PDFSyntaxError,
                    PDFPasswordIncorrect,
                    PdfminerException,
                ):
                    info["status"] = "SOURCE_UNAVAILABLE"
            self.files[document.pk] = info
        return self.files[document.pk]

    def locate(self, document_id, quote, *, page=None, role="REFERENCE", manual=False):
        document = self.document(document_id)
        result = {
            "document_id": document_id,
            "role": role,
            "quote": quote,
            "declared_page": page,
            "location_kind": "NONE",
            "location_value": None,
            "candidates": [],
            "status": "MISSING_DOCUMENT",
            "quote_status": "NOT_CHECKED",
        }
        if not document:
            return result
        info = self.file_info(document)
        result.update(
            file_format=document.file_format,
            document_sha256=document.sha256,
            original_filename=document.original_filename,
            download_url=f"/api/documents/{document.pk}/download",
            text_url=f"/api/documents/{document.pk}/text",
            source_verification=info["status"],
            text_sha256=text_digest(document.extracted_text),
            comparison_basis="STORED_EXTRACTED_TEXT",
            declared_page_kind="PHYSICAL_PDF_PAGE"
            if document.file_format == "PDF"
            else "LEGACY_NON_PHYSICAL_PAGE",
        )
        if info["status"] in {"SOURCE_CHANGED", "SOURCE_UNAVAILABLE"}:
            result["status"] = info["status"]
            return result
        if document.file_format in {"XLSX", "XLS"}:
            try:
                self._spreadsheet(document, quote, result)
            except (OSError, ValueError, BadZipFile):
                result["status"] = "SOURCE_UNREADABLE"
                result["candidates"] = []
        elif document.file_format == "PDF":
            self._pdf(document, quote, page, manual, info, result)
        else:
            result["candidates"] = [
                _text_candidate(document.extracted_text, *span)
                for span in quote_spans(document.extracted_text, quote)
            ]
            result["status"] = "NO_QUOTE" if not quote.strip() else "QUOTE_NOT_FOUND"
            result["quote_status"] = "EMPTY" if not quote.strip() else "NOT_FOUND"
            result["physical_page_verified"] = False
        self._finish(result)
        return result

    @staticmethod
    def _finish(result):
        candidates = result["candidates"]
        if len(candidates) > 1:
            result["status"] = "MULTIPLE_MATCHES"
            result["quote_status"] = "MULTIPLE_MATCHES"
        elif candidates:
            candidate = candidates[0]
            result["location_kind"] = candidate["kind"]
            result["location_value"] = candidate["value"]
            if candidate["kind"] == "PDF_PAGE":
                result["physical_page_verified"] = True
            if candidate["match_mode"] in {"EXACT", "WHITESPACE_NORMALIZED"}:
                result["quote_status"] = candidate["match_mode"]
                result["status"] = (
                    "EXACT_MATCH" if candidate["match_mode"] == "EXACT" else "WHITESPACE_MATCH"
                )

    def _pdf(self, document, quote, page, manual, info, result):
        page_ok = (
            type(page) is int and info["pdf_pages"] is not None and 1 <= page <= info["pdf_pages"]
        )
        result["physical_page_verified"] = page_ok
        result["physical_page_count"] = info["pdf_pages"]
        if page not in (None, 0) and not page_ok:
            result["status"] = "INVALID_PAGE"
            return
        if manual and page_ok:
            result.update(status="MANUAL_REVIEWED_PAGE", comparison_basis="B6A_MANUAL_METADATA")
            result["candidates"] = [
                {
                    "kind": "PDF_PAGE",
                    "value": {"page": page},
                    "matched_text": None,
                    "match_mode": "MANUAL_PAGE_ONLY",
                }
            ]
            # B6A is human review, not OCR. Keep quotation verification separate.
            result["quote_status"] = "HUMAN_TRANSCRIBED_NOT_MACHINE_CHECKED"
            return
        pages = document.extracted_text.split("\f") if document.extracted_text else []
        if info["pdf_pages"] is None or len(pages) != info["pdf_pages"]:
            result["status"] = "PAGE_ONLY" if page_ok else "NO_VERIFIABLE_TEXT"
            if page_ok:
                result["candidates"] = [
                    {
                        "kind": "PDF_PAGE",
                        "value": {"page": page},
                        "matched_text": None,
                        "match_mode": "PAGE_ONLY",
                    }
                ]
            return
        result.update(
            status="NO_QUOTE" if not quote.strip() else "QUOTE_NOT_FOUND",
            quote_status="EMPTY" if not quote.strip() else "NOT_FOUND",
        )
        for number, text in enumerate(pages, 1):
            if page_ok and number != page:
                continue
            for start, end, mode in quote_spans(text, quote):
                result["candidates"].append(
                    {
                        "kind": "PDF_PAGE",
                        "value": {
                            "page": number,
                            "page_text_start": start,
                            "page_text_end": end,
                            "page_text_sha256": text_digest(text),
                            "offset_unit": "UNICODE_CODE_POINT",
                        },
                        "matched_text": text[start:end],
                        "match_mode": mode,
                    }
                )

    def _spreadsheet(self, document, quote, result):
        result["comparison_basis"] = "ORIGINAL_WORKBOOK_CELLS"
        result.update(
            status="NO_QUOTE" if not quote.strip() else "QUOTE_NOT_FOUND",
            quote_status="EMPTY" if not quote.strip() else "NOT_FOUND",
        )
        if self.file_info(document)["status"] != "VERIFIED":
            result["status"] = "SOURCE_UNVERIFIED"
            return
        # Read existing cells without saving, formula evaluation, or pipeline extraction.
        if document.file_format == "XLSX":
            with document.file.open("rb") as stream:
                workbook = openpyxl.load_workbook(stream, read_only=True, data_only=False)
                try:
                    cells = [
                        (sheet.title, cell.coordinate, str(cell.value))
                        for sheet in workbook
                        for row in sheet
                        for cell in row
                        if cell.value is not None
                    ]
                finally:
                    workbook.close()
        else:
            import xlrd
            from openpyxl.utils import get_column_letter

            with document.file.open("rb") as stream:
                workbook = xlrd.open_workbook(file_contents=stream.read(), on_demand=True)
            try:
                cells = [
                    (sheet.name, f"{get_column_letter(c + 1)}{r + 1}", str(sheet.cell_value(r, c)))
                    for sheet in workbook.sheets()
                    for r in range(sheet.nrows)
                    for c in range(sheet.ncols)
                    if sheet.cell_value(r, c) != ""
                ]
            finally:
                workbook.release_resources()
        for sheet, coordinate, text in cells:
            for start, end, mode in quote_spans(text, quote):
                result["candidates"].append(
                    {
                        "kind": "SPREADSHEET_CELL",
                        "value": {
                            "sheet": sheet,
                            "cell": coordinate,
                            "start": start,
                            "end": end,
                            "offset_unit": "UNICODE_CODE_POINT",
                            "cell_text": text,
                        },
                        "matched_text": text[start:end],
                        "match_mode": mode,
                    }
                )

    def requirement(self, requirement):
        attachment = requirement.source_attachment
        result = self.locate(
            attachment.document_id if attachment else None,
            requirement.source_quote,
            page=requirement.source_page,
            role="REQUIREMENT_SOURCE",
        )
        result["attachment_id"] = requirement.source_attachment_id
        result["quote_origin"] = "STORED_REQUIREMENT_SOURCE_QUOTE"
        return result

    def _manual_index(self):
        if self.manual_rows is not None:
            return
        self.manual_rows = list(
            DocumentMetadata.objects.filter(
                document__owner_type="COMPANY", key__startswith="manual_"
            ).select_related("document")
        )
        self.manual_sources = {}
        for row in self.manual_rows:
            self.documents[row.document_id] = row.document
            value = row.value or {}
            if row.key == "manual_registration.b6a" and isinstance(value, dict):
                self.manual_sources.setdefault(value.get("key"), []).append((row.document, value))

    def manual_locations(self, *, certificate=None, company=None):
        self._manual_index()
        cache_key = ("certificate", certificate.pk) if certificate else ("company", company.pk)
        if cache_key in self.manual_cache:
            return self.manual_cache[cache_key]
        result = []
        for row in self.manual_rows:
            if certificate:
                key = (
                    "manual_certificate."
                    + hashlib.sha256(certificate.cert_no.encode()).hexdigest()[:32]
                )
                if row.document_id != certificate.source_document_id or row.key != key:
                    continue
                values = row.value.get("values", {})
                consistent = all(
                    str(getattr(certificate, field)) == str(value)
                    for field, value in values.items()
                )
            else:
                if not row.key.startswith("manual_company."):
                    continue
                field = row.key.removeprefix("manual_company.")
                if not hasattr(company, field):
                    continue
                consistent = str(getattr(company, field)) == str(row.value.get("value"))
            for evidence in (row.value or {}).get("evidence", []):
                sources = self.manual_sources.get(evidence.get("source"), [])
                valid = [
                    (doc, source) for doc, source in sources if source.get("sha256") == doc.sha256
                ]
                if len(valid) != 1:
                    location = self.locate(
                        None,
                        evidence.get("quote", ""),
                        page=evidence.get("page"),
                        role="CURRENT_COMPANY_REFERENCE",
                    )
                    location["status"] = "AMBIGUOUS_SOURCE" if valid else "MISSING_SOURCE"
                else:
                    doc, _ = valid[0]
                    location = self.locate(
                        doc.pk,
                        evidence.get("quote", ""),
                        page=evidence.get("page"),
                        role="CURRENT_COMPANY_REFERENCE",
                        manual=True,
                    )
                location.update(
                    metadata_id=row.pk,
                    metadata_key=row.key,
                    fields=evidence.get("fields", [field] if not certificate else []),
                    input_method=evidence.get("method"),
                    record_value_consistency="MATCHES_REVIEW"
                    if consistent
                    else "DIFFERS_FROM_REVIEW",
                    historical_evaluation_use="NOT_ASSERTED",
                )
                result.append(location)
        self.manual_cache[cache_key] = result
        return result


def locator_for(context):
    if "source_locator" not in context:
        context["source_locator"] = SourceLocator()
    return context["source_locator"]
