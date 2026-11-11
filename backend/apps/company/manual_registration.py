"""Import human-reviewed source facts, without extraction or downstream jobs.

The input manifest and backups contain private company information and stay local.
Company row locking serializes this importer; existing manual edits are never updated.
"""

import hashlib
import json
import re
from datetime import date
from pathlib import Path

import pdfplumber
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction

from apps.documents.models import Document, DocumentMetadata, MetadataSchema

from .models import Certificate, CertType, Company

REVIEW_KEY = "manual_registration.b6a"
COMPANY_FIELDS = {
    "name",
    "ceo",
    "business_no",
    "address",
    "phone",
    "email",
    "homepage",
    "established_date",
    "employees",
    "is_sme",
    "sme_cert_valid_until",
    "g2b_registered_items",
    "main_products",
    "description",
}
CERT_FIELDS = {
    "cert_no",
    "name",
    "cert_type",
    "standard",
    "holder",
    "scope",
    "product_codes",
    "issuer",
    "issue_date",
    "valid_from",
    "valid_until",
    "notes",
}
DATE_FIELDS = {
    "issue_date",
    "valid_from",
    "valid_until",
    "established_date",
    "sme_cert_valid_until",
}


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _key(cert_no):
    return "manual_certificate." + _digest(cert_no.encode())[:32]


def _values(values):
    return {k: date.fromisoformat(v) if k in DATE_FIELDS and v else v for k, v in values.items()}


def _write_new(path, value):
    with path.open("x", encoding="utf8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, default=str)


def _evidence(entries, sources):
    if not entries:
        raise ValueError("Human-reviewed source evidence is required")
    for entry in entries:
        source = sources[entry["source"]]
        page = entry["page"]
        if type(page) is not int or not 1 <= page <= source["page_count"]:
            raise ValueError("Evidence must use a verified physical PDF page")
        if not entry.get("quote", "").strip() or entry.get("method") not in {
            "VISUAL_REVIEW",
            "PDF_TEXT_AND_VISUAL_REVIEW",
        }:
            raise ValueError("A reviewed quote and method are required")


def validate_manifest(manifest):
    """Validate bytes/pages and explicit facts; never infer missing identifiers/dates."""
    if manifest.get("version") != 1:
        raise ValueError("Unsupported manifest version")
    sources = {}
    hashes = set()
    for source in manifest["sources"]:
        if source["key"] in sources:
            raise ValueError("Duplicate source key")
        if source["sha256"] in hashes:
            raise ValueError("Duplicate source bytes in manifest")
        hashes.add(source["sha256"])
        data = Path(source["path"]).read_bytes()
        if not re.fullmatch(r"[0-9a-f]{64}", source["sha256"]) or _digest(data) != source["sha256"]:
            raise ValueError("Source SHA256 mismatch")
        with pdfplumber.open(Path(source["path"])) as pdf:
            if len(pdf.pages) != source["page_count"]:
                raise ValueError("PDF page count mismatch")
        sources[source["key"]] = source
    seen = set()
    for source in sources.values():
        if source["category"] not in {"certificate", "company_profile"}:
            raise ValueError("Unsupported document category")
        for record in source.get("records", []):
            if record["decision"] == "HOLD":
                if not record.get("missing_fields") or not record.get("reason"):
                    raise ValueError("Held record requires missing fields and reason")
                _evidence(record["evidence"], sources)
                continue
            if record["decision"] != "REGISTER":
                raise ValueError("Explicit registration decision required")
            values = record["values"]
            if set(values) - CERT_FIELDS:
                raise ValueError("Unsupported certificate field")
            required = {"cert_no", "cert_type", "name", "holder", "scope", "issuer"}
            if any(not values.get(k) for k in required) or values["cert_no"] in seen:
                raise ValueError("Missing certificate identity or duplicate number")
            seen.add(values["cert_no"])
            if values["cert_type"] not in CertType.values:
                raise ValueError("Unknown document type")
            _evidence(record["evidence"], sources)
            covered = {f for e in record["evidence"] for f in e["fields"]}
            if set(values) - {"notes"} - covered:
                raise ValueError("Every certificate value needs field-level evidence")
            if any(e["source"] != source["key"] for e in record["evidence"]):
                raise ValueError("Certificate evidence must refer to its original PDF")
            candidate = Certificate(**_values(values))
            candidate.clean_fields(exclude=["source_document"])
            if (
                candidate.valid_from
                and candidate.valid_until
                and candidate.valid_from > candidate.valid_until
            ):
                raise ValueError("Reversed validity dates")
    for field, fact in manifest["company"].items():
        if field not in COMPANY_FIELDS:
            raise ValueError("Unsupported company field")
        _evidence(fact["evidence"], sources)
        Company(**_values({field: fact["value"]})).clean_fields(
            exclude=[f.name for f in Company._meta.fields if f.name != field]
        )
    return sources


def _existing_metadata(document, key, value):
    existing = DocumentMetadata.objects.filter(document=document, key=key).first()
    if existing and existing.value != value:
        raise ValueError("Existing reviewed metadata differs; manual review required")
    return existing


def _metadata(document, key, value, evidence):
    if _existing_metadata(document, key, value):
        return False
    first = evidence[0] if evidence else None
    DocumentMetadata.objects.create(
        document=document,
        key=key,
        label="원본 수동 확인·등록 근거",
        value=value,
        source="MANUAL",
        is_locked=True,
        evidence_page=first["page"] if first else None,
        evidence_quote=first["quote"] if first else "",
    )
    return True


def register_reviewed(manifest, *, apply=False, backup=None):
    """Default dry run. Apply requires an exclusive local recovery journal.

    No service/pipeline/worker hooks are called. A changed manifest conflicts instead
    of overwriting old review metadata. A rerun preserves edited structured rows.
    """
    sources = validate_manifest(manifest)
    if apply:
        backup = Path(backup) if backup else None
        private_root = (Path(settings.BACKEND_DIR) / ".venv").resolve()
        if not backup or not backup.resolve().is_relative_to(private_root):
            raise ValueError("An unused backup path under backend/.venv is required")
        if backup.exists() or backup.with_suffix(".result.json").exists():
            raise ValueError("Recovery journal already exists")
    created_files = []
    result = {
        "applied": apply,
        "new_documents": 0,
        "new_certificates": 0,
        "new_metadata": 0,
        "company_fields_changed": [],
        "company_fields_preserved": [],
        "preserved_edited_certificates": [],
        "inventory": [],
    }
    try:
        with transaction.atomic():
            # This singleton already exists; do not create business data on a dry run.
            company = Company.objects.select_for_update().get(pk=1)
            before = {
                "company": list(Company.objects.filter(pk=1).values()),
                "company_sources": list(company.source_documents.values_list("pk", flat=True)),
                "manifest": manifest,
                "manifest_sha256": _digest(
                    json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode()
                ),
            }
            docs = {}
            certificates = {}
            for key, source in sources.items():
                matches = list(
                    Document.objects.filter(owner_type="COMPANY", sha256=source["sha256"])
                )
                if len(matches) > 1:
                    raise ValueError("Duplicate existing source documents require review")
                document = matches[0] if matches else None
                if document:
                    with document.file.open("rb") as stream:
                        if _digest(stream.read()) != source["sha256"]:
                            raise ValueError("Existing uploaded source differs")
                    if document.page_count != source["page_count"]:
                        raise ValueError("Existing page count differs")
                    _existing_metadata(document, REVIEW_KEY, source)
                docs[key] = document
                result["new_documents"] += document is None
                for record in source.get("records", []):
                    if record["decision"] != "REGISTER":
                        continue
                    existing = (
                        Certificate.objects.select_for_update()
                        .filter(cert_no=record["values"]["cert_no"])
                        .first()
                    )
                    certificates[record["values"]["cert_no"]] = existing
                    if existing:
                        if not document or existing.source_document_id != document.pk:
                            raise ValueError("Certificate number belongs to another source")
                        marker = _existing_metadata(document, _key(existing.cert_no), record)
                        differs = any(
                            getattr(existing, f) != v for f, v in _values(record["values"]).items()
                        )
                        if differs and not marker:
                            raise ValueError(
                                "Existing manual certificate differs; refusing adoption"
                            )
                        if differs:
                            result["preserved_edited_certificates"].append(existing.pk)
                    else:
                        result["new_certificates"] += 1
            # Check all company provenance before any storage writes.
            company_changes = {}
            for field, fact in manifest["company"].items():
                source_key = fact["evidence"][0]["source"]
                document = docs[source_key]
                marker = (
                    _existing_metadata(document, "manual_company." + field, fact)
                    if document
                    else None
                )
                current = getattr(company, field)
                if marker or current not in (None, "", []):
                    if current != _values({field: fact["value"]})[field]:
                        result["company_fields_preserved"].append(field)
                else:
                    company_changes[field] = _values({field: fact["value"]})[field]
            result["company_fields_changed"] = list(company_changes)
            if apply:
                _write_new(backup, before)  # before DB or media mutation, never overwritten
            for key, source in sources.items():
                document = docs[key]
                if not document and apply:
                    data = Path(source["path"]).read_bytes()
                    if _digest(data) != source["sha256"]:
                        raise ValueError("Source changed during registration")
                    document = Document(
                        owner_type="COMPANY",
                        file_format="PDF",
                        original_filename=Path(source["path"]).name,
                        sha256=source["sha256"],
                        file_size=len(data),
                        page_count=source["page_count"],
                        category=MetadataSchema.objects.get(
                            code=source["category"], owner_type="COMPANY"
                        ),
                        category_source="MANUAL",
                        status="REVIEWED",
                    )
                    document.file.save(document.original_filename, ContentFile(data), save=False)
                    created_files.append((document.file.storage, document.file.name))
                    document.save()
                    docs[key] = document
                item = {
                    "key": key,
                    "sha256": source["sha256"],
                    "document_id": document.pk if document else None,
                    "registered": [],
                    "held": [],
                }
                if apply:
                    company.source_documents.add(document)
                    result["new_metadata"] += _metadata(document, REVIEW_KEY, source, [])
                for record in source.get("records", []):
                    if record["decision"] == "HOLD":
                        item["held"].append(
                            {"missing_fields": record["missing_fields"], "reason": record["reason"]}
                        )
                        continue  # original/known facts/reason are kept in REVIEW_KEY, no formal row
                    values = _values(record["values"])
                    cert = certificates[values["cert_no"]]
                    if apply:
                        if not cert:
                            cert = Certificate.objects.create(**values, source_document=document)
                        result["new_metadata"] += _metadata(
                            document, _key(cert.cert_no), record, record["evidence"]
                        )
                    item["registered"].append(
                        {
                            "id": cert.pk if cert else None,
                            "cert_no": values["cert_no"],
                            "cert_type": values["cert_type"],
                        }
                    )
                result["inventory"].append(item)
            if apply:
                for field, fact in manifest["company"].items():
                    document = docs[fact["evidence"][0]["source"]]
                    result["new_metadata"] += _metadata(
                        document, "manual_company." + field, fact, fact["evidence"]
                    )
                if company_changes:
                    for field, value in company_changes.items():
                        setattr(company, field, value)
                    company.save(update_fields=[*company_changes, "updated_at"])
                _write_new(backup.with_suffix(".result.json"), result)
        return result
    except Exception:
        # FileField writes are outside the database transaction. Remove only our new blobs.
        for storage, name in created_files:
            storage.delete(name)
        raise
