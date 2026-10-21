"""Map document metadata onto company models (specs/06 §6).

preview() returns the planned changes without saving; apply() saves them.
Metadata values come from DocumentMetadata rows, so admin edits are respected.
"""

import re
from dataclasses import dataclass, field
from datetime import date

from django.db import transaction

from apps.documents.extractors.company import classify_filter_type, standard_family
from apps.documents.models import Document

from .models import Certificate, CertType, Company, DeliveryRecord, PlantType, Product, TestReport

POWER_PLANT_PATTERN = r"발전|화력|복합|열병합|지역난방"


class MappingError(Exception):
    pass


@dataclass
class Change:
    model: str
    lookup: str
    action: str  # create / update / unchanged / replace
    changes: dict = field(default_factory=dict)  # field: [old, new]

    def as_dict(self) -> dict:
        return {
            "model": self.model,
            "lookup": self.lookup,
            "action": self.action,
            "changes": self.changes,
        }


def metadata_values(document: Document) -> dict:
    return {m.key: m.value for m in document.metadata.all()}


def _to_date(value) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _text(value) -> str:
    return "" if value is None else str(value)


# ---- per-category field builders ---------------------------------------------------


def _product_fields(meta: dict) -> dict:
    dim = meta.get("dimension") or {}
    return {
        "name": _text(meta.get("product_name")),
        "filter_type": meta.get("filter_type") or classify_filter_type(meta.get("product_name")),
        "application": _text(meta.get("application")),
        "width_mm": dim.get("w"),
        "height_mm": dim.get("h"),
        "depth_mm": dim.get("d"),
        "diameter_mm": dim.get("dia"),
        "diameter2_mm": dim.get("dia2"),
        "length_mm": dim.get("len"),
        "dimension_text": _text(dim.get("raw")),
        "media": _text(meta.get("media")),
        "frame_material": _text(meta.get("frame_material")),
        "frame_options": meta.get("frame_options") or [],
        "gasket": _text(meta.get("gasket")),
        "rated_airflow_m3h": meta.get("rated_airflow_m3h"),
        "initial_dp_pa": meta.get("initial_dp_pa"),
        "final_dp_pa": meta.get("final_dp_pa"),
        "airflow_dp_curve": meta.get("airflow_dp_curve") or [],
        "iso16890_class": _text(meta.get("iso16890_class")),
        "iso29461_class": _text(meta.get("iso29461_class")),
        "en1822_class": _text(meta.get("en1822_class")),
        "en779_class": _text(meta.get("en779_class")),
        "max_temp_c": meta.get("max_temp_c"),
        "max_rh": meta.get("max_rh"),
        "fire_rating": _text(meta.get("fire_rating")),
        "revision": _text(meta.get("revision")),
    }


def _test_report_fields(meta: dict) -> dict:
    standard = _text(meta.get("standard"))
    notes = _text(meta.get("notes"))
    dim = meta.get("sample_dimension") or {}
    return {
        "model_no_text": _text(meta.get("model_no")),
        "product": Product.objects.filter(model_no=meta.get("model_no")).first(),
        "sample_name": _text(meta.get("sample_name")),
        "sample_dimension": _text(dim.get("raw") if isinstance(dim, dict) else dim),
        "standard": standard,
        "standard_family": standard_family(standard),
        "is_obsolete_standard": "폐지" in standard or standard_family(standard) == "EN779",
        "is_official_certification": not ("준용" in standard or "준용" in notes),
        "test_date": _to_date(meta.get("test_date")),
        "issue_date": _to_date(meta.get("issue_date")),
        "lab_name": _text(meta.get("lab_name")),
        "lab_accreditation": _text(meta.get("lab_accreditation")),
        "result_class": _text(meta.get("result_class")),
        "test_airflow_m3h": meta.get("test_airflow_m3h"),
        "initial_dp_pa": meta.get("initial_dp_pa"),
        "results": meta.get("results") or {},
        "conditions": meta.get("conditions") or {},
        "notes": notes,
    }


CERT_TYPES = [
    (r"ISO\s*9001", CertType.ISO9001),
    (r"ISO\s*14001", CertType.ISO14001),
    (r"ISO\s*45001", CertType.ISO45001),
    (r"직접\s*생산", CertType.DIRECT_PRODUCTION),
    (r"중소기업\s*확인|소상공인\s*확인", CertType.SME),
    (r"\bKS\b", CertType.KS),
    (r"특허", CertType.PATENT),
]


def cert_type_for(*texts: str) -> str:
    joined = " ".join(t for t in texts if t)
    for pattern, code in CERT_TYPES:
        if re.search(pattern, joined):
            return code
    return CertType.OTHER


def _certificate_fields(meta: dict) -> dict:
    name, standard = _text(meta.get("cert_name")), _text(meta.get("standard"))
    return {
        "name": name,
        "cert_type": cert_type_for(standard, name),
        "standard": standard,
        "holder": _text(meta.get("holder")),
        "scope": _text(meta.get("scope")),
        "product_codes": meta.get("product_codes") or [],
        "issuer": _text(meta.get("issuer")),
        "issue_date": _to_date(meta.get("issue_date")),
        "valid_from": _to_date(meta.get("valid_from")),
        "valid_until": _to_date(meta.get("valid_until")),
    }


def plant_type_for(text: str) -> str:
    if "복합" in text:
        return PlantType.CCPP
    if re.search(r"열병합|지역난방", text):
        return PlantType.CHP
    if "화력" in text:
        return PlantType.THERMAL
    return PlantType.OTHER


def _delivery_rows(meta: dict) -> list[dict]:
    rows = []
    for record in meta.get("records") or []:
        context = f"{record.get('client', '')} {record.get('project_name', '')}"
        rows.append(
            {
                "delivered_ym": _text(record.get("delivered_ym")),
                "client": _text(record.get("client")),
                "project_name": _text(record.get("project_name")),
                "item_desc": _text(record.get("item_desc")),
                "model_nos": record.get("models") or [],
                "quantity": record.get("quantities") or [],
                "is_power_plant": bool(re.search(POWER_PLANT_PATTERN, context)),
                "plant_type": plant_type_for(context),
                "notes": _text(record.get("notes")),
            }
        )
    return rows


# ---- preview / apply -----------------------------------------------------------------


def _serializable(value):
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Product):
        return value.model_no
    return value


def _diff(instance, fields: dict) -> dict:
    changes = {}
    for name, new in fields.items():
        old = getattr(instance, name, None) if instance is not None else None
        if old != new and not (old in (None, "", [], {}) and new in (None, "", [], {})):
            changes[name] = [_serializable(old), _serializable(new)]
    return changes


def _upsert_plan(model, lookup_field: str, lookup_value, fields: dict) -> Change:
    if not lookup_value:
        raise MappingError(f"필수 값 '{lookup_field}'이(가) 비어 있어 반영할 수 없습니다.")
    instance = model.objects.filter(**{lookup_field: lookup_value}).first()
    changes = _diff(instance, fields)
    action = "create" if instance is None else ("update" if changes else "unchanged")
    return Change(model._meta.label, str(lookup_value), action, changes)


def preview(document: Document) -> list[Change]:
    code = document.category.code if document.category else None
    meta = metadata_values(document)
    if code == "datasheet":
        return [_upsert_plan(Product, "model_no", meta.get("model_no"), _product_fields(meta))]
    if code == "test_report":
        fields = _test_report_fields(meta)
        return [_upsert_plan(TestReport, "report_no", meta.get("report_no"), fields)]
    if code == "certificate":
        fields = _certificate_fields(meta)
        return [_upsert_plan(Certificate, "cert_no", meta.get("cert_no"), fields)]
    if code == "delivery_record":
        rows = _delivery_rows(meta)
        if not rows:
            raise MappingError("납품실적 행이 없습니다.")
        existing = DeliveryRecord.objects.filter(source_document=document).count()
        return [
            Change(
                DeliveryRecord._meta.label,
                document.display_name,
                "replace",
                {"rows": [existing, len(rows)]},
            )
        ]
    if code == "company_profile":
        company = Company.load()
        fields = {
            k: _text(meta.get(k))
            for k in ("name", "ceo", "business_no", "address", "phone", "email", "main_products")
            if meta.get(k)
        }
        changes = _diff(company, fields)
        return [Change(Company._meta.label, "회사", "update" if changes else "unchanged", changes)]
    raise MappingError("이 문서 분류는 회사 자료로 반영할 수 없습니다.")


@transaction.atomic
def apply(document: Document) -> list[Change]:
    plan = preview(document)
    code = document.category.code
    meta = metadata_values(document)
    if code == "datasheet":
        product, _ = Product.objects.update_or_create(
            model_no=meta["model_no"],
            defaults={**_product_fields(meta), "source_document": document},
        )
        TestReport.objects.filter(model_no_text=product.model_no, product__isnull=True).update(
            product=product
        )
    elif code == "test_report":
        TestReport.objects.update_or_create(
            report_no=meta["report_no"],
            defaults={**_test_report_fields(meta), "source_document": document},
        )
    elif code == "certificate":
        Certificate.objects.update_or_create(
            cert_no=meta["cert_no"],
            defaults={**_certificate_fields(meta), "source_document": document},
        )
    elif code == "delivery_record":
        DeliveryRecord.objects.filter(source_document=document).delete()
        for row in _delivery_rows(meta):
            record = DeliveryRecord.objects.create(**row, source_document=document)
            record.products.set(Product.objects.filter(model_no__in=row["model_nos"]))
    elif code == "company_profile":
        company = Company.load()
        for name, (_, new) in plan[0].changes.items():
            setattr(company, name, new)
        company.save()
        company.source_documents.add(document)
    document.status = Document.Status.REVIEWED
    document.save(update_fields=["status", "updated_at"])
    return plan


def link_delivery_products() -> None:
    """Re-link delivery rows to products (products may be created after the records)."""
    for record in DeliveryRecord.objects.all():
        record.products.set(Product.objects.filter(model_no__in=record.model_nos))


CONTACT_PATTERN = re.compile(r"연락처:\s*([\d-]{9,}),\s*([\w.+-]+@[\w-]+\.[\w.]+)")
COMPANY_NAME_PATTERN = re.compile(r"(\(주\)\s*[가-힣A-Za-z]+)")


def fill_company_from_documents(documents) -> Company:
    """Fill blank Company fields from contact lines in company documents (specs/12 §2.1)."""
    company = Company.load()
    for document in documents:
        text = document.extracted_text or ""
        if not company.name:
            match = COMPANY_NAME_PATTERN.search(text)
            if match:
                company.name = match.group(1).replace(" ", "")
        contact = CONTACT_PATTERN.search(text)
        if contact:
            company.phone = company.phone or contact.group(1)
            company.email = company.email or contact.group(2)
    company.save()
    return company
