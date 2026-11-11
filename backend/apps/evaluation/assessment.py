"""Recheck reviewed ambiguities against current inputs; keep work and facts separate.

No selections, requirements, metadata or task completion flags are written here.
"""

import copy
import re
from dataclasses import replace

from apps.documents.locations import SourceLocator

from .evidence import product_evidence

MET = "MET"
UNKNOWN = "NEEDS_CONFIRMATION"
GAP = "NEEDS_SUPPLEMENT"


def missing(key, label, *, choices=None):
    return {"key": key, "label": label, "choices": choices or []}


def task(key, label, timing="", *, conditional=False):
    return {
        "key": key,
        "label": label,
        "timing": timing,
        "state": "CONDITIONAL" if conditional else "OPEN",
        "blocks_current_comparison": False,
        "completion_verified": False,
    }


def check(field, status, required, actual, evidence=None):
    return {
        "field": field,
        "status": status,
        "required": required,
        "actual": actual,
        "evidence": evidence or [],
    }


def _source(req, ctx):
    if not hasattr(ctx, "_assessment_locator"):
        ctx._assessment_locator = SourceLocator()
    locator = ctx._assessment_locator
    original = locator.requirement(req)
    if original["status"] != "QUOTE_NOT_FOUND" or not req.source_attachment_id:
        return original
    from apps.documents.locations import text_digest
    from apps.documents.models import DocumentMetadata

    doc = req.source_attachment.document
    row = DocumentMetadata.objects.filter(
        document=doc, key=f"manual_requirement_revalidation.{req.pk}"
    ).first()
    value = row.value if row else {}
    if (
        not row
        or value.get("requirement_id") != req.pk
        or value.get("original_quote") != req.source_quote
        or value.get("source_sha256") != doc.sha256
        or value.get("text_sha256") != text_digest(doc.extracted_text)
    ):
        return original
    proof = locator.locate(
        doc.pk, value.get("reviewed_quote", ""), role="REVALIDATED_REQUIREMENT_SOURCE"
    )
    if (
        proof["status"] not in {"EXACT_MATCH", "WHITESPACE_MATCH"}
        or proof.get("source_verification") != "VERIFIED"
    ):
        return original
    proof.update(
        original_location=original,
        metadata_id=row.pk,
        quote_origin="EXPLICIT_MANUAL_ADDITIONAL_QUOTE",
        stored_requirement_quote_modified=False,
    )
    return proof


def result(
    req,
    verdict,
    reason,
    *,
    scope="CURRENT_COMPANY",
    checks=(),
    inputs=(),
    tasks=(),
    evidence=(),
    value="",
    ctx=None,
):
    from .rules import RuleResult

    review = (req.normalized or {}).get("interpretation_review")
    remaining = [c["field"] for c in checks if c["status"] == UNKNOWN]
    remaining = list(dict.fromkeys(remaining + [m["key"] for m in inputs]))
    resolved = [c["field"] for c in checks if c["status"] in (MET, GAP)]
    assessment = {
        "schema": "b6e.assessment.v1",
        "scope": scope,
        "current_company_verdict": verdict
        if scope in {"CURRENT_COMPANY", "CURRENT_DOCUMENTED_QUALIFICATION"}
        else "NOT_APPLICABLE",
        "checks": list(checks),
        "missing_inputs": list(inputs),
        "follow_up_tasks": list(tasks),
        "submission_ready": False,
        "final_bid_eligibility_verified": False,
        "interpretation_revalidation": {
            "original_review": review,
            "status": ("PARTIAL" if remaining else "RESOLVED") if resolved else "UNRESOLVED",
            "resolved_parts": resolved,
            "remaining_parts": remaining,
        },
    }
    if scope in {"NOTICE_FACT", "FUTURE_OBLIGATION"} and ctx:
        assessment["notice_source"] = _source(req, ctx)
    return RuleResult(
        verdict,
        "HIGH"
        if verdict == GAP and req.is_mandatory
        else "MEDIUM"
        if verdict == UNKNOWN
        else "LOW",
        reason,
        value,
        action_items=[m["label"] for m in inputs] + [t["label"] for t in tasks],
        evidences=list(evidence),
        trace={"assessment": assessment},
    )


def _sme(req, ctx):
    from .formal_sources import _holder, catalog, certificate_refs

    certs = [c for c in catalog(ctx)["certificates"] if c["cert_type"] == "SME"]
    checks, refs, alternatives = [], [], []
    for c in certs:
        evidence = certificate_refs(c)
        holder = bool(ctx.company.name and _holder(ctx.company.name) == _holder(c["holder"]))
        valid = bool(
            c["valid_from"]
            and c["valid_until"]
            and c["valid_from"] <= str(ctx.reference_date) <= c["valid_until"]
        )
        candidate_checks = [
            check(
                "sme.holder",
                MET if holder and evidence else UNKNOWN,
                ctx.company.name,
                c["holder"],
                evidence,
            ),
            check(
                "sme.category",
                MET
                if ctx.company.is_sme is True
                else GAP
                if ctx.company.is_sme is False
                else UNKNOWN,
                "중소기업/소상공인 일반 참가",
                ctx.company.is_sme,
                evidence,
            ),
            check(
                "sme.validity",
                MET
                if valid
                else GAP
                if c["valid_until"] and c["valid_until"] < str(ctx.reference_date)
                else UNKNOWN,
                str(ctx.reference_date),
                [c["valid_from"], c["valid_until"]],
                evidence,
            ),
        ]
        alternatives.append((candidate_checks, evidence, c["id"]))
    selected_ids = []
    if alternatives:
        checks, refs, selected_id = min(
            alternatives, key=lambda row: sum(c["status"] != MET for c in row[0])
        )
        selected_ids = [selected_id]
    if not checks:
        checks = [
            check("sme.certificate", UNKNOWN, "명의/구분/시작·종료일이 확인되는 SME 증서", None)
        ]
    verdict = (
        GAP
        if any(c["status"] == GAP for c in checks)
        else UNKNOWN
        if any(c["status"] == UNKNOWN for c in checks)
        else MET
    )
    out = result(
        req,
        verdict,
        "일반 중소기업 참가 경로에서 회사 명의·기업 구분·현재 기준일의 증서 기간을 실제 대조했습니다. "
        "조합/특별법인/확인서 신청 중 예외는 일반 경로를 차단하지 않습니다. 공공구매망 조회 및 향후 공고 마감일의 효력은 제출 전 확인 업무로 남습니다.",
        scope="CURRENT_DOCUMENTED_QUALIFICATION",
        checks=checks,
        inputs=[missing("company.sme_certificate", "SME 증서의 미확인 명의/구분/시작·종료일 보완")]
        if verdict == UNKNOWN
        else [],
        tasks=[
            task(
                "sme.portal_and_cutoff",
                "입찰 전 공공구매망 확인 및 새 공고 마감 전일 발급·유효 조건 재확인",
                "입찰 전",
            )
        ],
        evidence=refs,
        value="일반 중소기업 경로의 현재 증서 대조: " + verdict,
    )
    out.trace["assessment"]["qualification_routes"] = {
        "selected_for_comparison": "GENERAL_SME",
        "general_verdict": verdict,
        "exceptions": [
            {
                "route": r,
                "status": "NOT_NEEDED_FOR_GENERAL_ROUTE" if verdict == MET else "NOT_ASSERTED",
            }
            for r in ("COOPERATIVE", "SPECIAL_LEGAL_ENTITY", "APPLICATION_PENDING")
        ],
    }
    out.trace["assessment"]["certificate_ids_used"] = selected_ids
    return out


def _products(req, ctx):
    """Per-item comparison; do not treat one selected item as a whole-bid product."""
    if req.item_id:
        items = [req.item]
    else:
        items = list(req.bid.items.select_related("matched_product")) if req.bid_id else []
    if not items:
        return None
    comparisons, inputs, refs, checks = [], [], [], []
    invariant = req.category == "FILTER_GRADE" and not (req.normalized or {}).get("edition")
    for item in items:
        selected = item.matched_product
        pool = [selected] if selected else ctx.candidate_products.get(item.pk, [])
        candidates = []
        for p in pool:
            rr, cs, needs = _product_check(req, ctx, p)
            refs.append(product_evidence(p))
            refs.extend(e for c in cs for e in c.get("evidence", []) if e.get("type") == "document")
            candidates.append(
                {"product_id": p.pk, "verdict": rr, "checks": cs, "missing_inputs": needs}
            )
        if selected:
            current = candidates[0]["verdict"]
            checks.extend(candidates[0]["checks"])
            inputs.extend(candidates[0]["missing_inputs"])
        elif invariant and candidates and all(c["verdict"] == MET for c in candidates):
            current = (
                MET  # Every registered candidate has the same proven attribute; no choice made.
            )
            checks.extend(c for row in candidates for c in row["checks"])
        else:
            current = UNKNOWN
            inputs.append(
                missing(
                    f"items.{item.pk}.matched_product_id",
                    f"품목 {item.item_no}: 제안 제품 선택",
                    choices=[c["product_id"] for c in candidates],
                )
            )
        comparisons.append(
            {
                "item_id": item.pk,
                "selected_product_id": selected.pk if selected else None,
                "status": current,
                "selection_independent_attribute": not selected and current == MET,
                "candidates": candidates,
            }
        )
    verdict = (
        GAP
        if any(c["status"] == GAP for c in comparisons)
        else UNKNOWN
        if any(c["status"] == UNKNOWN for c in comparisons)
        else MET
    )
    reason = "품목별 현재 선택·후보의 실제 등록 속성을 비교했습니다. "
    if verdict == GAP:
        reason += "선택된 제품에서 요구와 다른 값이 확인되어 보완이 필요합니다. 미선택 품목이 이 차이를 가리지 않습니다."
    elif verdict == MET:
        reason += "선택 제품 또는 모든 등록 후보에서 해당 속성이 요구를 만족합니다. 미선택 품목의 모델을 확정한 것은 아닙니다."
    else:
        reason += "확인된 속성 비교는 보존하고 아래 특정 선택/조건 값만 미확인으로 남깁니다."
    out = result(
        req,
        verdict,
        reason,
        checks=checks,
        inputs=inputs,
        evidence=list(
            {(r["type"], r["id"], r.get("page"), r.get("quote")): r for r in refs}.values()
        ),
        value="; ".join(f"{c['field']}: {c['actual']}" for c in checks),
    )
    out.trace["assessment"]["item_comparisons"] = comparisons
    if (
        req.category == "MATERIAL"
        and (req.normalized or {}).get("part") == "gasket"
        and (req.normalized or {}).get("note")
    ):
        review = out.trace["assessment"]["interpretation_revalidation"]
        review["remaining_parts"].append("EPDM 지정과 제조사 기준 비고의 우선순위/승인 대안")
        review["status"] = "PARTIAL"
    # Preserve explicit candidate labels used by existing draft/comparison contracts.
    out.trace["candidate_comparisons"] = [
        {
            "product_id": c["product_id"],
            "candidate_verdict": c["verdict"],
            "rationale": str(c["checks"]),
            "trace": {},
        }
        for item in comparisons
        if not item["selected_product_id"]
        for c in item["candidates"]
    ]
    return out


def _product_check(req, ctx, product):
    from . import rules

    norm = req.normalized or {}
    refs = [product_evidence(product)]
    prefix = f"products.{product.pk}"
    needs, checks = [], []
    category = req.category
    if category == "MATERIAL" and norm.get("part") == "gasket":
        wanted = norm.get("required", [])
        actual = product.gasket
        match = any(rules.material_matches(v, actual) for v in wanted)
        different = bool(
            actual and wanted and ("urethane" in actual.lower() or "EPDM" in actual.upper())
        )
        verdict = MET if match else GAP if different else UNKNOWN
        checks.append(check(prefix + ".gasket", verdict, wanted, actual, refs))
        if verdict != MET:
            needs.append(
                missing(
                    prefix + ".gasket_option",
                    "요구 재질 개스킷의 제안 옵션/변경 사양 확정; 현재 등록 개스킷은 "
                    + (actual or "미상"),
                )
            )
    elif category == "MATERIAL" and norm.get("part") == "media":
        actual = product.media
        required = " ".join(norm.get("required", []))
        family = (
            "synthetic" in actual.lower()
            if "synthetic" in required.lower()
            else rules.material_matches(required, actual)
        )
        checks.append(
            check(prefix + ".media.family", MET if family else UNKNOWN, required, actual, refs)
        )
        for word, field in [("100%", "purity"), ("discharged", "discharged")]:
            if word in required.lower():
                known = word in actual.lower()
                checks.append(
                    check(prefix + ".media." + field, MET if known else UNKNOWN, word, actual, refs)
                )
                if not known:
                    needs.append(
                        missing(
                            prefix + ".media." + field,
                            f"여재의 {word} 명시 사양 또는 해당 조건 시험 근거",
                        )
                    )
        verdict = MET if all(c["status"] == MET for c in checks) else UNKNOWN
    elif category == "MATERIAL" and norm.get("parts"):
        components = component_values(product, ctx)
        for part in norm["parts"]:
            material = (product.extra or {}).get("component_materials", {}).get(
                part
            ) or components.get("values", {}).get(part)
            ok = bool(
                material and any(v.lower() in material.lower() for v in norm.get("required", []))
            )
            if material and "galvanized" in material.lower() and "powder" not in material.lower():
                checks.append(
                    check(
                        prefix + "." + part + ".base_material",
                        MET,
                        "아연도금 계열 또는 스테인리스",
                        material,
                        components.get("evidence", refs),
                    )
                )
            checks.append(
                check(
                    prefix + "." + part,
                    MET if ok else UNKNOWN,
                    norm.get("required"),
                    material,
                    components.get("evidence", refs),
                )
            )
            if not ok:
                needs.append(
                    missing(
                        prefix + "." + part + ".finish"
                        if material
                        else prefix + "." + part + ".material_and_finish",
                        f"{part}: 원문 기본 재질({material})은 확인됨. 분체도장 마감 여부/변경 옵션 확인"
                        if material
                        else f"{part}: 스테인리스 또는 분체도장 아연도금의 부품별 재질·마감 명시값",
                    )
                )
        verdict = MET if all(c["status"] == MET for c in checks) else UNKNOWN
    elif category == "ENVIRONMENT":
        base = rules.evaluate_environment(req, replace(ctx, comparison_product=product))
        for field in ("max_temp_c", "max_rh"):
            required, actual = norm.get(field), getattr(product, field)
            if required is not None:
                status = (
                    MET
                    if actual is not None and actual >= required
                    else GAP
                    if actual is not None
                    else UNKNOWN
                )
                checks.append(check(prefix + "." + field, status, required, actual, refs))
        if norm.get("min_temp_c") is None:
            checks.append(check("notice.min_temp_c", UNKNOWN, "원문 최저온도 부호/값", None))
            needs.append(
                missing("notice.min_temp_c", "원문 선행 대시의 부호 해석과 요구 최저온도 확정")
            )
        else:
            actual = (product.extra or {}).get("min_temp_c")
            checks.append(
                check(
                    prefix + ".min_temp_c",
                    MET
                    if actual is not None and actual <= norm["min_temp_c"]
                    else GAP
                    if actual is not None
                    else UNKNOWN,
                    norm["min_temp_c"],
                    actual,
                    refs,
                )
            )
            if actual is None:
                needs.append(missing(prefix + ".min_temp_c", "제품 사용 최저온도"))
        if norm.get("gas_turbine_model"):
            models = (product.extra or {}).get("compatible_turbines", [])
            ok = norm["gas_turbine_model"] in models
            checks.append(
                check(
                    prefix + ".turbine_compatibility",
                    MET if ok else UNKNOWN,
                    norm["gas_turbine_model"],
                    models,
                    refs,
                )
            )
            if not ok:
                needs.append(
                    missing(prefix + ".turbine_compatibility", "요구 가스터빈의 설치 호환 근거")
                )
        verdict = (
            GAP
            if base and base.verdict == GAP
            else MET
            if all(c["status"] == MET for c in checks)
            else UNKNOWN
        )
    else:
        proxy = copy.copy(req)
        proxy.normalized = {k: v for k, v in norm.items() if k != "interpretation_review"}
        rule = rules.RULES.get(category)
        base = rule(proxy, replace(ctx, comparison_product=product)) if rule else None
        verdict = base.verdict if base else UNKNOWN
        checks.append(
            check(
                prefix + "." + category.lower(),
                verdict,
                proxy.normalized,
                base.company_value if base else None,
                base.evidences if base else refs,
            )
        )
        if category == "FILTER_GRADE" and norm.get("edition"):
            family = norm.get("standard")
            edition = (product.extra or {}).get("standard_editions", {}).get(family)
            reports = [
                r
                for r in ctx.reports_for(product)
                if r.standard_family == family and str(norm["edition"]) in r.standard
            ]
            known = str(edition) == str(norm["edition"]) or bool(reports)
            checks.append(
                check(
                    prefix + ".standard_edition",
                    MET if known else UNKNOWN,
                    norm["edition"],
                    edition or [r.standard for r in reports],
                    refs,
                )
            )
            if not known:
                verdict = UNKNOWN if verdict != GAP else verdict
                needs.append(
                    missing(
                        prefix + ".standard_edition." + str(family),
                        "요구 판본을 명시한 제품 사양/시험 근거",
                    )
                )
        elif verdict == UNKNOWN:
            labels = {
                "EFFICIENCY": "요구 통계량·입경·규격·적용 제품이 일치하는 측정값",
                "PRESSURE_DROP": "동일 풍량·습도·적용 제품 범위의 차압 측정값",
                "TEST_STANDARD": "공인기관·규격 판본·분진·에어로졸 및 감독 승인 조건을 충족하는 시험 근거",
            }
            needs.append(
                missing(
                    prefix + "." + str(norm.get("metric") or category.lower()),
                    labels.get(category, "요구 속성의 미확인 명시값"),
                )
            )
    if not hasattr(ctx, "_assessment_locator"):
        ctx._assessment_locator = SourceLocator()
    doc = ctx._assessment_locator.document(product.source_document_id)
    verified = doc and ctx._assessment_locator.file_info(doc)["status"] == "VERIFIED"
    checks.append(
        check(
            prefix + ".source",
            MET if verified else UNKNOWN,
            "원본 바이트 SHA 일치",
            doc.pk if doc else None,
            refs,
        )
    )
    if not verified:
        verdict = UNKNOWN
        needs.append(missing(prefix + ".source", "제품 등록값의 연결 원본 및 현재 업로드 SHA 확인"))
    return verdict, checks, needs


def component_values(product, ctx):
    """Human-reviewed component data; no finish is inferred from a material name."""
    from apps.documents.models import DocumentMetadata

    if not hasattr(ctx, "_assessment_locator"):
        ctx._assessment_locator = SourceLocator()
    locator = ctx._assessment_locator
    doc = locator.document(product.source_document_id)
    if not doc:
        return {}
    metadata = DocumentMetadata.objects.filter(
        document=doc, key=f"manual_product_components.{product.pk}"
    ).first()
    if not metadata:
        return {}
    value = metadata.value
    info = locator.file_info(doc)
    if (
        value.get("product_id") != product.pk
        or value.get("source_sha256") != doc.sha256
        or info["status"] != "VERIFIED"
    ):
        return {}
    page = value.get("physical_page")
    if type(page) is not int or info.get("pdf_pages") is None or not 1 <= page <= info["pdf_pages"]:
        return {}
    values = value.get("values", {})
    evidence = []
    for item in value.get("evidence", []):
        field = item.get("field")
        if field not in values or values[field] not in item.get("quote", ""):
            return {}
        evidence.append(
            {
                "type": "document",
                "id": doc.pk,
                "document_id": doc.pk,
                "label": "부품별 기본 재질(사람 검토)",
                "page": page,
                "quote": item["quote"],
                "source_sha256": doc.sha256,
                "quote_verification": "HUMAN_TRANSCRIBED_NOT_MACHINE_CHECKED",
            }
        )
    if set(values) != {e.get("field") for e in value.get("evidence", [])}:
        return {}
    return {"values": values, "evidence": evidence}


def evaluate(req, ctx):
    """Only supported interpretations are released; all original review data survives."""
    norm = req.normalized or {}
    category = req.category
    if category == "CERTIFICATION" and norm.get("cert_type") == "SME":
        return _sme(req, ctx)
    if category in {
        "MATERIAL",
        "FILTER_GRADE",
        "DIMENSION",
        "FILTER_TYPE",
        "EFFICIENCY",
        "ENVIRONMENT",
        "TEST_STANDARD",
    }:
        return _products(req, ctx)
    # Work definitions are verified from a single original quote, never from a heading/page marker.
    future = category in {"WARRANTY", "INSPECTION"} or (
        category == "SUBMISSION_DOC" and norm.get("issuer_type") == "COMPANY"
    )
    fact = (category == "OTHER" and "pass_score" in norm) or norm.get(
        "metric"
    ) == "test_endpoint_dp"
    if future or fact:
        location = _source(req, ctx)
        verified = (
            location["status"] in {"EXACT_MATCH", "WHITESPACE_MATCH"}
            and location.get("source_verification") == "VERIFIED"
        )
        field_checks = notice_field_checks(req, ctx)
        verified = verified and all(c["status"] == MET for c in field_checks)
        status = MET if verified else UNKNOWN
        timings = norm.get("timing") or ("납품 후" if category == "WARRANTY" else "시험/검수 시")
        out = result(
            req,
            status,
            "원문과 저장 조건을 대조한 공고 사실/후속 업무입니다. 현재 회사의 완료 실적·시험 합격·보증 발급을 뜻하지 않습니다. "
            + (
                "현재 회사 비교와 분리해 이행 업무를 보존합니다."
                if verified
                else "원문 인용 위치 확인이 남아 있어 조건 확정을 보류합니다."
            ),
            scope="NOTICE_FACT" if fact else "FUTURE_OBLIGATION",
            checks=[check("notice.condition", status, norm, req.source_quote)] + field_checks,
            inputs=[]
            if verified
            else [
                missing(
                    f"requirements.{req.pk}.source_review", "보존된 인용과 원문 구절의 정확한 대조"
                )
            ],
            tasks=[
                task(
                    f"requirements.{req.pk}.fulfilment",
                    req.title,
                    timings,
                    conditional=bool(norm.get("applicability")),
                )
            ],
            ctx=ctx,
            value="원문 조건 확인; 후속 업무 미완료",
        )
        out.trace["assessment"]["follow_up_tasks"][0]["parameters"] = norm
        out.trace["assessment"]["follow_up_tasks"][0]["requirement_text"] = req.requirement_text
        if norm.get("copies") or norm.get("applicability"):
            out.trace["assessment"]["follow_up_parameters"] = {
                k: norm[k]
                for k in (
                    "copies",
                    "applicability",
                    "delivery_copies",
                    "days_after_contract",
                    "note",
                )
                if k in norm
            }
            if norm.get("copies"):
                out.trace["assessment"]["interpretation_revalidation"]["status"] = "PARTIAL"
                out.trace["assessment"]["interpretation_revalidation"]["remaining_parts"].append(
                    "future_document_copies_and_applicability"
                )
        return out
    if category == "OTHER" and norm.get("restriction"):
        return result(
            req,
            UNKNOWN,
            "일반 SME 증서는 별도 대조했으며 요구 제조 실적과 직접생산 적용 범위가 남아 있습니다.",
            inputs=[
                missing(
                    "company.direct_production_applicability", "직접생산 증서의 제안 품목 적용 범위"
                ),
                missing(
                    "company.qualifying_delivery_contract", "가스터빈/F7 이상 제조 납품 실적 근거"
                ),
            ],
        )
    return None


def notice_field_checks(req, ctx):
    """Matching a quote alone does not validate its normalized numerical meanings."""
    norm = req.normalized or {}
    attachment = req.source_attachment
    if not attachment:
        return []
    doc = ctx._assessment_locator.document(attachment.document_id)
    text = doc.extracted_text if doc else ""
    patterns = {}
    if "months" in norm:
        months = norm["months"]
        years = months / 12 if isinstance(months, (float, int)) else None
        options = [rf"{months}\s*개월"]
        if years is not None and years.is_integer():
            options.append(rf"{int(years)}\s*년")
        patterns["months"] = r"하자담보(?:책임)?기간\s*[:：]?\s*(?:" + "|".join(options) + ")"
    if "pass_score" in norm:
        patterns["pass_score"] = (
            rf"(?:통과점수\s*[:：]\s*{re.escape(str(norm['pass_score']))}\s*점|(?:종합평점\s*)?{re.escape(str(norm['pass_score']))}\s*점\s*이상)"
        )
    if "lower_limit_rate_pct" in norm:
        patterns["lower_limit_rate_pct"] = re.escape(str(norm["lower_limit_rate_pct"])) + r"\s*%"
    if "days_after_contract" in norm:
        patterns["days_after_contract"] = rf"계약\s*후\s*{norm['days_after_contract']}\s*일\s*이내"
    if "delivery_copies" in norm:
        patterns["delivery_copies"] = rf"제품\s*도면\s*{norm['delivery_copies']}\s*부"
    if "도면 승인" in norm.get("note", ""):
        patterns["note"] = r"제품\s*제작은\s*발주자의\s*도면\s*승인\s*후[\s\S]{0,30}?착수"
    if norm.get("metric") == "test_endpoint_dp":
        patterns["value"] = rf"Final\s*Pr\.\s*Drop\s*:\s*{norm['value']:g}\s*Pa"
    result = []
    for field, pattern in patterns.items():
        found = re.search(pattern, text, re.I)
        quote = found.group() if found else ""
        proof = (
            ctx._assessment_locator.locate(doc.pk, quote, role="NOTICE_FIELD_CHECK")
            if found
            else None
        )
        result.append(
            {
                **check("notice." + field, MET if found else UNKNOWN, norm[field], quote),
                "source_location": proof,
            }
        )
    return result


def supplement(req, rr, ctx):
    """Make remaining unknowns actionable without erasing the original requirement."""
    if rr is None:
        rr = result(req, UNKNOWN, "현재 자료로 아래 특정 조건을 확정할 수 없습니다.")
    if "assessment" in rr.trace:
        return rr
    norm = req.normalized or {}
    category = req.category
    requirements = {
        "G2B_ITEM": [
            missing("company.g2b_registered_items", "요구 물품번호의 나라장터 제조 등록 확인")
        ],
        "DIRECT_PRODUCTION": [
            missing(
                "company.direct_production_applicability",
                "직접생산 증서의 필터 종류/공장 제한이 제안 품목에 적용되는지 확인(기존 증서 재요청 아님)",
            )
        ],
        "KS": [
            missing(
                "company.ks_route",
                "KS 증빙 또는 불가피시 승인 경로 중 적용 경로 선택",
                choices=["KS_PROOF", "UNAVOIDABLE_NON_KS_APPROVAL"],
            )
        ],
    }
    inputs = requirements.get(norm.get("cert_type"), [])
    if category == "TRACK_RECORD" or (
        category == "SUBMISSION_DOC" and "실적" in str(norm.get("doc"))
    ):
        inputs = [
            missing(
                "company.qualifying_delivery_contract",
                "요구 기간·단일계약 금액·가스터빈 용도·F7 이상이 확인되는 제조 납품 계약/실적 근거",
            )
        ]
    elif category == "DELIVERY":
        inputs = [
            missing(
                "company.delivery_commitment",
                "제안 전체 수량의 일괄 납기 일수(요구 180일 이내) 및 분할불가 수용 여부",
            )
        ]
    elif category == "SUBMISSION_DOC" and "성적서" in str(norm.get("doc")):
        inputs = [
            missing(
                "company.filter_element_and_finished_reports",
                "여재/Filter Element와 필터 완제품 각각의 원본 시험성적서 및 제출 부수·범위",
            )
        ]
    elif category == "PRESSURE_DROP":
        metric = norm.get("metric")
        label = (
            "RH≥80%에서 차압 변동폭(기준 차압·측정조건 포함)"
            if metric == "dp_variation_at_high_rh"
            else "공고 풍량 표기(2770m/h·1630CFM)의 적용 단위/개별·페어 시험 범위 및 동일조건 초기 차압"
        )
        inputs = [missing("testing." + str(metric), label)]
    elif category == "AIRFLOW":
        inputs = [
            missing(
                "engineering.system_airflow",
                "시스템 구성·수량·설계 마진·설계 조건이 포함된 총 흡입 풍량 산정 근거",
            )
        ]
    elif norm.get("metric") == "net_effective_filtering_area":
        inputs = [
            missing(
                "engineering.net_effective_area",
                "공고 순유효면적의 단위/정의와 제안 페어의 실제 순유효면적(단순 면적 합산 불가)",
            )
        ]
    elif category == "OTHER" and norm.get("restriction"):
        inputs = requirements["DIRECT_PRODUCTION"] + [
            missing("company.qualifying_delivery_contract", "가스터빈/F7 이상 제조 납품 실적 근거")
        ]
    elif category == "OTHER" and norm.get("scope"):
        inputs = [
            missing(
                "offer.pair_configuration",
                "선택 품목 조합·기 설치 호환·Gasket/Nut 포함·EA/Set/1식 구성 수량",
            )
        ]
    out = result(
        req,
        rr.verdict,
        rr.rationale,
        checks=[check("current.condition", rr.verdict, norm, rr.company_value, rr.evidences)],
        inputs=inputs if rr.verdict != MET else [],
        evidence=rr.evidences,
        value=rr.company_value,
    )
    return replace(
        rr,
        trace={**rr.trace, **out.trace},
        action_items=list(dict.fromkeys([m["label"] for m in inputs] + rr.action_items)),
    )


def saved_assessment(evaluation):
    """No reinterpretation of old results on GET or after a manual edit."""
    if not evaluation or evaluation.is_modified:
        return {"schema": None, "status": "MANUAL_REVIEW_REQUIRED" if evaluation else "NO_RESULT"}
    return (evaluation.rule_trace or {}).get("assessment") or {
        "schema": None,
        "status": "LEGACY_UNSTRUCTURED",
    }


def input_requests(evaluations):
    requests = {}
    for ev in evaluations:
        for row in saved_assessment(ev).get("missing_inputs", []):
            entry = requests.setdefault(row["key"], {**row, "requirement_ids": []})
            entry["requirement_ids"].append(ev.requirement_id)
            entry.setdefault("conditions_by_requirement", {})[str(ev.requirement_id)] = (
                ev.requirement.normalized
            )
    return list(requests.values())


def summary(evaluations):
    rows = list(evaluations)
    current = {MET: 0, GAP: 0, UNKNOWN: 0, "NOT_APPLICABLE": 0}
    scopes = {}
    open_tasks = []
    for ev in rows:
        assessment = saved_assessment(ev)
        scope = assessment.get("scope", "LEGACY_OR_MANUAL")
        scopes[scope] = scopes.get(scope, 0) + 1
        status = assessment.get("current_company_verdict", UNKNOWN)
        current[status] = current.get(status, 0) + 1
        open_tasks.extend(
            {**t, "requirement_id": ev.requirement_id}
            for t in assessment.get("follow_up_tasks", [])
        )
    return {
        "total_requirements": len(rows),
        "by_scope": scopes,
        "current_company_counts": current,
        "follow_up_tasks": open_tasks,
        "input_requests": input_requests(rows),
        "notice_or_workflow_MET_is_company_compliance": False,
    }
