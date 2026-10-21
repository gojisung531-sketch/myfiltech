"""Item ↔ product matching and bid fit score (specs/08 §6)."""

import logging
import re
from dataclasses import dataclass

from django.db import transaction

from apps.company.models import FilterType
from apps.core.app_settings import get_setting
from apps.documents.extractors.company import classify_filter_type
from apps.llm.providers import LLMError
from apps.llm.services import LLMNotConfigured, is_llm_configured, run_task

from . import rules
from .context import EvaluationContext, nominal_family
from .grades import family_of, meets, product_grades, required_grade

logger = logging.getLogger(__name__)

MATCH_WEIGHTS = {"type": 0.35, "dimension": 0.30, "grade": 0.25, "application": 0.10}
MATCH_THRESHOLD = 0.6
TOP_N = 3

_DOMAINS = {
    "GT_INTAKE": r"가스터빈|\bGT\b|흡기|air\s*intake|공기\s*흡입|입구\s*공기|pulse",
    "HVAC": r"공조|클린룸|hvac|공기\s*조화|전산실|제어실|실험동물|역사",
}
_AXES = [
    ("w", "width_mm"),
    ("h", "height_mm"),
    ("d", "depth_mm"),
    ("dia", "diameter_mm"),
    ("dia2", "diameter2_mm"),
    ("len", "length_mm"),
]


def _domains(text: str) -> set[str]:
    return {name for name, pattern in _DOMAINS.items() if re.search(pattern, text or "", re.I)}


def item_filter_type(item) -> str:
    if item.filter_type:
        return item.filter_type
    return classify_filter_type(f"{item.name} {item.spec_text}")


@dataclass
class MatchScore:
    product: object
    score: float
    parts: dict
    reasons: list[str]

    @property
    def reason(self) -> str:
        return " · ".join(self.reasons)


def score_item_product(
    item, product, item_requirements, *, tolerance: float, nominal: dict, context_text: str = ""
) -> MatchScore:
    parts: dict[str, float] = {}
    reasons: list[str] = []

    wanted = item_filter_type(item)
    if wanted in ("", FilterType.OTHER):
        parts["type"] = 0.5
    else:
        parts["type"] = 1.0 if wanted == product.filter_type else 0.0
        reasons.append(
            f"형식 {'일치' if parts['type'] else '불일치'}({product.get_filter_type_display()})"
        )

    axis_scores = []
    for axis, field in _AXES:
        target = getattr(item, f"{field}")
        if target is None:
            continue
        actual = getattr(product, field)
        if actual is None:
            axis_scores.append(0.0)
            continue
        upper = item.depth_mm_max if axis == "d" and item.depth_mm_max else None
        if upper is not None and target - tolerance <= actual <= upper + tolerance:
            axis_scores.append(1.0)
        elif abs(actual - target) <= tolerance:
            axis_scores.append(1.0)
        elif nominal_family(actual, nominal, tolerance) and nominal_family(
            actual, nominal, tolerance
        ) == nominal_family(target, nominal, tolerance):
            axis_scores.append(0.5)
        else:
            axis_scores.append(0.0)
    parts["dimension"] = sum(axis_scores) / len(axis_scores) if axis_scores else 0.5
    if axis_scores:
        label = (
            "일치"
            if parts["dimension"] == 1
            else ("공칭 동일군" if parts["dimension"] >= 0.5 else "불일치")
        )
        reasons.append(f"치수 {label}")

    grade_scores = []
    for requirement in item_requirements:
        if requirement.category != "FILTER_GRADE":
            continue
        grade = required_grade(requirement.normalized)
        if grade is None:
            continue
        verdicts = [meets(g, grade) for g in product_grades(product)]
        if True in verdicts:
            grade_scores.append(1.0)
            reasons.append(f"등급 충족({grade})")
        elif False in verdicts:
            grade_scores.append(0.0)
            reasons.append(f"등급 미달({grade})")
        else:
            grade_scores.append(0.5)
            reasons.append(f"등급 비교 불가 — 다른 시험규격({grade})")
    parts["grade"] = sum(grade_scores) / len(grade_scores) if grade_scores else 0.5

    wanted_domains = _domains(f"{item.name} {item.spec_text} {context_text}")
    product_domains = _domains(f"{product.application} {product.name}")
    if wanted_domains and product_domains:
        parts["application"] = 1.0 if wanted_domains & product_domains else 0.0
    else:
        parts["application"] = 0.5

    score = sum(MATCH_WEIGHTS[k] * v for k, v in parts.items())
    return MatchScore(product, round(score, 3), parts, reasons)


def match_items(bid, ctx: EvaluationContext | None = None) -> None:
    """Score every item against every active product; keep the top 3 per item."""
    from apps.bids.models import BidProductMatch

    ctx = ctx or EvaluationContext.for_bid(bid)
    tolerance = float(get_setting("evaluation.dimension_tolerance_mm"))
    nominal = get_setting("evaluation.nominal_dimension_map")
    context_text = f"{bid.title} {bid.plant_name}"
    with transaction.atomic():
        BidProductMatch.objects.filter(bid=bid).delete()
        for item in bid.items.all():
            requirements = list(item.requirements.all())
            scored = sorted(
                (
                    score_item_product(
                        item,
                        p,
                        requirements,
                        tolerance=tolerance,
                        nominal=nominal,
                        context_text=context_text,
                    )
                    for p in ctx.products
                ),
                key=lambda m: m.score,
                reverse=True,
            )[:TOP_N]
            for rank, match in enumerate(scored, start=1):
                BidProductMatch.objects.create(
                    bid=bid,
                    item=item,
                    product=match.product,
                    score=match.score,
                    reason=match.reason,
                    rank=rank,
                )
            best = scored[0] if scored else None
            item.matched_product = best.product if best else None
            item.match_score = best.score if best else None
            item.save(update_fields=["matched_product", "match_score", "updated_at"])


def _fraction(values: list[float]) -> float:
    return sum(values) / len(values) if values else 1.0


def compute_fit(bid, ctx: EvaluationContext | None = None) -> dict:
    """Rule-based fit score with a per-component breakdown (specs/08 §6.2)."""
    ctx = ctx or EvaluationContext.for_bid(bid)
    weights = get_setting("fit.weights")
    items = list(bid.items.all())
    requirements = list(bid.requirements.all())

    matched = [i for i in items if (i.match_score or 0) >= MATCH_THRESHOLD]
    product_ratio = len(matched) / len(items) if items else 0.0

    keywords = get_setting("fit.power_plant_keywords")
    text = f"{bid.title} {bid.buyer_org} {bid.plant_name}"
    is_power_plant = bid.is_power_plant
    if is_power_plant is None:
        is_power_plant = any(k in text for k in keywords)

    qualification_values, qualification_detail = [], []
    for requirement in requirements:
        if requirement.category not in ("CERTIFICATION", "TRACK_RECORD"):
            continue
        result = rules.evaluate(requirement, ctx)
        if result is None:
            qualification_values.append(0.5)
            qualification_detail.append({"title": requirement.title, "verdict": None})
            continue
        qualification_values.append(1.0 if result.verdict == rules.MET else 0.0)
        qualification_detail.append(
            {"title": requirement.title, "verdict": result.verdict, "risk": result.risk_level}
        )
    blocking = any(
        d.get("risk") == "HIGH" and d.get("verdict") != rules.MET for d in qualification_detail
    )
    qualification_ratio = 0.0 if blocking else _fraction(qualification_values)

    families = {r.standard_family for r in ctx.test_reports}
    coverage = []
    for requirement in requirements:
        if requirement.category != "TEST_STANDARD":
            continue
        family = family_of(
            (requirement.normalized or {}).get("standard") or requirement.requirement_text
        )
        coverage.append(1.0 if family and family in families else 0.0)
    coverage_ratio = _fraction(coverage)

    ratios = {
        "product_type": product_ratio,
        "power_plant": 1.0 if is_power_plant else 0.0,
        "qualification": qualification_ratio,
        "spec_coverage": coverage_ratio,
    }
    breakdown = {
        key: {
            "weight": weights.get(key, 0),
            "ratio": round(ratio, 3),
            "points": round(weights.get(key, 0) * ratio, 1),
        }
        for key, ratio in ratios.items()
    }
    breakdown["product_type"]["detail"] = f"품목 {len(items)}개 중 매칭 제품 있음 {len(matched)}개"
    breakdown["qualification"]["detail"] = qualification_detail
    breakdown["spec_coverage"]["detail"] = (
        f"요구 시험규격 {len(coverage)}건 중 보유 {int(sum(coverage))}건"
    )
    score = round(sum(b["points"] for b in breakdown.values()))
    return {
        "score": max(0, min(100, score)),
        "breakdown": breakdown,
        "is_power_plant": is_power_plant,
    }


def rule_reason(fit: dict) -> str:
    b = fit["breakdown"]
    return (
        f"제품 매칭 {b['product_type']['points']}/{b['product_type']['weight']}"
        f" · 발전소 {b['power_plant']['points']}/{b['power_plant']['weight']}"
        f" · 자격 {b['qualification']['points']}/{b['qualification']['weight']}"
        f" · 시험규격 {b['spec_coverage']['points']}/{b['spec_coverage']['weight']}"
    )


def update_fit(bid, ctx: EvaluationContext | None = None, job=None) -> dict:
    """Compute the fit score, ask the LLM for a reason (±10 adjustment) and save it."""
    ctx = ctx or EvaluationContext.for_bid(bid)
    fit = compute_fit(bid, ctx)
    score, reason = fit["score"], rule_reason(fit)
    if is_llm_configured():
        try:
            data = run_task("bid.fit_score", fit_variables(bid, ctx, score), job=job).data
            adjusted = int(data.get("fit_score", score))
            score = max(0, min(100, max(score - 10, min(score + 10, adjusted))))
            reason = f"{data.get('reason', '').strip()}\n({rule_reason(fit)})"
        except (LLMError, LLMNotConfigured) as exc:
            logger.warning("fit_score LLM failed for bid %s: %s", bid.pk, exc)
    bid.fit_score = score
    bid.fit_reason = reason
    if bid.is_power_plant is None:
        bid.is_power_plant = fit["is_power_plant"]
    bid.extra = {
        **(bid.extra or {}),
        "fit_breakdown": fit["breakdown"],
        "rule_fit_score": fit["score"],
    }
    bid.save(update_fields=["fit_score", "fit_reason", "is_power_plant", "extra", "updated_at"])
    return fit


def fit_variables(bid, ctx: EvaluationContext, rule_score: int) -> dict:
    from apps.company.models import Product

    return {
        "bid_summary": bid.summary or bid.title,
        "rule_score": rule_score,
        "items": [
            {"item_no": i.item_no, "name": i.name, "spec_text": i.spec_text, "quantity": i.quantity}
            for i in bid.items.all()
        ],
        "products": [
            {
                "model_no": p.model_no,
                "name": p.name,
                "filter_type": p.get_filter_type_display(),
                "dimension": p.dimension_text,
                "grades": ", ".join(str(g) for g in product_grades(p)),
            }
            for p in ctx.products or Product.objects.none()
        ],
    }
