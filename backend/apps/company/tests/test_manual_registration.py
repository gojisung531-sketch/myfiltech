"""Isolated import safety tests; synthetic PDF bytes never enter the development DB."""

import copy
import hashlib
from pathlib import Path

import pytest

from apps.company.manual_registration import register_reviewed
from apps.company.models import Certificate, Company
from apps.core.models import Job
from apps.documents.models import Document, DocumentMetadata, MetadataSchema
from apps.llm.models import LLMCallLog

pytestmark = pytest.mark.django_db


@pytest.fixture
def reviewed(tmp_path, settings):
    settings.BACKEND_DIR = tmp_path
    (tmp_path / ".venv").mkdir()
    # A minimal one-page PDF, with real cross-reference offsets.
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] >>",
    ]
    data = b"%PDF-1.4\n"
    offsets = []
    for index, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data += f"{index} 0 obj\n".encode() + obj + b"\nendobj\n"
    start = len(data)
    data += b"xref\n0 4\n0000000000 65535 f \n"
    data += b"".join(f"{offset:010} 00000 n \n".encode() for offset in offsets)
    data += f"trailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n".encode()
    path = tmp_path / "source.pdf"
    path.write_bytes(data)
    evidence = [
        {
            "source": "source",
            "page": 1,
            "quote": "Test source review",
            "method": "VISUAL_REVIEW",
            "fields": ["cert_no", "name", "cert_type", "holder", "scope", "issuer"],
        }
    ]
    source = {
        "key": "source",
        "path": str(path),
        "sha256": hashlib.sha256(data).hexdigest(),
        "page_count": 1,
        "category": "certificate",
        "records": [
            {
                "decision": "REGISTER",
                "values": {
                    "cert_no": "SYNTHETIC-1",
                    "name": "Patent",
                    "cert_type": "PATENT",
                    "holder": "Test holder",
                    "scope": "Test scope",
                    "issuer": "Test issuer",
                },
                "evidence": evidence,
                "unknown_fields": ["valid_until"],
            }
        ],
    }
    Company.objects.create(name="Existing manual name")
    MetadataSchema.objects.get_or_create(
        code="certificate", defaults={"name": "Certificates", "owner_type": "COMPANY"}
    )
    manifest = {
        "version": 1,
        "sources": [source],
        "company": {
            "name": {"value": "Reviewed name", "evidence": evidence},
            "phone": {"value": "Test phone", "evidence": evidence},
        },
    }
    return manifest, tmp_path


def apply(reviewed, name="before.json"):
    manifest, root = reviewed
    return register_reviewed(manifest, apply=True, backup=root / ".venv" / name)


def snapshot():
    return {
        model._meta.label: list(model.objects.order_by("pk").values())
        for model in [Company, Certificate, Document, DocumentMetadata, Job, LLMCallLog]
    }


def test_dry_run_has_no_side_effects(reviewed):
    before = snapshot()
    result = register_reviewed(reviewed[0])
    assert result["new_documents"] == result["new_certificates"] == 1
    assert snapshot() == before
    assert not list((reviewed[1] / ".venv").iterdir())


def test_apply_rerun_preserves_manual_edits_and_unknown_dates(reviewed):
    initial_jobs, initial_logs = Job.objects.count(), LLMCallLog.objects.count()
    result = apply(reviewed)
    cert = Certificate.objects.get()
    assert cert.cert_type == "PATENT" and cert.valid_until is None and cert.status_on() == "UNKNOWN"
    assert (
        cert.source_document
        and Path(cert.source_document.file.path).read_bytes()
        == Path(reviewed[0]["sources"][0]["path"]).read_bytes()
    )
    assert Company.objects.get().name == "Existing manual name"
    assert result["company_fields_preserved"] == ["name"]
    cert.scope = "Staff correction"
    cert.save()
    Company.objects.filter(pk=1).update(phone="Staff phone")
    before = snapshot()
    result = apply(reviewed, "rerun.json")
    assert result["new_documents"] == result["new_certificates"] == result["new_metadata"] == 0
    assert result["company_fields_changed"] == []
    assert result["preserved_edited_certificates"] == [cert.pk]
    assert snapshot() == before
    assert (Job.objects.count(), LLMCallLog.objects.count()) == (initial_jobs, initial_logs)


def test_number_collision_does_not_adopt_other_source(reviewed):
    Certificate.objects.create(cert_no="SYNTHETIC-1", holder="Manual holder")
    before = snapshot()
    with pytest.raises(ValueError, match="another source"):
        apply(reviewed)
    assert snapshot() == before


def test_same_bytes_under_different_source_keys_are_rejected(reviewed):
    alias = copy.deepcopy(reviewed[0]["sources"][0])
    alias["key"] = "renamed-source"
    reviewed[0]["sources"].append(alias)
    before = snapshot()
    with pytest.raises(ValueError, match="Duplicate source bytes"):
        apply(reviewed)
    assert snapshot() == before


@pytest.mark.parametrize("mutation", ["hash", "page", "number", "date", "evidence"])
def test_invalid_evidence_stops_before_mutation(reviewed, mutation):
    manifest = reviewed[0]
    source = manifest["sources"][0]
    record = source["records"][0]
    if mutation == "hash":
        source["sha256"] = "0" * 64
    elif mutation == "page":
        record["evidence"][0]["page"] = 2
    elif mutation == "number":
        record["values"]["cert_no"] = ""
    elif mutation == "date":
        record["values"]["valid_until"] = "invented"
    else:
        record["evidence"] = []
    before = snapshot()
    with pytest.raises(ValueError):
        apply(reviewed)
    assert snapshot() == before


def test_hold_preserves_original_and_missing_fields_without_formal_row(reviewed):
    source = reviewed[0]["sources"][0]
    record = source["records"][0]
    record.update(decision="HOLD", missing_fields=["cert_no"], reason="Number illegible")
    record["values"]["cert_no"] = ""
    result = apply(reviewed)
    assert Certificate.objects.count() == 0 and Document.objects.count() == 1
    assert result["inventory"][0]["held"] == [
        {"missing_fields": ["cert_no"], "reason": "Number illegible"}
    ]
    assert DocumentMetadata.objects.get(key="manual_registration.b6a").value == source


def test_changed_manifest_cannot_overwrite_review_metadata(reviewed):
    apply(reviewed)
    before = snapshot()
    reviewed[0]["sources"][0]["records"][0]["values"]["scope"] = "Changed proposal"
    with pytest.raises(ValueError, match="metadata differs"):
        apply(reviewed, "changed.json")
    assert snapshot() == before


def test_db_failure_rolls_back_rows_and_only_new_blobs(reviewed, monkeypatch, settings):
    original = DocumentMetadata.objects.create
    before = snapshot()
    calls = []

    def fail(**kwargs):
        calls.append(kwargs["key"])
        if len(calls) == 2:
            raise RuntimeError("Simulated metadata failure")
        return original(**kwargs)

    monkeypatch.setattr(DocumentMetadata.objects, "create", fail)
    with pytest.raises(RuntimeError):
        apply(reviewed)
    assert snapshot() == before
    assert not [p for p in Path(settings.MEDIA_ROOT).rglob("*") if p.is_file()]
    assert (reviewed[1] / ".venv/before.json").exists()


def test_existing_source_is_reused_and_backup_is_exclusive(reviewed):
    apply(reviewed)
    before = snapshot()
    with pytest.raises(ValueError, match="already exists"):
        apply(reviewed)
    assert snapshot() == before
    manifest = copy.deepcopy(reviewed[0])
    manifest["company"]["ceo"] = {
        "value": "Reviewed CEO",
        "evidence": manifest["company"]["phone"]["evidence"],
    }
    result = register_reviewed(
        manifest, apply=True, backup=reviewed[1] / ".venv/new-company-fact.json"
    )
    assert result["new_documents"] == result["new_certificates"] == 0
    assert Company.objects.get().ceo == "Reviewed CEO"
