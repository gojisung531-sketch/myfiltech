"""EVALUATE_BID: rules → LLM (assist) → save, keeping manual edits (specs/08 §7–8)."""

import logging

from django.db import transaction
from django.utils import timezone

from apps.core.app_settings import get_setting
from apps.llm.providers import LLMError
from apps.llm.services import LLMNotConfigured, is_llm_configured, run_task

from . import rules
from .context import EvaluationContext
from .evidence import company_evidence
from .models import RISK_ORDER, EvaluationHistory, RequirementEvaluation, Verdict

logger = logging.getLogger(__name__)

VERDICT_PREFIX = {
    Verdict.MET: "충족",
    Verdict.NEEDS_SUPPLEMENT: "보완 필요",
    Verdict.NEEDS_CONFIRMATION: "확인 필요",
}
EDITABLE_FIELDS = [
    "verdict",
    "risk_level",
    "company_value",
    "auto_answer",
    "rationale",
    "action_items",
    "clarification_question",
    "evidences",
]


def _noop(progress, message=""):
    return None


def template_answer(verdict: str, company_value: str, rationale: str, actions: list[str]) -> str:
    """Compliance-matrix answer built from a rule result when no LLM is used (specs/08 §7.1)."""
    prefix = VERDICT_PREFIX.get(verdict, verdict)
    if verdict == Verdict.MET and company_value:
        return f"{prefix} — {company_value}"
    answer = f"{prefix} — {rationale}"
    if verdict == Verdict.NEEDS_SUPPLEMENT and actions:
        answer += f" {actions[0]} 예정."
    return answer


def bid_quote(requirement) -> dict | None:
    if not requirement.source_quote:
        return None
    attachment = requirement.source_attachment
    return {
        "type": "bid_quote",
        "id": attachment.pk if attachment else 0,
        "label": attachment.document.display_name if attachment else "공고",
        "page": requirement.source_page or 0,
        "quote": requirement.source_quote,
    }


def bid_context(bid, ctx: EvaluationContext) -> str:
    lines = [
        f"공고명: {bid.title}",
        f"공고번호: {bid.notice_no or '-'}",
        f"수요기관: {bid.buyer_org or '-'}",
        f"입찰 마감: {timezone.localtime(bid.bid_close_at):%Y-%m-%d %H:%M}"
        if bid.bid_close_at
        else "입찰 마감: -",
        f"판정 기준일: {ctx.reference_date}"
        + (" (과거 공고 — 오늘 기준 재입찰 시뮬레이션)" if ctx.is_simulation else ""),
    ]
    if bid.summary:
        lines.append(f"요약: {bid.summary}")
    for item in bid.items.select_related("matched_product"):
        product = item.matched_product.model_no if item.matched_product else "매칭 제품 없음"
        lines.append(f"품목 {item.item_no or '-'}: {item.name} / {item.spec_text} → {product}")
    return "\n".join(lines)


def _rule_payload(result: rules.RuleResult | None) -> dict | None:
    if result is None:
        return None
    return {
        "verdict": result.verdict,
        "risk_level": result.risk_level,
        "company_value": result.company_value,
        "rationale": result.rationale,
        "action_items": result.action_items,
        "evidences": result.evidences,
    }


def _requirement_payload(requirement, result, ctx) -> dict:
    return {
        "id": requirement.pk,
        "category": requirement.category,
        "category_label": requirement.get_category_display(),
        "title": requirement.title,
        "requirement_text": requirement.requirement_text,
        "normalized": requirement.normalized,
        "is_mandatory": requirement.is_mandatory,
        "item": str(requirement.item) if requirement.item_id else "",
        "source_quote": requirement.source_quote,
        "rule_result": _rule_payload(result),
        "company_evidence": company_evidence(requirement, ctx),
    }


def _judge(bid, batch: list[tuple], ctx, job) -> tuple[dict[int, dict], object]:
    """Run evaluation.judge for one batch. Returns ({requirement_id: result}, call_log)."""
    variables = {
        "bid_context": bid_context(bid, ctx),
        "requirements": [_requirement_payload(req, rr, ctx) for req, rr in batch],
        "verdict_definitions": get_setting("evaluation.verdict_definitions"),
    }
    try:
        result = run_task("evaluation.judge", variables, job=job)
    except (LLMError, LLMNotConfigured) as exc:  # includes LLMInvalidOutput
        logger.warning("evaluation.judge failed for bid %s: %s", bid.pk, exc)
        return {}, None
    by_id = {}
    for out in result.data.get("results") or []:
        if isinstance(out, dict) and isinstance(out.get("requirement_id"), int):
            by_id[out["requirement_id"]] = out
    return by_id, result.call_log


def _unique(values) -> list[str]:
    return list(dict.fromkeys(v.strip() for v in values if isinstance(v, str) and v.strip()))


def _llm_evidences(out: dict) -> list[dict]:
    refs = []
    for ref in out.get("evidence_refs") or []:
        if isinstance(ref, dict) and (ref.get("label") or "").strip():
            refs.append(
                {
                    "type": ref.get("type") or "document",
                    "id": ref.get("id") or 0,
                    "label": ref["label"],
                    "page": ref.get("page") or 0,
                    "quote": ref.get("quote") or "",
                }
            )
    return refs


def merge(requirement, result: rules.RuleResult | None, out: dict | None) -> dict:
    """Combine rule and LLM output. A rule verdict is never changed by the LLM."""
    quote = bid_quote(requirement)
    if result is not None:
        risk = result.risk_level
        if out and RISK_ORDER.get(out.get("risk_level"), 0) > RISK_ORDER[risk]:
            risk = out["risk_level"]
        rationale = result.rationale
        llm_rationale = (out or {}).get("rationale", "").strip()
        if llm_rationale and llm_rationale not in rationale:
            rationale = f"{rationale}\n{llm_rationale}"
        actions = _unique(result.action_items + list((out or {}).get("action_items") or []))
        company_value = result.company_value or (out or {}).get("company_value", "")
        data = {
            "verdict": result.verdict,
            "risk_level": risk,
            "company_value": company_value,
            "rationale": rationale,
            "action_items": actions,
            "clarification_question": (out or {}).get("clarification_question", "")
            or result.trace.get("question", ""),
            "evidences": result.evidences + ([quote] if quote else []),
            "auto_answer": (out or {}).get("auto_answer", "").strip()
            or template_answer(result.verdict, company_value, result.rationale, actions),
            "decided_by": RequirementEvaluation.DecidedBy.RULE_LLM
            if out
            else RequirementEvaluation.DecidedBy.RULE,
            "rule_trace": result.trace,
        }
    elif out:
        verdict = out.get("verdict") or Verdict.NEEDS_CONFIRMATION
        evidences = _llm_evidences(out)
        rationale = out.get("rationale", "")
        if verdict == Verdict.MET and not evidences:
            verdict = Verdict.NEEDS_CONFIRMATION
            rationale = (
                f"{rationale}\n(근거 자료가 제시되지 않아 '확인 필요'로 조정했습니다.)".strip()
            )
        data = {
            "verdict": verdict,
            "risk_level": out.get("risk_level") or "MEDIUM",
            "company_value": out.get("company_value", ""),
            "rationale": rationale,
            "action_items": _unique(out.get("action_items") or []),
            "clarification_question": out.get("clarification_question", ""),
            "evidences": evidences + ([quote] if quote else []),
            "auto_answer": out.get("auto_answer", "")
            or template_answer(verdict, out.get("company_value", ""), rationale, []),
            "decided_by": RequirementEvaluation.DecidedBy.LLM,
            "rule_trace": {},
        }
    else:
        rationale = "규칙으로 판정할 수 없고 LLM 판정 결과가 없어 담당자 확인이 필요합니다."
        data = {
            "verdict": Verdict.NEEDS_CONFIRMATION,
            "risk_level": "MEDIUM" if requirement.is_mandatory else "LOW",
            "company_value": "",
            "rationale": rationale,
            "action_items": ["담당자 검토"],
            "clarification_question": "",
            "evidences": [quote] if quote else [],
            "auto_answer": template_answer(Verdict.NEEDS_CONFIRMATION, "", rationale, []),
            "decided_by": RequirementEvaluation.DecidedBy.RULE,
            "rule_trace": {"unjudged": True},  # internal note, not for buyer-facing drafts
        }
    return data


def save_evaluation(requirement, data: dict, call_log=None) -> RequirementEvaluation:
    evaluation = getattr(requirement, "evaluation", None) or RequirementEvaluation(
        requirement=requirement
    )
    for name, value in data.items():
        setattr(evaluation, name, value)
    evaluation.ai_verdict = data["verdict"]
    evaluation.ai_answer = data["auto_answer"]
    evaluation.is_modified = False
    evaluation.modified_by = None
    evaluation.modified_at = None
    evaluation.llm_call = call_log
    evaluation.save()
    EvaluationHistory.objects.create(evaluation=evaluation, snapshot=evaluation.snapshot())
    return evaluation


def verdict_counts(bid) -> dict:
    evaluations = RequirementEvaluation.objects.filter(requirement__bid=bid)
    counts = {v: 0 for v in Verdict.values}
    high = 0
    for verdict, risk in evaluations.values_list("verdict", "risk_level"):
        counts[verdict] = counts.get(verdict, 0) + 1
        high += risk == "HIGH"
    return {**counts, "HIGH": high, "total": sum(counts.values())}


def refresh_counts(bid) -> dict:
    counts = verdict_counts(bid)
    bid.extra = {**(bid.extra or {}), "verdict_counts": counts}
    bid.save(update_fields=["extra", "updated_at"])
    return counts


def evaluate_bid(
    bid,
    *,
    keep_modified: bool = True,
    requirement_ids: list[int] | None = None,
    job=None,
    report=_noop,
) -> dict:
    status = bid.ProcessingStatus
    bid.processing_status = status.EVALUATING
    bid.processing_error = ""
    bid.save(update_fields=["processing_status", "processing_error", "updated_at"])
    try:
        ctx = EvaluationContext.for_bid(bid)
        requirements = bid.requirements.select_related(
            "item__matched_product", "source_attachment__document", "evaluation"
        )
        if requirement_ids:
            requirements = requirements.filter(pk__in=requirement_ids)
        pending, skipped = [], 0
        for requirement in requirements:
            existing = getattr(requirement, "evaluation", None)
            if keep_modified and existing and existing.is_modified:
                skipped += 1
                continue
            try:
                result = rules.evaluate(requirement, ctx)
            except Exception:  # a broken rule must not stop the whole bid
                logger.exception("rule failed for requirement %s", requirement.pk)
                result = None
            pending.append((requirement, result))

        use_llm = get_setting("evaluation.use_llm") and is_llm_configured()
        size = max(1, int(get_setting("evaluation.batch_size")))
        counts = {"rule": 0, "llm": 0}
        done = 0
        for start in range(0, len(pending), size):
            batch = pending[start : start + size]
            outs, call_log = ({}, None)
            if use_llm:
                report(10 + int(80 * done / max(1, len(pending))), "LLM 판정 중")
                outs, call_log = _judge(bid, batch, ctx, job)
            with transaction.atomic():
                for requirement, result in batch:
                    out = outs.get(requirement.pk)
                    save_evaluation(
                        requirement, merge(requirement, result, out), call_log if out else None
                    )
                    counts["rule" if result else "llm"] += 1
            done += len(batch)
        summary = refresh_counts(bid)
    except Exception as exc:
        bid.processing_status = status.FAILED
        bid.processing_error = f"판정 실패: {exc}"[:2000]
        bid.save(update_fields=["processing_status", "processing_error", "updated_at"])
        raise
    bid.processing_status = status.EVALUATED
    bid.save(update_fields=["processing_status", "updated_at"])
    report(100, "판정 완료")
    return {
        "bid_id": bid.pk,
        "evaluated": len(pending),
        "skipped_modified": skipped,
        "by_rule": counts["rule"],
        "llm_used": bool(use_llm),
        "counts": summary,
        "reference_date": str(ctx.reference_date),
    }


def update_evaluation(evaluation: RequirementEvaluation, data: dict, user) -> RequirementEvaluation:
    for name in EDITABLE_FIELDS:
        if name in data:
            setattr(evaluation, name, data[name])
    evaluation.is_modified = True
    evaluation.decided_by = RequirementEvaluation.DecidedBy.MANUAL
    evaluation.modified_by = user
    evaluation.modified_at = timezone.now()
    evaluation.save()
    EvaluationHistory.objects.create(
        evaluation=evaluation, snapshot=evaluation.snapshot(), changed_by=user
    )
    refresh_counts(evaluation.requirement.bid)
    return evaluation


def revert_evaluation(evaluation: RequirementEvaluation, user) -> RequirementEvaluation:
    """Restore the last automatic snapshot (specs/08 §8)."""
    last_ai = evaluation.history.filter(changed_by__isnull=True).first()
    if last_ai is None:
        raise ValueError("되돌릴 자동 판정 기록이 없습니다.")
    for name, value in last_ai.snapshot.items():
        setattr(evaluation, name, value)
    evaluation.is_modified = False
    evaluation.modified_by = None
    evaluation.modified_at = None
    evaluation.save()
    EvaluationHistory.objects.create(
        evaluation=evaluation, snapshot=evaluation.snapshot(), changed_by=user
    )
    refresh_counts(evaluation.requirement.bid)
    return evaluation
