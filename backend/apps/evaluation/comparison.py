"""② 회사 자료 비교 table (specs/05 §3 ②): requirement vs product spec / reports / certs / records."""

from apps.company.models import Certificate, DeliveryRecord, TestReport
from apps.core.freshness import FreshnessReader
from apps.documents.locations import SourceLocator

from .context import EvaluationContext
from .evidence import (
    evidence_document_map,
    manufacturer_inputs,
    stored_evidence_locations,
    target_product,
)
from .grades import family_of, product_grades


def _num(value) -> str:
    return f"{value:,.0f}" if isinstance(value, (int, float)) else "-"


def product_spec(product, category: str) -> str:
    if product is None:
        return ""
    claims = (product.extra or {}).get("manufacturer_claims") or {}
    if claims and category in ("EFFICIENCY", "PRESSURE_DROP", "AIRFLOW", "OTHER"):
        return claims.get(category, {}).get("display", "")
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


def _cert_ref(cert, ctx, locator, saved_ids) -> dict:
    return {
        "id": cert.pk,
        "label": f"{cert.name or cert.cert_type} {cert.cert_no} (~{cert.valid_until or '?'})",
        "status": cert.status_on(ctx.reference_date, ctx.expiring_days),
        "document_id": cert.source_document_id,
        "relation_to_evaluation": "SAVED_ID_REFERENCE"
        if cert.pk in saved_ids
        else "CURRENT_REFERENCE_ONLY",
        "evidence_locations": locator.manual_locations(certificate=cert),
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
    ctx = EvaluationContext.for_bid(bid, read_only=True)
    freshness = FreshnessReader()
    locator = SourceLocator()
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
    requirements = list(
        bid.requirements.select_related(
            "item__matched_product", "evaluation__analysis_run", "source_attachment__document"
        )
    )
    doc_map = evidence_document_map(
        getattr(r, "evaluation", None).evidences
        for r in requirements
        if getattr(r, "evaluation", None)
    )
    for requirement in requirements:
        evaluation = getattr(requirement, "evaluation", None)
        product = target_product(requirement, ctx)
        category = requirement.category
        candidates = manufacturer_inputs(requirement, ctx)

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
        saved_cert_ids = set(cert_ids)
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
                "product_spec": product_spec(product, category)
                if product
                else "; ".join(
                    f"비교 후보 {p['model_no']} (제조사 기재): "
                    f"{product_spec(next(v for v in ctx.products if v.pk == p['product_id']), category)}"
                    for p in candidates
                ),
                "comparison_candidates": candidates,
                "interpretation_review": (requirement.normalized or {}).get(
                    "interpretation_review"
                ),
                "comparison_trace": evaluation.rule_trace if evaluation else {},
                "rationale": evaluation.rationale if evaluation else "",
                "test_reports": [_report_ref(reports[i]) for i in report_ids if i in reports],
                "certificates": [
                    _cert_ref(certs[i], ctx, locator, saved_cert_ids)
                    for i in cert_ids
                    if i in certs
                ],
                "source_location": locator.requirement(requirement),
                "stored_evidence_locations": stored_evidence_locations(
                    evaluation.evidences if evaluation else [], doc_map, locator
                ),
                "current_company_locations": [
                    location
                    for location in locator.manual_locations(company=ctx.company)
                    if category == "CERTIFICATION"
                    and set(location["fields"])
                    & {"is_sme", "sme_cert_valid_until", "g2b_registered_items"}
                ],
                "stored_evaluation_updated_at": str(evaluation.updated_at) if evaluation else None,
                "current_references_revise_stored_evaluation": False,
                "delivery_records": [_record_ref(records[i]) for i in record_ids if i in records],
                "verdict": evaluation.verdict if evaluation else None,
                "risk_level": evaluation.risk_level if evaluation else None,
                "company_value": evaluation.company_value if evaluation else "",
            }
        )
        row = rows[-1]
        row["freshness"] = (
            freshness.result(evaluation)
            if evaluation
            else {"status": "UNKNOWN", "reasons": [{"code": "NO_SAVED_EVALUATION"}]}
        )
        row["stored_result"] = {
            key: row[key]
            for key in (
                "verdict",
                "risk_level",
                "company_value",
                "rationale",
                "stored_evidence_locations",
            )
        }
        row["stored_result"]["freshness"] = row["freshness"]
        row["current_reference"] = {
            key: row[key]
            for key in (
                "product",
                "product_spec",
                "comparison_candidates",
                "certificates",
                "test_reports",
                "delivery_records",
                "current_company_locations",
            )
        }
        row["temporal_alignment"] = "SEPARATE_CURRENT_REFERENCE_AND_STORED_RESULT"
    return {
        "reference_date": str(ctx.reference_date),
        "is_simulation": ctx.is_simulation,
        "items": items,
        "rows": rows,
        "freshness": freshness.evaluations(bid.pk),
        "legacy_flat_fields_mix_time_contexts": True,
    }
