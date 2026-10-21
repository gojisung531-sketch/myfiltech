"""Deterministic rule engine (specs/08 §5). A rule returns a RuleResult, or None to defer to
the LLM. The LLM never overrides a rule verdict.
"""

import re
from dataclasses import dataclass, field
from datetime import date

from apps.core.app_settings import get_setting
from apps.core.units import parse_number

from .context import EvaluationContext, nominal_family
from .evidence import product_evidence, record_evidence, report_evidence, target_product
from .grades import FAMILY_LABELS, family_of, meets, parse_grade, product_grades, required_grade

MET = "MET"
NEEDS_SUPPLEMENT = "NEEDS_SUPPLEMENT"
NEEDS_CONFIRMATION = "NEEDS_CONFIRMATION"


@dataclass
class RuleResult:
    verdict: str
    risk_level: str
    rationale: str
    company_value: str = ""
    action_items: list[str] = field(default_factory=list)
    evidences: list[dict] = field(default_factory=list)
    trace: dict = field(default_factory=dict)


def _cert_evidence(cert) -> dict:
    return {
        "type": "certificate",
        "id": cert.pk,
        "label": f"{cert.name or cert.cert_type} ({cert.cert_no})",
        "page": 1,
        "quote": f"유효 기간 {cert.valid_from} ~ {cert.valid_until}",
    }


def code_matches(cert_code: str, required: str) -> bool:
    """Hierarchical item codes: '40161505' matches '4016150501'; 'x' is a wildcard digit."""
    cert_code, required = str(cert_code).lower().strip(), str(required).strip()
    if not cert_code or not required:
        return False
    return all(c == "x" or c == r for c, r in zip(cert_code, required, strict=False))


def evaluate_certification(requirement, ctx: EvaluationContext) -> RuleResult | None:
    norm = requirement.normalized or {}
    cert_type = (norm.get("cert_type") or "").upper()
    mandatory = requirement.is_mandatory
    ref = ctx.reference_date

    if cert_type == "SME":
        company = ctx.company
        if company.is_sme is None:
            return RuleResult(
                NEEDS_CONFIRMATION,
                "HIGH" if mandatory else "MEDIUM",
                "회사 정보에 중소기업 여부가 입력되어 있지 않습니다.",
                action_items=["회사 정보에 중소기업 여부와 확인서 유효기간 입력"],
            )
        if not company.is_sme:
            return RuleResult(NEEDS_SUPPLEMENT, "HIGH", "회사 정보상 중소기업이 아닙니다.")
        if company.sme_cert_valid_until and company.sme_cert_valid_until < ref:
            return RuleResult(
                NEEDS_SUPPLEMENT,
                "HIGH",
                f"중소기업확인서 유효기간({company.sme_cert_valid_until})이 기준일({ref})보다 이전입니다.",
                action_items=["중소기업확인서 갱신"],
            )
        return RuleResult(MET, "LOW", "회사 정보상 중소기업이며 확인서가 유효합니다.", "중소기업")

    if cert_type == "G2B_ITEM":
        code = str(norm.get("product_code") or "")
        items = ctx.company.g2b_registered_items or []
        hit = next(
            (
                i
                for i in items
                if code
                and (code_matches(i.get("code", ""), code) or code_matches(code, i.get("code", "")))
            ),
            None,
        )
        if hit:
            return RuleResult(
                MET,
                "LOW",
                f"나라장터 등록 물품 {hit.get('code')}이(가) 요구 분류와 일치합니다.",
                str(hit.get("code")),
            )
        return RuleResult(
            NEEDS_CONFIRMATION,
            "HIGH" if mandatory else "MEDIUM",
            f"회사 정보에 요구 물품분류번호({code or '미상'})의 나라장터 등록 내역이 없습니다.",
            action_items=["나라장터 제조물품 등록 여부 확인"],
        )

    if not cert_type or cert_type == "OTHER":
        return None
    certs = [c for c in ctx.certificates if c.cert_type == cert_type]
    if not certs:
        return RuleResult(
            NEEDS_SUPPLEMENT,
            "HIGH" if mandatory else "MEDIUM",
            f"요구 인증({cert_type})을 보유하고 있지 않습니다.",
            action_items=[f"{cert_type} 인증 취득 또는 대체 서류 확인"],
        )
    cert = max(certs, key=lambda c: c.valid_until or date.min)
    status = cert.status_on(ref, ctx.expiring_days)
    evidence = [_cert_evidence(cert)]
    trace = {"reference_date": str(ref), "valid_until": str(cert.valid_until), "status": status}
    if status == "EXPIRED":
        return RuleResult(
            NEEDS_SUPPLEMENT,
            "HIGH" if mandatory else "MEDIUM",
            f"{cert.name or cert_type}({cert.cert_no})의 유효기간({cert.valid_until})이 기준일({ref})에 만료되었습니다.",
            f"{cert.cert_no} (만료 {cert.valid_until})",
            action_items=["인증 갱신(사후·갱신심사) 후 갱신 인증서 제출"],
            evidences=evidence,
            trace=trace,
        )
    if status == "UNKNOWN":
        return RuleResult(
            NEEDS_CONFIRMATION,
            "MEDIUM",
            "인증서 유효기간 정보가 없습니다.",
            cert.cert_no,
            evidences=evidence,
        )

    required_code = str(norm.get("product_code") or "")
    if required_code:
        codes = cert.product_codes or []
        if not any(code_matches(code, required_code) for code in codes):
            return RuleResult(
                NEEDS_CONFIRMATION,
                "HIGH" if mandatory else "MEDIUM",
                f"요구 세부품명번호 {required_code}와 보유 인증서({cert.cert_no})의 품목번호 {', '.join(codes) or '(없음)'}가 일치하는지 확인이 필요합니다.",
                f"{cert.cert_no} 품목번호 {', '.join(codes) or '-'}",
                action_items=["직접생산확인 품목(세부품명번호) 일치 여부 확인, 필요 시 추가 신청"],
                evidences=evidence,
                trace={**trace, "required_code": required_code, "cert_codes": codes},
            )
    required_note = norm.get("required_note")
    if required_note and required_note not in (cert.scope or ""):
        return RuleResult(
            NEEDS_CONFIRMATION,
            "HIGH" if mandatory else "MEDIUM",
            f"인증서 범위에 요구 특이사항 '{required_note}'이(가) 기재되어 있는지 확인이 필요합니다.",
            cert.scope,
            action_items=["인증서 필수특이사항 기재 여부 확인"],
            evidences=evidence,
            trace=trace,
        )
    risk = "MEDIUM" if status == "EXPIRING" else "LOW"
    note = " (만료 임박)" if status == "EXPIRING" else ""
    return RuleResult(
        MET,
        risk,
        f"{cert.name or cert_type}({cert.cert_no})이(가) 기준일({ref})에 유효합니다{note}.",
        f"{cert.cert_no} (~{cert.valid_until})",
        evidences=evidence,
        trace=trace,
    )


def _months_before(ref: date, years: int) -> str:
    return f"{ref.year - years:04d}-{ref.month:02d}"


def evaluate_track_record(requirement, ctx: EvaluationContext) -> RuleResult | None:
    norm = requirement.normalized or {}
    years = norm.get("period_years")
    product_types = [t for t in norm.get("product_types") or [] if t]
    grade = required_grade(norm.get("grade") or {})
    if not (years or product_types or grade):
        return None  # unstructured requirement → LLM

    cutoff = _months_before(ctx.reference_date, int(years)) if years else "0000-00"
    records = [r for r in ctx.delivery_records if r.delivered_ym >= cutoff]
    if norm.get("power_plant_only"):
        records = [r for r in records if r.is_power_plant]

    qualifying = []
    for record in records:
        products = list(record.products.all())
        if product_types:
            products = [p for p in products if p.filter_type in product_types]
        if grade:
            products = [p for p in products if any(meets(g, grade) for g in product_grades(p))]
        if products:
            qualifying.append((record, products))

    condition = norm.get("spec_condition") or ", ".join(
        filter(
            None,
            [
                f"최근 {years}년" if years else "",
                "/".join(product_types),
                str(grade) if grade else "",
            ],
        )
    )
    trace = {
        "reference_date": str(ctx.reference_date),
        "cutoff": cutoff,
        "candidates": len(records),
        "qualifying": [r.delivered_ym for r, _ in qualifying],
    }
    evidences = [
        {
            "type": "delivery_record",
            "id": record.pk,
            "label": f"{record.delivered_ym} {record.client} {record.project_name}",
            "page": 1,
            "quote": ", ".join(p.model_no for p in products),
        }
        for record, products in qualifying
    ]
    if not qualifying:
        return RuleResult(
            NEEDS_SUPPLEMENT,
            "HIGH" if requirement.is_mandatory else "MEDIUM",
            f"요구 실적 조건({condition})을 만족하는 납품실적이 없습니다.",
            action_items=["실적 요건 충족 여부 재확인 — 미충족 시 입찰 참가자격 미달"],
            trace=trace,
        )
    company_value = "; ".join(e["label"] for e in evidences)
    min_amount = norm.get("min_amount_krw")
    if min_amount:
        amounts = [r.amount_krw for r, _ in qualifying if r.amount_krw is not None]
        if not amounts:
            return RuleResult(
                NEEDS_CONFIRMATION,
                "MEDIUM",
                f"조건에 맞는 실적 {len(qualifying)}건이 있으나 금액 정보가 없어 기준금액 {min_amount:,}원 충족 여부를 확인해야 합니다.",
                company_value,
                action_items=["실적증명서의 계약금액 확인"],
                evidences=evidences,
                trace=trace,
            )
        if max(amounts) < min_amount:
            return RuleResult(
                NEEDS_SUPPLEMENT,
                "HIGH",
                f"조건에 맞는 실적의 최대 금액({max(amounts):,}원)이 기준금액({min_amount:,}원)에 못 미칩니다.",
                company_value,
                evidences=evidences,
                trace=trace,
            )
    return RuleResult(
        MET,
        "LOW",
        f"요구 실적 조건({condition})을 만족하는 납품실적 {len(qualifying)}건이 있습니다.",
        company_value,
        evidences=evidences,
        trace=trace,
    )


# ---- shared helpers -------------------------------------------------------------------


def compare(actual: float, operator: str, limit: float) -> bool:
    return {
        ">=": actual >= limit,
        ">": actual > limit,
        "<=": actual <= limit,
        "<": actual < limit,
        "=": abs(actual - limit) <= abs(limit) * 0.01,
    }.get(operator or "", actual >= limit)


def _fmt(value) -> str:
    return f"{value:,.1f}".rstrip("0").rstrip(".") if isinstance(value, float) else f"{value:,}"


def _no_product(requirement) -> RuleResult:
    return RuleResult(
        NEEDS_SUPPLEMENT,
        "HIGH",
        "요구 사양에 대응하는 매칭 제품이 없습니다.",
        action_items=["대응 가능 제품 검토 또는 신규 사양 제작 검토"],
    )


# ---- product specification ------------------------------------------------------------

_AXES = [
    ("w", "width_mm", "폭"),
    ("h", "height_mm", "높이"),
    ("d", "depth_mm", "깊이"),
    ("dia", "diameter_mm", "외경"),
    ("dia2", "diameter2_mm", "외경2"),
    ("len", "length_mm", "길이"),
]


def _required_dims(requirement) -> dict:
    norm = requirement.normalized or {}
    dims = {k: norm.get(k) for k, _, _ in _AXES if isinstance(norm.get(k), (int, float))}
    if norm.get("d_max"):
        dims["d_max"] = norm["d_max"]
    item = requirement.item
    if not dims and item is not None:
        for key, attr, _ in _AXES:
            value = getattr(item, attr, None)
            if value is not None:
                dims[key] = value
        if item.depth_mm_max:
            dims["d_max"] = item.depth_mm_max
    return {k: v for k, v in dims.items() if v}


def _product_dim_sets(product) -> list[tuple[str, dict]]:
    base = {key: getattr(product, attr) for key, attr, _ in _AXES if getattr(product, attr)}
    sets = [(product.model_no, base)]
    for variant in product.dimension_variants or []:
        if isinstance(variant, dict):
            values = {k: variant.get(k) for k, _, _ in _AXES if variant.get(k)}
            if values:
                sets.append((variant.get("label") or product.model_no, values))
    return sets


def _compare_dims(required: dict, actual: dict, ctx: EvaluationContext) -> tuple[str, list]:
    """Return ('exact'|'nominal'|'mismatch', per-axis trace)."""
    status, trace = "exact", []
    for key, _, label in _AXES:
        target = required.get(key)
        if target is None:
            continue
        value = actual.get(key)
        upper = required.get("d_max") if key == "d" else None
        if value is None:
            axis = "mismatch"
        elif upper and target - ctx.tolerance <= value <= upper + ctx.tolerance:
            axis = "exact"
        elif abs(value - target) <= ctx.tolerance:
            axis = "exact"
        elif (family := nominal_family(value, ctx.nominal, ctx.tolerance)) and family == (
            nominal_family(target, ctx.nominal, ctx.tolerance)
        ):
            axis = "nominal"
        else:
            axis = "mismatch"
        trace.append(
            {"axis": label, "required": target, "upper": upper, "product": value, "result": axis}
        )
        if axis == "mismatch":
            status = "mismatch"
        elif axis == "nominal" and status == "exact":
            status = "nominal"
    return status, trace


def _dims_text(dims: dict) -> str:
    if dims.get("dia"):
        dia = f"Ø{_fmt(dims['dia'])}" + (f"/Ø{_fmt(dims['dia2'])}" if dims.get("dia2") else "")
        return f"{dia} × {_fmt(dims.get('len') or 0)} mm"
    parts = [_fmt(dims[k]) for k in ("w", "h", "d") if dims.get(k)]
    if dims.get("d_max"):
        parts[-1] = f"{parts[-1]}~{_fmt(dims['d_max'])}"
    return " × ".join(parts) + " mm"


def evaluate_dimension(requirement, ctx: EvaluationContext) -> RuleResult | None:
    required = _required_dims(requirement)
    if not required:
        return None
    product = target_product(requirement, ctx)
    if product is None:
        return _no_product(requirement)
    best = None
    for label, actual in _product_dim_sets(product):
        status, trace = _compare_dims(required, actual, ctx)
        rank = {"exact": 0, "nominal": 1, "mismatch": 2}[status]
        if best is None or rank < best[0]:
            best = (rank, status, trace, label, actual)
    _, status, trace, label, actual = best
    evidence = [product_evidence(product)]
    company_value = f"{label} {_dims_text(actual)}"
    rule_trace = {"tolerance_mm": ctx.tolerance, "axes": trace}
    if status == "exact":
        return RuleResult(
            MET,
            "LOW",
            f"요구 치수 {_dims_text(required)}와 {label} 치수 {_dims_text(actual)}가 허용오차 ±{_fmt(ctx.tolerance)} mm 이내로 일치합니다.",
            company_value,
            evidences=evidence,
            trace=rule_trace,
        )
    if status == "nominal":
        return RuleResult(
            NEEDS_SUPPLEMENT,
            "MEDIUM",
            f"요구 치수 {_dims_text(required)}와 {label} 치수 {_dims_text(actual)}는 같은 인치 공칭군이지만 실제 치수 차이가 허용오차(±{_fmt(ctx.tolerance)} mm)를 넘습니다.",
            company_value,
            action_items=[f"{_dims_text(required)} 사양 제작 가능 여부 확인 및 도면 제출"],
            evidences=evidence,
            trace=rule_trace,
        )
    alternatives = [
        p.model_no
        for p in ctx.products
        if p.pk != product.pk
        and any(_compare_dims(required, a, ctx)[0] == "exact" for _, a in _product_dim_sets(p))
    ]
    actions = [f"대안 제품 {', '.join(alternatives)} 검토"] if alternatives else []
    return RuleResult(
        NEEDS_SUPPLEMENT,
        "HIGH",
        f"요구 치수 {_dims_text(required)}와 {label} 치수 {_dims_text(actual)}가 다릅니다.",
        company_value,
        action_items=actions + [f"{_dims_text(required)} 사양 신규 제작 가능 여부 검토"],
        evidences=evidence,
        trace=rule_trace,
    )


def evaluate_filter_type(requirement, ctx: EvaluationContext) -> RuleResult | None:
    required = (requirement.normalized or {}).get("type")
    if not required:
        return None
    product = target_product(requirement, ctx)
    if product is None:
        return _no_product(requirement)
    label = product.get_filter_type_display()
    if product.filter_type == required:
        return RuleResult(
            MET,
            "LOW",
            f"{product.model_no}의 형식({label})이 요구 형식과 일치합니다.",
            f"{product.model_no} ({label})",
            evidences=[product_evidence(product)],
        )
    alternatives = [p.model_no for p in ctx.products if p.filter_type == required]
    if alternatives:
        return RuleResult(
            NEEDS_SUPPLEMENT,
            "MEDIUM",
            f"매칭 제품 {product.model_no}({label})의 형식이 요구와 다르며, 같은 형식의 제품 {', '.join(alternatives)}이(가) 있습니다.",
            f"{product.model_no} ({label})",
            action_items=[f"매칭 제품을 {', '.join(alternatives)}(으)로 변경 검토"],
            evidences=[product_evidence(product)],
        )
    return RuleResult(
        NEEDS_SUPPLEMENT,
        "HIGH",
        f"요구 형식의 제품이 없습니다(매칭 제품 {product.model_no}: {label}).",
        f"{product.model_no} ({label})",
        action_items=["요구 형식 제품 개발·제작 가능 여부 검토"],
        evidences=[product_evidence(product)],
    )


def _reference_text(grade, ctx_map: list[dict]) -> str:
    """Approximate grades in other systems — narrative only, never a verdict (specs/08 §5.1)."""
    for row in ctx_map or []:
        value = row.get(grade.family)
        if value and parse_grade(str(value), grade.family) == grade:
            others = [f"{FAMILY_LABELS.get(k, k)} {v}" for k, v in row.items() if k != grade.family]
            return " ≈ ".join(others)
    return ""


def evaluate_filter_grade(requirement, ctx: EvaluationContext) -> RuleResult | None:
    norm = requirement.normalized or {}
    grade = required_grade(norm)
    if grade is None:
        return None
    product = target_product(requirement, ctx)
    if product is None:
        return None
    reports = ctx.reports_for(product)
    same_reports = [
        (r, g)
        for r in reports
        if r.standard_family == grade.family and (g := parse_grade(r.result_class, grade.family))
    ]
    same_product = [g for g in product_grades(product) if g.family == grade.family]
    evidence_base = [product_evidence(product)]

    passing = [(r, g) for r, g in same_reports if meets(g, grade)]
    if passing:
        report, achieved = max(passing, key=lambda rg: rg[0].issue_date or date.min)
        evidence = [report_evidence(report, f"분류 결과 {report.result_class}")]
        if report.is_obsolete_standard:
            return RuleResult(
                MET,
                "MEDIUM",
                f"{report.report_no}({report.standard}, {report.issue_date:%Y})에서 {achieved.label} 등급으로 요구({grade}) 이상입니다. 단, 폐지된 규격(EN 779:2012 → ISO 16890 대체)의 성적서입니다.",
                f"{achieved} ({report.report_no})",
                action_items=["발주처에 폐지 규격 성적서 인정 여부 확인 또는 현행 규격 시험 검토"],
                evidences=evidence,
            )
        return RuleResult(
            MET,
            "LOW",
            f"{report.report_no}({report.standard})에서 {achieved.label} 등급으로 요구({grade}) 이상입니다.",
            f"{achieved} ({report.report_no})",
            evidences=evidence,
        )
    if same_reports or any(meets(g, grade) is False for g in same_product):
        achieved = same_reports[0][1] if same_reports else same_product[0]
        return RuleResult(
            NEEDS_SUPPLEMENT,
            "HIGH",
            f"{product.model_no}의 {FAMILY_LABELS.get(grade.family, grade.family)} 등급 {achieved.label}이(가) 요구 {grade.label}에 못 미칩니다.",
            str(achieved),
            action_items=["상위 등급 제품 검토 또는 사양 변경"],
            evidences=[report_evidence(r) for r, _ in same_reports] or evidence_base,
        )
    if any(meets(g, grade) for g in same_product):
        achieved = next(g for g in same_product if meets(g, grade))
        return RuleResult(
            MET,
            "MEDIUM",
            f"{product.model_no} 사양서에 {achieved} 등급이 기재되어 있으나 같은 규격의 시험성적서는 없습니다.",
            f"{achieved} (사양서)",
            action_items=[f"{FAMILY_LABELS.get(grade.family, grade.family)} 시험성적서 확보"],
            evidences=evidence_base,
        )
    others = [g for g in product_grades(product)]
    reference = _reference_text(grade, get_setting("evaluation.grade_reference_map"))
    held = ", ".join(str(g) for g in others) or "등급 정보 없음"
    text = requirement.requirement_text or ""
    if "동등" in text:
        return RuleResult(
            NEEDS_CONFIRMATION,
            "MEDIUM",
            f"요구 규격({FAMILY_LABELS.get(grade.family, grade.family)}) 자료가 없고 보유 등급은 {held}입니다. 공고에 '동등 이상' 문구가 있어 타 규격 인정 여부 확인이 필요합니다."
            + (f" (참고 근사: {reference})" if reference else ""),
            held,
            evidences=evidence_base,
            trace={"reference_map": reference},
        )
    return RuleResult(
        NEEDS_SUPPLEMENT,
        "MEDIUM",
        f"요구 규격({grade}) 시험성적서·등급 자료가 없습니다. 보유 등급: {held}."
        + (
            f" 참고 근사: {reference} — 규격이 달라 동등으로 판정하지 않습니다."
            if reference
            else ""
        ),
        held,
        action_items=[
            f"요구 규격({FAMILY_LABELS.get(grade.family, grade.family)})으로 공인기관 시험 의뢰"
        ],
        evidences=evidence_base,
        trace={"reference_map": reference},
    )


def _metric_pattern(metric: str) -> str | None:
    m = (metric or "").lower().replace(" ", "")
    if "epm10" in m:
        return r"^ePM10"
    if "epm2" in m:
        return r"^ePM2"
    if "epm1" in m:
        return r"^ePM1(?!0)"
    if "0_4" in m or "0.4" in m:
        if "avg" in m or "average" in m or "평균" in m:
            return r"0\.4.*평균"
        if "min" in m or "최소" in m:
            return r"0\.4.*최소"
        if "init" in m or "초기" in m:
            return r"0\.4.*초기"
        return r"0\.4"
    if "mpps" in m or "integral" in m:
        return r"integral"
    if "local" in m:
        return r"local"
    if "gravimetric" in m or "arrestance" in m or "중량" in m:
        return r"중량법"
    return None


def evaluate_efficiency(requirement, ctx: EvaluationContext) -> RuleResult | None:
    norm = requirement.normalized or {}
    value = norm.get("value")
    pattern = _metric_pattern(norm.get("metric") or requirement.title)
    if not isinstance(value, (int, float)) or pattern is None:
        return None
    product = target_product(requirement, ctx)
    if product is None:
        return None
    family = family_of(norm.get("test_standard") or "")
    operator = norm.get("operator") or ">="
    reports = ctx.reports_for(product)
    measured = []
    for report in reports:
        if family and report.standard_family != family:
            continue
        for key, raw in (report.results or {}).items():
            if isinstance(raw, (str, int, float)) and re.search(pattern, key, re.I):
                number = parse_number(str(raw))
                if number is not None:
                    measured.append((report, key, number))
    if measured:
        report, key, number = measured[0]
        evidence = [report_evidence(report, f"{key}: {report.results[key]}")]
        if compare(number, operator, value):
            return RuleResult(
                MET,
                "MEDIUM" if report.is_obsolete_standard else "LOW",
                f"{report.report_no}의 {key} {_fmt(number)}%가 요구({operator} {_fmt(value)}%)를 만족합니다."
                + (" (폐지 규격 성적서)" if report.is_obsolete_standard else ""),
                f"{_fmt(number)}% ({report.report_no})",
                evidences=evidence,
            )
        return RuleResult(
            NEEDS_SUPPLEMENT,
            "HIGH",
            f"{report.report_no}의 {key} {_fmt(number)}%가 요구({operator} {_fmt(value)}%)에 못 미칩니다.",
            f"{_fmt(number)}% ({report.report_no})",
            action_items=["상위 효율 제품 검토"],
            evidences=evidence,
        )
    if family and any(r.standard_family != family for r in reports):
        return RuleResult(
            NEEDS_SUPPLEMENT,
            "MEDIUM",
            f"요구 시험규격({FAMILY_LABELS.get(family, family)})의 측정값이 없고 다른 규격 성적서만 있습니다.",
            ", ".join(r.report_no for r in reports),
            action_items=[f"{FAMILY_LABELS.get(family, family)} 기준 효율 시험 의뢰"],
            evidences=[report_evidence(r) for r in reports],
        )
    return RuleResult(
        NEEDS_CONFIRMATION,
        "MEDIUM",
        "요구 효율 항목의 측정값이 회사 성적서에 없습니다.",
        action_items=["해당 효율 측정값 확보 여부 확인"],
        evidences=[product_evidence(product)],
    )


def interpolate(curve: list[dict], airflow: float) -> float | None:
    points = sorted(
        (float(p["airflow_m3h"]), float(p["dp_pa"]))
        for p in curve or []
        if p.get("airflow_m3h") is not None and p.get("dp_pa") is not None
    )
    for (x0, y0), (x1, y1) in zip(points, points[1:], strict=False):
        if x0 <= airflow <= x1:
            return y0 + (airflow - x0) / (x1 - x0) * (y1 - y0) if x1 != x0 else y0
    return None


def _same_airflow(a: float | None, b: float | None) -> bool:
    return a is not None and b is not None and abs(a - b) <= max(a, b) * 0.01


def evaluate_pressure_drop(requirement, ctx: EvaluationContext) -> RuleResult | None:
    norm = requirement.normalized or {}
    value = norm.get("value")
    metric = norm.get("metric") or "initial_dp"
    operator = norm.get("operator") or "<="
    if not isinstance(value, (int, float)):
        return None
    product = target_product(requirement, ctx)
    if product is None:
        return None

    if metric == "final_dp":
        if operator not in (">", ">="):
            return None
        if product.final_dp_pa is None:
            return RuleResult(NEEDS_CONFIRMATION, "MEDIUM", "제품 권장 최종 차압 정보가 없습니다.")
        ok = compare(product.final_dp_pa, operator, value)
        return RuleResult(
            MET if ok else NEEDS_SUPPLEMENT,
            "LOW" if ok else "MEDIUM",
            f"{product.model_no} 권장 최종 차압 {_fmt(product.final_dp_pa)} Pa — 요구 {operator} {_fmt(value)} Pa {'충족' if ok else '미달'}.",
            f"권장 최종 차압 {_fmt(product.final_dp_pa)} Pa",
            action_items=[] if ok else ["최종 차압 사용 조건 협의 또는 사양 변경 검토"],
            evidences=[product_evidence(product)],
        )

    airflow = norm.get("at_airflow_m3h")
    reports = [r for r in ctx.reports_for(product) if r.initial_dp_pa is not None]
    if not airflow or _same_airflow(airflow, product.rated_airflow_m3h):
        report = next(
            (
                r
                for r in reports
                if _same_airflow(r.test_airflow_m3h, airflow or product.rated_airflow_m3h)
            ),
            None,
        )
        actual = (
            product.initial_dp_pa
            if product.initial_dp_pa is not None
            else (report and report.initial_dp_pa)
        )
        if actual is None:
            return RuleResult(NEEDS_CONFIRMATION, "MEDIUM", "제품 초기 차압 정보가 없습니다.")
        at = airflow or product.rated_airflow_m3h
        source = report.report_no if report else "사양서"
        ok = compare(actual, operator, value)
        return RuleResult(
            MET if ok else NEEDS_SUPPLEMENT,
            "LOW" if ok else "HIGH",
            f"{product.model_no} 초기 차압 {_fmt(actual)} Pa @{_fmt(at)} m³/h ({source}) — 요구 {operator} {_fmt(value)} Pa {'충족' if ok else '미달'}.",
            f"{_fmt(actual)} Pa @{_fmt(at)} m³/h ({source})",
            action_items=[] if ok else ["저차압 사양 검토 또는 풍량 조건 협의"],
            evidences=[report_evidence(report, f"초기 차압 {_fmt(report.initial_dp_pa)} Pa")]
            if report
            else [product_evidence(product)],
        )

    estimated = interpolate(product.airflow_dp_curve, airflow)
    if estimated is None:
        return RuleResult(
            NEEDS_CONFIRMATION,
            "MEDIUM",
            f"요구 풍량 {_fmt(airflow)} m³/h가 {product.model_no} 풍량-차압 곡선 범위 밖이라 차압을 산정할 수 없습니다.",
            action_items=[f"{_fmt(airflow)} m³/h 조건 차압 시험 또는 제조 데이터 확인"],
            evidences=[product_evidence(product)],
        )
    points = sorted(product.airflow_dp_curve, key=lambda p: p["airflow_m3h"])
    lo = max((p for p in points if p["airflow_m3h"] <= airflow), key=lambda p: p["airflow_m3h"])
    hi = min((p for p in points if p["airflow_m3h"] >= airflow), key=lambda p: p["airflow_m3h"])
    formula = (
        f"{_fmt(lo['dp_pa'])} + ({_fmt(airflow)} − {_fmt(lo['airflow_m3h'])}) / "
        f"({_fmt(hi['airflow_m3h'])} − {_fmt(lo['airflow_m3h'])}) × "
        f"({_fmt(hi['dp_pa'])} − {_fmt(lo['dp_pa'])}) = {estimated:.1f} Pa"
    )
    ok = compare(estimated, operator, value)
    return RuleResult(
        MET if ok else NEEDS_SUPPLEMENT,
        "MEDIUM" if ok else "HIGH",
        f"성적서 풍량과 요구 풍량({_fmt(airflow)} m³/h)이 달라 풍량-차압 곡선 선형 보간값 {estimated:.1f} Pa로 비교했습니다 — 요구 {operator} {_fmt(value)} Pa {'충족' if ok else '미달'} (보간값).",
        f"≈{estimated:.1f} Pa @{_fmt(airflow)} m³/h (보간값)",
        action_items=[] if ok else ["저차압 사양 검토 또는 풍량 조건 협의"],
        evidences=[product_evidence(product)],
        trace={"interpolation": formula, "lower": lo, "upper": hi},
    )


def evaluate_airflow(requirement, ctx: EvaluationContext) -> RuleResult | None:
    value = (requirement.normalized or {}).get("value")
    if not isinstance(value, (int, float)):
        return None
    product = target_product(requirement, ctx)
    if product is None or not product.rated_airflow_m3h:
        return None
    rated = product.rated_airflow_m3h
    if value > rated * 10:  # whole-system airflow, not per filter
        quantity = sum((i.quantity or 0) for i in requirement.bid.items.all())
        capacity = quantity * rated
        return RuleResult(
            NEEDS_CONFIRMATION,
            "LOW",
            f"시스템 총 풍량 {_fmt(value)} m³/h 요구입니다. 필터 {_fmt(quantity)}개 × 정격 {_fmt(rated)} m³/h = {_fmt(capacity)} m³/h (참고).",
            f"정격 {_fmt(rated)} m³/h/개",
            action_items=["하우스 구성(필터 수량·배열) 기준 풍량 확인"],
            evidences=[product_evidence(product)],
            trace={"quantity": quantity, "capacity_m3h": capacity},
        )
    ok = rated >= value
    return RuleResult(
        MET if ok else NEEDS_SUPPLEMENT,
        "LOW" if ok else "MEDIUM",
        f"{product.model_no} 정격 풍량 {_fmt(rated)} m³/h — 요구 {_fmt(value)} m³/h {'충족' if ok else '미달'}.",
        f"정격 {_fmt(rated)} m³/h",
        evidences=[product_evidence(product)],
    )


MATERIAL_SYNONYMS = [
    ["ABS", "플라스틱", "Plastic"],
    ["SUS304", "SUS", "Stainless", "스테인리스", "스텐"],
    ["아연도", "Galvanized", "GI"],
    ["EPDM"],
    ["폴리우레탄", "Polyurethane", "PU"],
    ["네오프렌", "Neoprene"],
    ["유리섬유", "Glass fiber", "Glass fibre", "Fiberglass"],
    ["합성섬유", "Synthetic"],
    ["알루미늄", "Aluminum", "Aluminium"],
    ["셀룰로오스", "Cellulose"],
]
_PART_FIELDS = {
    "frame": "frame_material",
    "liner": "frame_material",
    "media": "media",
    "gasket": "gasket",
}


def _material_groups(term: str) -> list[list[str]]:
    return [g for g in MATERIAL_SYNONYMS if any(s.lower() in term.lower() for s in g)]


def material_matches(term: str, material: str) -> bool:
    if not term or not material:
        return False
    groups = _material_groups(term)
    if groups:
        return any(s.lower() in material.lower() for g in groups for s in g)
    return term.lower() in material.lower() or material.lower() in term.lower()


def evaluate_material(requirement, ctx: EvaluationContext) -> RuleResult | None:
    norm = requirement.normalized or {}
    field_name = _PART_FIELDS.get(norm.get("part") or "")
    required = [t for t in norm.get("required") or [] if t]
    forbidden = [t for t in norm.get("forbidden") or [] if t]
    if not field_name or not (required or forbidden):
        return None
    product = target_product(requirement, ctx)
    if product is None:
        return None
    material = getattr(product, field_name) or ""
    evidence = [product_evidence(product)]
    bad = [t for t in forbidden if material_matches(t, material)]
    if bad:
        return RuleResult(
            NEEDS_SUPPLEMENT,
            "HIGH",
            f"{product.model_no}의 재질({material})에 금지 재질({', '.join(bad)})이 포함됩니다.",
            material,
            action_items=["재질 변경 사양 검토"],
            evidences=evidence,
        )
    if not required:
        return RuleResult(
            MET,
            "LOW",
            f"{product.model_no} 재질({material})에 금지 재질이 없습니다.",
            material,
            evidences=evidence,
        )
    if any(material_matches(t, material) for t in required):
        return RuleResult(
            MET,
            "LOW",
            f"{product.model_no}의 재질({material})이 요구({' 또는 '.join(required)})를 만족합니다.",
            material,
            evidences=evidence,
        )
    options = [
        o
        for o in product.frame_options or []
        if field_name == "frame_material"
        and any(material_matches(t, str(o.get("material", ""))) for t in required)
    ]
    if options:
        option = options[0]
        notes = [
            record_evidence(r, r.notes)
            for r in ctx.delivery_records
            if product in r.products.all()
            and r.notes
            and any(material_matches(t, r.notes) for t in required)
        ]
        note_text = f" 납품실적 비고: {'; '.join(n['quote'] for n in notes)}." if notes else ""
        return RuleResult(
            NEEDS_SUPPLEMENT,
            "MEDIUM",
            f"표준 재질은 {material}이며, 요구 재질은 {option.get('model', '')} {option.get('material', '')} {option.get('note', '')} 옵션입니다.{note_text}",
            f"{material} (옵션: {option.get('model', '')} {option.get('material', '')})",
            action_items=[
                f"{option.get('material', '')} 주문제작 사양·납기 확인 (해당 사양 실적 없음)"
            ],
            evidences=evidence + notes,
        )
    return None  # synonym gap or free-text material → LLM


def evaluate_environment(requirement, ctx: EvaluationContext) -> RuleResult | None:
    norm = requirement.normalized or {}
    checks = [
        ("max_temp_c", "최고 온도", "℃"),
        ("max_rh", "최고 습도", "%RH"),
    ]
    wanted = [
        (k, label, unit) for k, label, unit in checks if isinstance(norm.get(k), (int, float))
    ]
    if not wanted:
        return None
    product = target_product(requirement, ctx)
    if product is None:
        return None
    lines, failed, unknown = [], [], []
    for key, label, unit in wanted:
        actual = getattr(product, key)
        if actual is None:
            unknown.append(label)
            continue
        ok = actual >= norm[key]
        lines.append(f"{label} 요구 {_fmt(norm[key])}{unit} / 제품 {_fmt(actual)}{unit}")
        if not ok:
            failed.append(label)
    evidence = [product_evidence(product)]
    if failed:
        return RuleResult(
            NEEDS_SUPPLEMENT,
            "MEDIUM",
            f"{product.model_no} 사용 환경이 요구에 못 미칩니다: {'; '.join(lines)}.",
            "; ".join(lines),
            action_items=["사용 환경 대응 사양(내습·내열) 검토"],
            evidences=evidence,
        )
    if unknown:
        return RuleResult(
            NEEDS_CONFIRMATION,
            "MEDIUM",
            f"{product.model_no}의 {', '.join(unknown)} 정보가 없습니다.",
            "; ".join(lines),
            evidences=evidence,
        )
    return RuleResult(
        MET,
        "LOW",
        f"{product.model_no} 사용 환경 충족: {'; '.join(lines)}.",
        "; ".join(lines),
        evidences=evidence,
    )


_OFFICIAL = r"listing|listed|classified|인증|등재"


def evaluate_fire_rating(requirement, ctx: EvaluationContext) -> RuleResult | None:
    norm = requirement.normalized or {}
    text = f"{norm.get('standard') or ''} {norm.get('class') or ''} {requirement.requirement_text} {requirement.title}"
    is_ul = re.search(r"UL\s*900", text, re.I)
    is_korean = "방염" in text
    if not (is_ul or is_korean):
        return None
    product = target_product(requirement, ctx)
    if product is None:
        return None
    reports = [r for r in ctx.reports_for(product) if r.standard_family == "UL900"] if is_ul else []
    if not reports:
        return RuleResult(
            NEEDS_SUPPLEMENT,
            "MEDIUM",
            f"요구 난연 기준({'UL 900' if is_ul else '방염'}) 시험 자료가 없습니다."
            + (f" 사양서 기재: {product.fire_rating}." if product.fire_rating else ""),
            product.fire_rating,
            action_items=["난연(방염) 시험 의뢰"],
            evidences=[product_evidence(product)],
        )
    report = reports[0]
    evidence = [report_evidence(report, report.notes or report.result_class)]
    official_required = bool(re.search(_OFFICIAL, text, re.I))
    if report.is_official_certification:
        return RuleResult(
            MET,
            "LOW",
            f"{report.report_no} UL 900 공식 인증 자료가 있습니다.",
            report.report_no,
            evidences=evidence,
        )
    if official_required:
        return RuleResult(
            NEEDS_SUPPLEMENT,
            "MEDIUM",
            f"공식 UL Listing/Classified가 요구되나 보유 자료는 {report.report_no} 준용 시험(공식 인증 아님)입니다.",
            f"{report.report_no} ({report.result_class}, 준용 시험)",
            action_items=["UL 공식 인증 취득 또는 준용 시험 성적서 인정 여부 질의"],
            evidences=evidence,
        )
    return RuleResult(
        MET,
        "LOW",
        f"{report.report_no} UL 900 준용 시험 결과 {report.result_class} — 공식 Listing은 아닙니다.",
        f"{report.report_no} ({report.result_class}, 준용 시험)",
        evidences=evidence,
    )


_LAB_KEYWORDS = r"KOLAS|공인|accredit"


def evaluate_test_standard(requirement, ctx: EvaluationContext) -> RuleResult | None:
    norm = requirement.normalized or {}
    family = family_of(norm.get("standard") or "") or family_of(requirement.requirement_text)
    if family is None:
        return None
    product = target_product(requirement, ctx) if requirement.item_id else None
    pool = ctx.reports_for(product) if product else ctx.test_reports
    reports = [r for r in pool if r.standard_family == family]
    label = FAMILY_LABELS.get(family, family)
    if not reports:
        return RuleResult(
            NEEDS_SUPPLEMENT,
            "MEDIUM",
            f"{label} 시험성적서를 보유하고 있지 않습니다.",
            action_items=[f"{label} 공인기관 시험 의뢰 (일정·비용 반영)"],
        )
    max_age = norm.get("max_age_years") or get_setting("evaluation.test_report_max_age_years")
    if max_age:
        cutoff = date(ctx.reference_date.year - int(max_age), ctx.reference_date.month, 1)
        fresh = [r for r in reports if r.issue_date and r.issue_date >= cutoff]
        if not fresh:
            return RuleResult(
                NEEDS_SUPPLEMENT,
                "MEDIUM",
                f"{label} 성적서가 있으나 유효 기간({max_age}년) 이내 발행본이 없습니다.",
                ", ".join(r.report_no for r in reports),
                action_items=[f"{label} 재시험 의뢰"],
                evidences=[report_evidence(r) for r in reports],
            )
        reports = fresh
    report = max(reports, key=lambda r: r.issue_date or date.min)
    evidence = [report_evidence(r) for r in reports]
    lab_requirement = norm.get("lab_requirement") or ""
    lab_note = ""
    risk = "LOW"
    if re.search(_LAB_KEYWORDS, lab_requirement, re.I) and not re.search(
        _LAB_KEYWORDS, report.lab_accreditation or "", re.I
    ):
        lab_note = f" 시험기관 요건({lab_requirement}) 충족 여부 확인이 필요합니다."
        risk = "MEDIUM"
    if report.is_obsolete_standard:
        return RuleResult(
            MET,
            "MEDIUM",
            f"{report.report_no}({report.standard}) 성적서를 보유합니다. 단, 폐지 규격(EN 779:2012 → ISO 16890 대체)입니다.{lab_note}",
            f"{report.report_no} ({report.issue_date})",
            action_items=["폐지 규격 성적서 인정 여부 확인"],
            evidences=evidence,
        )
    return RuleResult(
        MET,
        risk,
        f"{label} 시험성적서 {report.report_no}({report.lab_name})를 보유합니다.{lab_note}",
        f"{report.report_no} ({report.issue_date})",
        evidences=evidence,
    )


# ---- delivery / documents -------------------------------------------------------------


def evaluate_delivery(requirement, ctx: EvaluationContext) -> RuleResult | None:
    days = (requirement.normalized or {}).get("days_after_contract")
    if not isinstance(days, (int, float)) or not days:
        return None
    product = requirement.item.matched_product if requirement.item_id else None
    lead = (product.extra or {}).get("lead_time_days") if product else None
    lead = lead or get_setting("company.standard_lead_time_days")
    if not lead:
        return RuleResult(
            NEEDS_CONFIRMATION,
            "LOW",
            f"요구 납기는 계약 후 {_fmt(days)}일이며, 회사 표준 납기 정보가 없습니다.",
            action_items=["생산팀 납기 확인"],
        )
    ok = lead <= days
    source = (
        f"{product.model_no} 표준 납기"
        if product and (product.extra or {}).get("lead_time_days")
        else "회사 표준 납기 설정"
    )
    return RuleResult(
        MET if ok else NEEDS_SUPPLEMENT,
        "LOW" if ok else "MEDIUM",
        f"표준 납기 {_fmt(lead)}일 — 요구 계약 후 {_fmt(days)}일 {'충족' if ok else '초과'}.",
        f"표준 납기 {_fmt(lead)}일",
        action_items=[] if ok else ["분할 납품·납기 협의 또는 생산 일정 조정"],
        evidences=[
            {"type": "company", "id": 0, "label": source, "page": 0, "quote": f"{_fmt(lead)}일"}
        ],
    )


_COMPANY_ISSUED = (
    r"납품서|계약이행계획|이행계획서|치수|외관|증권|보증서|확약서|계획서|도면|data\s*sheet|QIP|ITP|"
    r"품질보증|견적|사용자\s*설명|매뉴얼|manual|명세서"
)
_CERT_KEYWORDS = [
    (r"ISO\s*9001", "ISO9001"),
    (r"ISO\s*14001", "ISO14001"),
    (r"ISO\s*45001", "ISO45001"),
    (r"직접생산", "DIRECT_PRODUCTION"),
    (r"중소기업", "SME"),
]


def evaluate_submission_doc(requirement, ctx: EvaluationContext) -> RuleResult | None:
    norm = requirement.normalized or {}
    doc = norm.get("doc") or requirement.title or requirement.requirement_text
    timing = norm.get("timing") or ""
    text = f"{doc} {requirement.requirement_text}"

    for pattern, cert_type in _CERT_KEYWORDS:
        if re.search(pattern, text, re.I):
            proxy = type(requirement)(
                bid=requirement.bid,
                category="CERTIFICATION",
                title=requirement.title,
                requirement_text=requirement.requirement_text,
                normalized={"cert_type": cert_type, "product_code": norm.get("product_code", "")},
                is_mandatory=requirement.is_mandatory,
            )
            return evaluate_certification(proxy, ctx)

    if re.search(r"성적서", text) and not re.search(r"치수|외관", text):
        family = family_of(text)
        reports = [r for r in ctx.test_reports if not family or r.standard_family == family]
        if reports:
            return RuleResult(
                MET,
                "LOW",
                f"제출할 시험성적서({', '.join(r.report_no for r in reports[:3])})를 보유합니다.",
                ", ".join(r.report_no for r in reports[:3]),
                action_items=[f"{timing or '제출 시점'}에 성적서 원본·사본 준비"],
                evidences=[report_evidence(r) for r in reports[:3]],
            )
        return RuleResult(
            NEEDS_SUPPLEMENT,
            "MEDIUM",
            f"요구 시험성적서({FAMILY_LABELS.get(family, family) if family else doc})를 보유하고 있지 않습니다.",
            action_items=["공인기관 시험 의뢰"],
        )
    if re.search(r"실적", text):
        if ctx.delivery_records:
            return RuleResult(
                MET,
                "LOW",
                f"납품실적 {len(ctx.delivery_records)}건이 있어 실적증명서 발급을 요청할 수 있습니다.",
                f"납품실적 {len(ctx.delivery_records)}건",
                action_items=["발주처별 실적증명서 발급 요청"],
                evidences=[record_evidence(r) for r in ctx.delivery_records[:3]],
            )
        return RuleResult(NEEDS_SUPPLEMENT, "HIGH", "제출할 납품실적이 없습니다.")
    if re.search(_COMPANY_ISSUED, text, re.I) or norm.get("issuer_type") in ("COMPANY", "SURETY"):
        issuer = (
            "보증보험사 발급"
            if (norm.get("issuer_type") == "SURETY" or "증권" in text)
            else "당사 작성·발급"
        )
        return RuleResult(
            MET,
            "LOW",
            f"'{doc}'은(는) {issuer} 서류로 제출 가능합니다.",
            issuer,
            action_items=[
                f"{timing or '제출 시점'}에 '{doc}' {'발급' if '발급' in issuer else '작성'}"
            ],
        )
    return None


def evaluate_placeholder(requirement, ctx: EvaluationContext) -> RuleResult:
    label = requirement.get_category_display()
    return RuleResult(
        NEEDS_CONFIRMATION,
        "MEDIUM",
        f"공고에 {label} 요구사항이 명시되어 있지 않습니다.",
        action_items=[f"발주처에 {label} 요구 조건 확인"],
        trace={
            "placeholder": True,
            "question": f"공고문에 {label} 관련 요구 조건이 없어 확인을 요청드립니다.",
        },
    )


RULES = {
    "DIMENSION": evaluate_dimension,
    "FILTER_TYPE": evaluate_filter_type,
    "FILTER_GRADE": evaluate_filter_grade,
    "EFFICIENCY": evaluate_efficiency,
    "PRESSURE_DROP": evaluate_pressure_drop,
    "AIRFLOW": evaluate_airflow,
    "MATERIAL": evaluate_material,
    "ENVIRONMENT": evaluate_environment,
    "FIRE_RATING": evaluate_fire_rating,
    "TEST_STANDARD": evaluate_test_standard,
    "CERTIFICATION": evaluate_certification,
    "TRACK_RECORD": evaluate_track_record,
    "DELIVERY": evaluate_delivery,
    "SUBMISSION_DOC": evaluate_submission_doc,
}


def evaluate(requirement, ctx: EvaluationContext) -> RuleResult | None:
    if (requirement.normalized or {}).get("placeholder"):
        return evaluate_placeholder(requirement, ctx)
    rule = RULES.get(requirement.category)
    return rule(requirement, ctx) if rule else None
