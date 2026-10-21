"""② 회사 자료 비교 table (specs/05 §3 ②): requirement vs product spec / reports / certs / records."""

from apps.company.models import Certificate, DeliveryRecord, TestReport

from .context import EvaluationContext
from .evidence import target_product
from .grades import family_of, product_grades


def _num(value) -> str:
    return f"{value:,.0f}" if isinstance(value, (int, float)) else "-"


def product_spec(product, category: str) -> str:
    if product is None:
        return ""
    if category == "DIMENSION":
        return product.dimension_text
    if category == "FILTER_TYPE":
        return product.get_filter_type_display()
    if category in ("FILTER_GRADE", "EFFICIENCY"):
        return ", ".join(str(g) for g in product_grades(product))
    if category == "PRESSURE_DROP":
        return (
            f"초기 {_num(product.initial_dp_pa)} Pa @{_num(product.rated_airflow_m3h)} m³/h"
            f" / 권장 최종 {_num(product.final_dp_pa)} Pa"
        )
    if category == "AIRFLOW":
        return f"정격 {_num(product.rated_airflow_m3h)} m³/h"
    if category == "MATERIAL":
        return " / ".join(
            f"{label} {value}"
            for label, value in (
                ("여재", product.media),
                ("프레임", product.frame_material),
                ("개스킷", product.gasket),
            )
            if value
        )
    if category == "ENVIRONMENT":
        return f"최고 {_num(product.max_temp_c)} ℃ / {_num(product.max_rh)} %RH"
    if category == "FIRE_RATING":
        return product.fire_rating
    return ""


def _report_ref(report) -> dict:
    return {
        "id": report.pk,
        "label": f"{report.report_no} ({report.standard_family} {report.result_class})",
        "document_id": report.source_document_id,
    }


def _cert_ref(cert, ctx) -> dict:
    return {
        "id": cert.pk,
        "label": f"{cert.name or cert.cert_type} {cert.cert_no} (~{cert.valid_until or '?'})",
        "status": cert.status_on(ctx.reference_date, ctx.expiring_days),
        "document_id": cert.source_document_id,
    }


def _record_ref(record) -> dict:
    return {
        "id": record.pk,
        "label": f"{record.delivered_ym} {record.client} {', '.join(record.model_nos or [])}",
        "document_id": record.source_document_id,
    }


def _evidence_ids(evaluation, kind: str) -> list[int]:
    if evaluation is None:
        return []
    return [
        e.get("id") for e in evaluation.evidences or [] if e.get("type") == kind and e.get("id")
    ]


def _requirement_value(requirement) -> str:
    return requirement.requirement_text or requirement.title


def comparison(bid) -> dict:
    ctx = EvaluationContext.for_bid(bid)
    reports = {r.pk: r for r in TestReport.objects.all()}
    certs = {c.pk: c for c in Certificate.objects.all()}
    records = {r.pk: r for r in DeliveryRecord.objects.prefetch_related("products")}

    items = []
    for item in bid.items.select_related("matched_product").prefetch_related(
        "product_matches__product"
    ):
        items.append(
            {
                "id": item.pk,
                "item_no": item.item_no,
                "name": item.name,
                "spec_text": item.spec_text,
                "quantity": item.quantity,
                "unit": item.unit,
                "matched_product": item.matched_product_id,
                "matched_model_no": item.matched_product.model_no if item.matched_product else None,
                "candidates": [
                    {
                        "product": m.product_id,
                        "model_no": m.product.model_no,
                        "name": m.product.name,
                        "score": m.score,
                        "reason": m.reason,
                    }
                    for m in item.product_matches.all()
                ],
            }
        )

    rows = []
    requirements = bid.requirements.select_related("item__matched_product", "evaluation")
    for requirement in requirements:
        evaluation = getattr(requirement, "evaluation", None)
        product = target_product(requirement, ctx)
        category = requirement.category

        report_ids = _evidence_ids(evaluation, "test_report")
        if (
            not report_ids
            and product is not None
            and category
            in (
                "FILTER_GRADE",
                "EFFICIENCY",
                "PRESSURE_DROP",
                "TEST_STANDARD",
                "FIRE_RATING",
            )
        ):
            family = family_of((requirement.normalized or {}).get("standard") or "")
            report_ids = [
                r.pk for r in ctx.reports_for(product) if not family or r.standard_family == family
            ]
        cert_ids = _evidence_ids(evaluation, "certificate")
        if not cert_ids and category == "CERTIFICATION":
            cert_type = (requirement.normalized or {}).get("cert_type")
            cert_ids = [c.pk for c in ctx.certificates if c.cert_type == cert_type]
        record_ids = _evidence_ids(evaluation, "delivery_record")
        if not record_ids and category == "TRACK_RECORD":
            record_ids = [r.pk for r in ctx.delivery_records[:5]]

        rows.append(
            {
                "requirement_id": requirement.pk,
                "category": category,
                "category_label": requirement.get_category_display(),
                "title": requirement.title,
                "requirement_value": _requirement_value(requirement),
                "is_mandatory": requirement.is_mandatory,
                "item_id": requirement.item_id,
                "item_label": str(requirement.item) if requirement.item_id else None,
                "product": {"id": product.pk, "model_no": product.model_no} if product else None,
                "product_spec": product_spec(product, category),
                "test_reports": [_report_ref(reports[i]) for i in report_ids if i in reports],
                "certificates": [_cert_ref(certs[i], ctx) for i in cert_ids if i in certs],
                "delivery_records": [_record_ref(records[i]) for i in record_ids if i in records],
                "verdict": evaluation.verdict if evaluation else None,
                "risk_level": evaluation.risk_level if evaluation else None,
                "company_value": evaluation.company_value if evaluation else "",
            }
        )
    return {
        "reference_date": str(ctx.reference_date),
        "is_simulation": ctx.is_simulation,
        "items": items,
        "rows": rows,
    }
