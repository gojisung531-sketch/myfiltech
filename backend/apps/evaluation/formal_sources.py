"""Current formal evidence, retaining human review and scope limitations."""

import json
from dataclasses import replace

from django.core.serializers.json import DjangoJSONEncoder

from apps.documents.locations import SourceLocator


def _anchors(locations):
    result = {}
    for loc in locations:
        key = (loc.get("document_id"), loc.get("declared_page"), loc.get("quote"))
        if key not in result:
            result[key] = {
                k: loc.get(k)
                for k in (
                    "document_id",
                    "document_sha256",
                    "declared_page",
                    "quote",
                    "status",
                    "quote_status",
                    "source_verification",
                    "record_value_consistency",
                )
            }
            result[key]["fields"] = []
        result[key]["fields"] = sorted(set(result[key]["fields"] + loc.get("fields", [])))
    return list(result.values())


def catalog(ctx):
    if hasattr(ctx, "_formal_catalog"):
        return ctx._formal_catalog
    locator = SourceLocator()
    company = ctx.company
    data = {
        "reference_date": str(ctx.reference_date),
        "is_simulation": ctx.is_simulation,
        "company": {
            f.name: getattr(company, f.name)
            for f in company._meta.concrete_fields
            if f.name not in {"created_at", "updated_at"}
        },
        "company_sources": _anchors(locator.manual_locations(company=company)),
        "certificates": [],
        "limitations": [
            "보유와 요구 충족은 별개. 명의·품목/공장·제작/정비·기간·외부 확인 조건을 각각 대조한다.",
            "인용은 B6A 사람 검토 전사이며 OCR 일치/진위 검증이 아니다. 없는 쪽·인용을 생성하지 않는다.",
            "회사자료 전체가 현재 입력이다. 직접 근거 미확인을 회사 미보유로 바꾸지 않는다.",
            "현재 날짜의 과거 공고 시뮬레이션이며 당시 자격을 입증하지 않는다.",
        ],
    }
    for cert in ctx.certificates:
        values = {
            f.name: getattr(cert, f.name)
            for f in cert._meta.concrete_fields
            if f.name not in {"source_document", "created_at", "updated_at"}
        }
        values.update(
            source_document_id=cert.source_document_id,
            status=cert.status_on(ctx.reference_date, ctx.expiring_days),
            sources=_anchors(locator.manual_locations(certificate=cert)),
        )
        data["certificates"].append(values)
    ctx._formal_catalog = json.loads(json.dumps(data, cls=DjangoJSONEncoder, ensure_ascii=False))
    return ctx._formal_catalog


def certificate_refs(cert):
    refs = []
    for source in cert["sources"]:
        if (
            source["source_verification"] == "VERIFIED"
            and source["record_value_consistency"] == "MATCHES_REVIEW"
            and source["status"] == "MANUAL_REVIEWED_PAGE"
        ):
            refs.append(
                {
                    "type": "certificate",
                    "id": cert["id"],
                    "label": f"{cert['name']} ({cert['cert_no']})",
                    "document_id": source["document_id"],
                    "page": source["declared_page"],
                    "quote": source["quote"],
                    "source_sha256": source["document_sha256"],
                    "quote_verification": source["quote_status"],
                }
            )
    return refs


def rule_with_formal_sources(requirement, result, ctx):
    """Enrich this execution only; never backfill old saved evidence."""
    if result is None:
        return None
    kind = (requirement.normalized or {}).get("cert_type")
    if not kind or kind == "G2B_ITEM":
        return result
    certs = [c for c in catalog(ctx)["certificates"] if c["cert_type"] == kind]
    used = result.trace.get("assessment", {}).get("certificate_ids_used")
    if used is not None:
        certs = [c for c in certs if c["id"] in used]
    if not certs:
        return result
    refs = [r for c in certs for r in certificate_refs(c)]
    values = "; ".join(
        f"{c['name']} {c['cert_no']}; 명의 {c['holder']}; 범위 {c['scope']}; "
        f"기간 {c['valid_from'] or '시작 미상'}~{c['valid_until'] or '종료 미상'}"
        for c in certs
    )
    trace = {
        **result.trace,
        "formal_certificates": certs,
        "reference_date": str(ctx.reference_date),
    }
    invalid = any(
        not certificate_refs(c)
        or not c["holder"]
        or not ctx.company.name
        or _holder(ctx.company.name) not in _holder(c["holder"])
        or (c["valid_from"] and c["valid_from"] > str(ctx.reference_date))
        for c in certs
    )
    return replace(
        result,
        verdict="NEEDS_CONFIRMATION" if invalid else result.verdict,
        rationale=result.rationale
        + (
            " 현재 정식 증서의 명의·범위·기간·출처를 함께 제시합니다. "
            "등록 사실만으로 공공구매망 확인·제안 품목/공장 적용·절차 완료를 확정하지 않습니다."
        )
        + (" 명의/기간/검토 출처의 추가 확인이 필요합니다." if invalid else ""),
        company_value=values,
        evidences=[e for e in result.evidences if e.get("type") != "certificate"] + refs,
        trace=trace,
    )


def _holder(value):
    for token in ("주식회사", "(주)", "㈜", " ", "\t", "\n"):
        value = value.replace(token, "")
    return value


def validate_judgment(out, ctx, requirement):
    """Only exact registered manual citations survive. No source inventions."""
    allowed = {
        (r["type"], r["id"], r["page"], r["quote"]): r
        for cert in catalog(ctx)["certificates"]
        for r in certificate_refs(cert)
    }
    refs, rejected = [], 0
    for ref in out.get("evidence_refs") or []:
        key = (ref.get("type"), ref.get("id"), ref.get("page"), ref.get("quote"))
        source = allowed.get(key)
        if source and ref.get("document_id", source["document_id"]) == source["document_id"]:
            refs.append(source)
        else:
            rejected += 1
    # These unresolved categories have no deterministic applicability/fulfilment check.
    # Even a real certificate cannot establish warranty, price/score or inspection completion.
    reason = (
        f"현재 정식 회사정보·인증 {len(ctx.certificates)}건·제품 {len(ctx.products)}개를 참조했습니다. "
        f"'{requirement.title}'의 적용 범위와 이행 완료는 이 입력만으로 확정할 수 없습니다. "
        "보유 자료 자체의 부재나 실제 미달을 뜻하지 않으며 담당자 확인이 필요합니다."
    )
    return {
        **out,
        "verdict": "NEEDS_CONFIRMATION",
        "company_value": "현재 정식 자료 참조; 해당 요건 이행 미확정",
        "rationale": reason,
        "auto_answer": "확인 필요 — " + reason,
        "action_items": [f"내부 담당자가 '{requirement.title}'의 적용·이행 및 직접 증빙 확인"],
        "clarification_question": "",
        "evidence_refs": refs,
        "_source_validation": {
            "mode": "FORMAL_CURRENT_SOURCES",
            "accepted_refs": len(refs),
            "rejected_refs": rejected,
            "generated_details_not_published": True,
            "semantic_fulfilment_verified": False,
        },
    }
