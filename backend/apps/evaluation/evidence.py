"""Evidence candidates per requirement (specs/08 §4)."""

from .context import EvaluationContext

# Requirements about the product itself; the rest (qualification, documents, delivery…)
# are compared with company-wide data.
PRODUCT_CATEGORIES = {
    "DIMENSION",
    "FILTER_TYPE",
    "FILTER_GRADE",
    "EFFICIENCY",
    "PRESSURE_DROP",
    "AIRFLOW",
    "MATERIAL",
    "ENVIRONMENT",
    "FIRE_RATING",
}


def target_product(requirement, ctx: EvaluationContext):
    """The item's matched product; for bid-level product requirements, the bid's only
    matched product (specs/08 §4)."""
    item = requirement.item
    if item is not None:
        return item.matched_product
    if requirement.category not in PRODUCT_CATEGORIES:
        return None
    matched = {p.pk: p for p in ctx.matched_products}
    return next(iter(matched.values())) if len(matched) == 1 else None


def product_evidence(product) -> dict:
    return {
        "type": "product",
        "id": product.pk,
        "label": f"{product.model_no} {product.name} 기술사양서",
        "page": 1,
        "quote": product.dimension_text,
    }


def report_evidence(report, quote: str = "") -> dict:
    return {
        "type": "test_report",
        "id": report.pk,
        "label": f"시험성적서 {report.report_no} ({report.standard})",
        "page": 1,
        "quote": quote or f"{report.result_class}",
    }


def record_evidence(record, quote: str = "") -> dict:
    return {
        "type": "delivery_record",
        "id": record.pk,
        "label": f"{record.delivered_ym} {record.client} {record.project_name}",
        "page": 1,
        "quote": quote or ", ".join(record.model_nos or []),
    }


def _product_summary(product) -> dict:
    fields = [
        "model_no",
        "name",
        "filter_type",
        "application",
        "dimension_text",
        "dimension_variants",
        "media",
        "frame_material",
        "frame_options",
        "gasket",
        "rated_airflow_m3h",
        "initial_dp_pa",
        "final_dp_pa",
        "airflow_dp_curve",
        "iso16890_class",
        "iso29461_class",
        "en1822_class",
        "en779_class",
        "ashrae_merv",
        "max_temp_c",
        "max_rh",
        "fire_rating",
    ]
    data = {f: getattr(product, f) for f in fields}
    return {"id": product.pk, **{k: v for k, v in data.items() if v not in (None, "", [], {})}}


def _report_summary(report) -> dict:
    return {
        "id": report.pk,
        "report_no": report.report_no,
        "model_no": report.product.model_no if report.product else report.model_no_text,
        "standard": report.standard,
        "standard_family": report.standard_family,
        "is_obsolete_standard": report.is_obsolete_standard,
        "is_official_certification": report.is_official_certification,
        "issue_date": str(report.issue_date or ""),
        "lab": f"{report.lab_name} {report.lab_accreditation}".strip(),
        "result_class": report.result_class,
        "test_airflow_m3h": report.test_airflow_m3h,
        "results": report.results,
        "notes": report.notes,
    }


def _record_summary(record) -> dict:
    return {
        "id": record.pk,
        "delivered_ym": record.delivered_ym,
        "client": record.client,
        "project_name": record.project_name,
        "model_nos": record.model_nos,
        "quantity": record.quantity,
        "amount_krw": record.amount_krw,
        "is_power_plant": record.is_power_plant,
        "notes": record.notes,
    }


def company_evidence(requirement, ctx: EvaluationContext) -> dict:
    """Compact company data the LLM may cite for one requirement."""
    product = target_product(requirement, ctx)
    if product is not None:
        return {
            "product": _product_summary(product),
            "test_reports": [_report_summary(r) for r in ctx.reports_for(product)],
            "delivery_records": [
                _record_summary(r) for r in ctx.delivery_records if product in r.products.all()
            ],
        }
    company = ctx.company
    return {
        "company": {
            "name": company.name,
            "is_sme": company.is_sme,
            "sme_cert_valid_until": str(company.sme_cert_valid_until or ""),
            "g2b_registered_items": company.g2b_registered_items,
        },
        "certificates": [
            {
                "id": c.pk,
                "cert_no": c.cert_no,
                "name": c.name,
                "cert_type": c.cert_type,
                "scope": c.scope,
                "product_codes": c.product_codes,
                "valid_until": str(c.valid_until or ""),
                "status": c.status_on(ctx.reference_date, ctx.expiring_days),
            }
            for c in ctx.certificates
        ],
        "delivery_records": [_record_summary(r) for r in ctx.delivery_records],
        "test_reports": [
            {k: v for k, v in _report_summary(r).items() if k != "results"}
            for r in ctx.test_reports
        ],
        "products": [{"id": p.pk, "model_no": p.model_no, "name": p.name} for p in ctx.products],
    }


def evidence_document_map(evidence_lists) -> dict[tuple[str, int], int]:
    """{(type, id): document_id} for evidence that points at a stored document, so the UI can
    open it in the document viewer. One query per evidence type."""
    from apps.bids.models import BidAttachment
    from apps.company.models import Certificate, DeliveryRecord, Product, TestReport

    models = {
        "product": (Product, "source_document_id"),
        "test_report": (TestReport, "source_document_id"),
        "certificate": (Certificate, "source_document_id"),
        "delivery_record": (DeliveryRecord, "source_document_id"),
        "bid_quote": (BidAttachment, "document_id"),
    }
    wanted: dict[str, set[int]] = {}
    for evidences in evidence_lists:
        for e in evidences or []:
            if e.get("type") in models and e.get("id"):
                wanted.setdefault(e["type"], set()).add(e["id"])
    result = {}
    for kind, ids in wanted.items():
        model, field = models[kind]
        for pk, document_id in model.objects.filter(pk__in=ids).values_list("pk", field):
            if document_id:
                result[(kind, pk)] = document_id
    return result
