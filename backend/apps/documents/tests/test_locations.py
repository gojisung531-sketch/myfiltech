"""Synthetic files and isolated DB only; no original company files or LLM calls."""

import hashlib
import io

import openpyxl
import pytest
from django.core.files.base import ContentFile

from apps.bids.models import BidAttachment, BidNotice, BidRequirement
from apps.company.models import Certificate, Company
from apps.documents.locations import SourceLocator, quote_spans, text_digest
from apps.documents.models import Document, DocumentMetadata
from apps.evaluation.models import RequirementEvaluation

pytestmark = pytest.mark.django_db


def pdf_bytes(pages=1):
    kids = " ".join(f"{n + 3} 0 R" for n in range(pages))
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {pages} >>".encode(),
    ]
    objects += [b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] >>"] * pages
    data = b"%PDF-1.4\n"
    offsets = []
    for index, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data += f"{index} 0 obj\n".encode() + obj + b"\nendobj\n"
    start = len(data)
    data += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    data += b"".join(f"{offset:010} 00000 n \n".encode() for offset in offsets)
    data += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n".encode()
    )
    return data


@pytest.fixture
def document_factory():
    def create(fmt="HWP", text="", data=b"synthetic original", owner="BID", **kwargs):
        doc = Document(
            file_format=fmt,
            owner_type=owner,
            extracted_text=text,
            sha256=hashlib.sha256(data).hexdigest(),
            original_filename="test." + fmt.lower(),
            **kwargs,
        )
        doc.file.save(doc.original_filename, ContentFile(data), save=False)
        doc.save()
        return doc

    return create


def test_hwp_heading_lines_offsets_and_markers_are_not_physical_pages(document_factory):
    text = "😀 Header\nPAGE\n4/8\n\n7.2 Inspection\nExact required\nwords\n"
    doc = document_factory(text=text, page_count=1)
    result = SourceLocator().locate(doc.pk, "Exact required words", page=4)
    assert result["status"] == "WHITESPACE_MATCH"
    assert result["physical_page_verified"] is False
    assert result["location_kind"] == "EXTRACTED_TEXT_RANGE"
    value = result["location_value"]
    assert text[value["start"] : value["end"]] == "Exact required\nwords"
    assert value["start_utf16"] == value["start"] + 1
    assert value["text_sha256"] == text_digest(text)
    assert value["section_heading"]["text"] == "7.2 Inspection"
    assert value["unverified_printed_marker"] == "PAGE\n4/8"
    assert value["extracted_block"] and value["original_hwp_paragraph"] is None


def test_all_literal_and_differently_wrapped_hits_remain_ambiguous(document_factory):
    doc = document_factory(text="target words\nsecond target\n words")
    result = SourceLocator().locate(doc.pk, "target words")
    assert result["status"] == "MULTIPLE_MATCHES" and len(result["candidates"]) == 2
    assert result["location_kind"] == "NONE" and result["location_value"] is None
    assert [c["match_mode"] for c in result["candidates"]] == ["EXACT", "WHITESPACE_NORMALIZED"]


def test_punctuation_mismatch_is_not_silently_repaired(document_factory):
    doc = document_factory(text="The holder said “required words” today")
    result = SourceLocator().locate(doc.pk, "said required words")
    assert result["status"] == "QUOTE_NOT_FOUND" and result["candidates"] == []
    assert result["quote"] == "said required words"


def test_blank_quote_never_matches_every_cell_or_text_character(document_factory):
    doc = document_factory(text="many words")
    assert SourceLocator().locate(doc.pk, " \n ")["status"] == "NO_QUOTE"
    assert quote_spans("many words", "") == []


def test_pdf_requires_real_page_count_and_respects_declared_page(document_factory):
    doc = document_factory("PDF", "first phrase\fsecond phrase", pdf_bytes(2), page_count=999)
    result = SourceLocator().locate(doc.pk, "second phrase", page=2)
    assert result["status"] == "EXACT_MATCH" and result["location_value"]["page"] == 2
    assert result["physical_page_count"] == 2
    assert SourceLocator().locate(doc.pk, "second phrase", page=1)["status"] == "QUOTE_NOT_FOUND"
    assert SourceLocator().locate(doc.pk, "second phrase", page=999)["status"] == "INVALID_PAGE"


def test_scanned_pdf_has_page_only_and_never_invents_quote_match(document_factory):
    doc = document_factory("PDF", "", pdf_bytes())
    result = SourceLocator().locate(doc.pk, "not OCRed", page=1)
    assert result["status"] == "PAGE_ONLY" and result["location_value"] == {"page": 1}
    assert result["quote_status"] == "NOT_CHECKED"
    assert result["candidates"][0]["matched_text"] is None


def test_pdf_page_segmentation_mismatch_does_not_create_page_mapping(document_factory):
    doc = document_factory("PDF", "all pages flattened", pdf_bytes(2), page_count=1)
    result = SourceLocator().locate(doc.pk, "flattened")
    assert result["status"] == "NO_VERIFIABLE_TEXT" and result["candidates"] == []


def test_workbook_coordinates_retain_blank_rows_and_multiple_sheets(document_factory):
    wb = openpyxl.Workbook()
    wb.active.title = "Details"
    wb.active["C8"] = "item ABC"
    wb.create_sheet("Other")["B5"] = "item ABC"
    wb["Other"]["G9"] = "unique DEF"
    wb["Other"]["H9"] = "=1+1"
    data = io.BytesIO()
    wb.save(data)
    doc = document_factory("XLSX", "flattened text", data.getvalue(), page_count=1)
    result = SourceLocator().locate(doc.pk, "ABC", page=1)
    assert result["status"] == "MULTIPLE_MATCHES"
    assert [(c["value"]["sheet"], c["value"]["cell"]) for c in result["candidates"]] == [
        ("Details", "C8"),
        ("Other", "B5"),
    ]
    result = SourceLocator().locate(doc.pk, "DEF")
    assert result["location_kind"] == "SPREADSHEET_CELL"
    assert result["location_value"]["cell"] == "G9"
    assert SourceLocator().locate(doc.pk, "2")["status"] == "QUOTE_NOT_FOUND"


def test_original_hash_change_or_missing_file_invalidates_navigation(document_factory):
    doc = document_factory(text="target")
    with open(doc.file.path, "wb") as stream:
        stream.write(b"changed")
    assert SourceLocator().locate(doc.pk, "target")["status"] == "SOURCE_CHANGED"
    doc.file.storage.delete(doc.file.name)
    assert SourceLocator().locate(doc.pk, "target")["status"] == "SOURCE_UNAVAILABLE"


def test_corrupt_original_is_reported_without_running_parser(document_factory):
    doc = document_factory("PDF", "target", b"not a PDF")
    assert SourceLocator().locate(doc.pk, "target")["status"] == "SOURCE_UNAVAILABLE"
    doc = document_factory("XLSX", "target", b"not a ZIP")
    assert SourceLocator().locate(doc.pk, "target")["status"] == "SOURCE_UNREADABLE"


@pytest.fixture
def manual_case(document_factory):
    doc = document_factory("PDF", "", pdf_bytes(3), owner="COMPANY")
    DocumentMetadata.objects.create(
        document=doc,
        key="manual_registration.b6a",
        source="MANUAL",
        value={"key": "original", "sha256": doc.sha256},
    )
    cert = Certificate.objects.create(
        cert_no="TEST-NUMBER", cert_type="PATENT", holder="Test", source_document=doc
    )
    key = "manual_certificate." + hashlib.sha256(cert.cert_no.encode()).hexdigest()[:32]
    DocumentMetadata.objects.create(
        document=doc,
        key=key,
        source="MANUAL",
        value={
            "values": {"cert_no": cert.cert_no, "holder": cert.holder},
            "evidence": [
                {
                    "source": "original",
                    "page": 2,
                    "quote": "Test co-owner",
                    "fields": ["holder"],
                    "method": "VISUAL_REVIEW",
                },
                {
                    "source": "original",
                    "page": 1,
                    "quote": "Test number",
                    "fields": ["cert_no"],
                    "method": "VISUAL_REVIEW",
                },
            ],
        },
    )
    company = Company.objects.create(name="Manual name")
    company.source_documents.add(doc)
    DocumentMetadata.objects.create(
        document=doc,
        key="manual_company.name",
        source="MANUAL",
        value={
            "value": company.name,
            "evidence": [
                {
                    "source": "original",
                    "page": 3,
                    "quote": "Manual name",
                    "fields": ["name"],
                    "method": "VISUAL_REVIEW",
                }
            ],
        },
    )
    return doc, cert, company


def test_manual_pages_are_per_field_and_shared_documents_are_not_all_page_one(manual_case):
    doc, cert, company = manual_case
    results = SourceLocator().manual_locations(certificate=cert)
    assert [x["location_value"]["page"] for x in results] == [2, 1]
    assert all(
        x["status"] == "MANUAL_REVIEWED_PAGE" and x["document_id"] == doc.pk for x in results
    )
    assert all(x["quote_status"] == "HUMAN_TRANSCRIBED_NOT_MACHINE_CHECKED" for x in results)
    assert SourceLocator().manual_locations(company=company)[0]["location_value"] == {"page": 3}
    cert.holder = "Staff edit"
    cert.save()
    assert (
        SourceLocator().manual_locations(certificate=cert)[0]["record_value_consistency"]
        == "DIFFERS_FROM_REVIEW"
    )


def test_metadata_source_hash_disagreement_is_not_guessed(manual_case):
    doc, cert, _ = manual_case
    DocumentMetadata.objects.filter(document=doc, key="manual_registration.b6a").update(
        value={"key": "original", "sha256": "0" * 64}
    )
    assert SourceLocator().manual_locations(certificate=cert)[0]["status"] == "MISSING_SOURCE"


def test_api_additions_preserve_saved_evidence_and_never_backfill_new_certs(
    document_factory,
    manual_case,
    manager_client,
    monkeypatch,
):
    from apps.core.models import Job
    from apps.documents import pipeline
    from apps.llm import services
    from apps.llm.models import LLMCallLog

    def forbidden(*args, **kwargs):
        raise AssertionError("No extraction, LLM, or downstream work allowed")

    monkeypatch.setattr(pipeline, "run_pipeline", forbidden)
    monkeypatch.setattr(services, "run_task", forbidden)
    doc = document_factory(text="3. Requirements\noriginal quotation")
    bid = BidNotice.objects.create(title="Synthetic bid")
    attachment = BidAttachment.objects.create(bid=bid, document=doc)
    req = BidRequirement.objects.create(
        bid=bid,
        title="Test",
        category="CERTIFICATION",
        normalized={"cert_type": "PATENT"},
        source_attachment=attachment,
        source_quote="original quotation",
    )
    stored = [
        {
            "type": "bid_quote",
            "id": attachment.pk,
            "page": 0,
            "quote": req.source_quote,
            "label": "Saved source",
        }
    ]
    evaluation = RequirementEvaluation.objects.create(
        requirement=req, verdict="NEEDS_CONFIRMATION", decided_by="RULE", evidences=stored
    )
    before = (
        list(RequirementEvaluation.objects.values()),
        list(BidRequirement.objects.values()),
        Job.objects.count(),
        LLMCallLog.objects.count(),
        DocumentMetadata.objects.count(),
    )
    for _ in range(2):
        rows = manager_client.get(f"/api/bids/{bid.pk}/requirements?include=evaluation").data
        assert rows[0]["source_quote"] == req.source_quote
        assert rows[0]["source_location"]["location_kind"] == "EXTRACTED_TEXT_RANGE"
        evidence = rows[0]["evaluation"]["evidences"][0]
        assert {k: evidence[k] for k in stored[0]} == stored[0]
        assert evidence["source_location"]["role"] == "STORED_EVALUATION_EVIDENCE"
        comparison = manager_client.get(f"/api/bids/{bid.pk}/comparison").data["rows"][0]
        assert comparison["certificates"][0]["relation_to_evaluation"] == "CURRENT_REFERENCE_ONLY"
        assert len(comparison["stored_evidence_locations"]) == 1
        assert all(
            e["saved_reference"]["type"] != "certificate"
            for e in comparison["stored_evidence_locations"]
        )
        assert comparison["current_references_revise_stored_evaluation"] is False
        assert manager_client.get(f"/api/certificates/{manual_case[1].pk}").data[
            "evidence_locations"
        ]
        assert manager_client.get("/api/company").data["evidence_locations"]
        text = manager_client.get(f"/api/documents/{doc.pk}/text").data
        assert (
            text["pages"] == [doc.extracted_text] and text["extracted_text"] == doc.extracted_text
        )
        assert text["pages_kind"] == "EXTRACTION_CHUNKS_NOT_PHYSICAL_PAGES"
        locate = manager_client.get(f"/api/documents/{doc.pk}/locate", {"quote": req.source_quote})
        assert locate.data["status"] == "EXACT_MATCH"
    evaluation.refresh_from_db()
    assert evaluation.evidences == stored
    assert before == (
        list(RequirementEvaluation.objects.values()),
        list(BidRequirement.objects.values()),
        Job.objects.count(),
        LLMCallLog.objects.count(),
        DocumentMetadata.objects.count(),
    )


def test_locate_permissions_input_validation_and_existing_document_access(
    document_factory, api_client, manager_client
):
    doc = document_factory(text="target")
    assert api_client.get(f"/api/documents/{doc.pk}/locate?quote=target").status_code == 401
    assert (
        manager_client.get(f"/api/documents/{doc.pk}/locate?quote=target&page=oops").status_code
        == 400
    )
    assert (
        manager_client.get(f"/api/documents/{doc.pk}/locate?quote=target&page=0").status_code == 400
    )
    assert (
        manager_client.get(f"/api/documents/{doc.pk}/locate", {"quote": "x" * 8001}).status_code
        == 400
    )
    assert manager_client.get("/api/documents/99999/locate?quote=target").status_code == 404
