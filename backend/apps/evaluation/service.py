"""EVALUATE_BID: rules → LLM (assist) → save, keeping manual edits (specs/08 §7–8)."""

import json
import logging

from django.utils import timezone

from apps.core.app_settings import get_setting
from apps.core.freshness import InputsChanged, begin_run, fail_run, finish_run, output_snapshot
from apps.llm.providers import LLMError
from apps.llm.services import LLMNotConfigured, is_llm_configured, run_task

from . import rules
from .context import EvaluationContext
from .evidence import company_evidence, product_evidence
from .formal_sources import catalog, rule_with_formal_sources, validate_judgment
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
        "source": bid_quote(requirement),
        "rule_result": _rule_payload(result),
        "company_evidence": company_evidence(requirement, ctx),
    }


def _judge(
    bid, batch: list[tuple], ctx, job, *, formal_sources=False
) -> tuple[dict[int, dict], object]:
    """Run evaluation.judge for one batch. Returns ({requirement_id: result}, call_log)."""
    variables = {
        "bid_context": bid_context(bid, ctx),
        "requirements": [_requirement_payload(req, rr, ctx) for req, rr in batch],
        "verdict_definitions": get_setting("evaluation.verdict_definitions"),
    }
    if formal_sources:
        from apps.llm.models import PromptTemplate
        from apps.llm.prompts import render

        shared = {**company_evidence(batch[0][0], ctx), **catalog(ctx)}
        for row in variables["requirements"]:
            row["company_evidence"] = {
                "shared_source": "bid_context.CURRENT_FORMAL_COMPANY_DATA",
                "comparison_candidates": row["company_evidence"].get("comparison_candidates", []),
            }
        variables["bid_context"] += (
            "\nCURRENT_FORMAL_COMPANY_DATA\n"
            + json.dumps(shared, ensure_ascii=False, default=str)
            + "\n없는 자료/쪽/인용을 만들지 말 것. 증서 보유만으로 복합 자격·이행 완료를 판정하지 말 것."
        )
        template = PromptTemplate.active("evaluation.judge")
        limit = get_setting("llm.max_input_chars")
        if limit and len(render(template.user_prompt_template, variables)) > limit:
            raise ValueError(
                "정식 자료 입력이 프롬프트 한도를 초과합니다. 잘라서 판정하지 않습니다."
            )
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
                    **{
                        k: ref[k]
                        for k in ("document_id", "source_sha256", "quote_verification")
                        if k in ref
                    },
                }
            )
    return refs


def merge(requirement, result: rules.RuleResult | None, out: dict | None) -> dict:
    """Combine rule and LLM output. A rule verdict is never changed by the LLM."""
    if result and (
        result.trace.get("interpretation_review") or result.trace.get("selection_status")
    ):
        out = None  # A generated answer must not hide a reviewed ambiguity/candidate limitation.
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
            "rule_trace": {"source_validation": out["_source_validation"]}
            if out.get("_source_validation")
            else {},
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


def validate_judgment_sources(out: dict, ctx, requirement=None) -> dict:
    """Bound a source-scoped run to supplied, verified company references.

    Catalog references describe manufacturer claims; they cannot establish a test,
    certificate, commercial commitment or a selected product for a general requirement.
    """
    allowed = {}
    for product in ctx.products:
        if product.source_document_id and (product.extra or {}).get("manufacturer_source"):
            ref = product_evidence(product)
            allowed[(ref["type"], ref["id"], ref["page"], ref["quote"])] = ref
    refs = []
    for ref in _llm_evidences(out):
        key = (ref["type"], ref["id"], ref["page"], ref["quote"])
        if key in allowed:
            refs.append(allowed[key])
    result = {**out, "evidence_refs": refs}
    if out.get("verdict") != Verdict.NEEDS_CONFIRMATION:
        result["verdict"] = Verdict.NEEDS_CONFIRMATION
        result["rationale"] = (
            "제공된 제조사 후보 자료는 해당 회사의 이행·시험·자격 완료를 입증하지 않습니다. "
            "해당 요구의 직접 근거와 적용 대상 확인이 필요합니다."
        )
        result["auto_answer"] = template_answer(
            Verdict.NEEDS_CONFIRMATION, "", result["rationale"], []
        )
    if not refs:
        title = requirement.title if requirement is not None else "해당 요구"
        result["company_value"] = "카탈로그 사양은 별도 등록; 이 요구의 직접 이행 근거 미확인"
        result["verdict"] = Verdict.NEEDS_CONFIRMATION
        result["rationale"] = (
            f"'{title}'의 회사 이행·자격·절차 완료를 확인할 직접 근거가 현재 입력에 없습니다. "
            "등록된 제조사 사양은 해당 범위에서 비교하며, 이를 회사 미보유·실제 미달이나 시험·제출 완료로 확대하지 않습니다. "
            "추출되지 않은 세부 조건은 원문에서 확인해야 합니다."
        )
        result["auto_answer"] = template_answer(
            Verdict.NEEDS_CONFIRMATION, "", result["rationale"], []
        )
        result["action_items"] = [
            f"'{title}'의 적용·이행 범위와 직접 자료 확인; 현재 카탈로그 비교는 계속 활용"
        ]
        result["clarification_question"] = ""
        result["_source_validation"] = {
            "company_reference_verified": False,
            "unverified_generated_details_not_published": True,
        }
    return result


def save_evaluation(
    requirement, data: dict, call_log=None, analysis_run=None
) -> RequirementEvaluation:
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
    evaluation.analysis_run = analysis_run
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
    rules_first: bool = False,
    source_scoped: bool = False,
    formal_sources: bool = False,
) -> dict:
    if source_scoped and formal_sources:
        raise ValueError("카탈로그 전용과 정식 회사자료 실행은 동시에 지정할 수 없습니다.")
    status = bid.ProcessingStatus
    bid.processing_status = status.EVALUATING
    bid.processing_error = ""
    bid.save(update_fields=["processing_status", "processing_error", "updated_at"])
    run = None
    try:
        run = begin_run(
            bid.pk,
            "EVALUATION",
            {
                "keep_modified": keep_modified,
                "requirement_ids": requirement_ids,
                "rules_first": rules_first,
                "source_scoped": source_scoped,
                "formal_sources": formal_sources,
            },
        )
        bid.refresh_from_db()  # match the captured input rather than a caller's stale object
        ctx = EvaluationContext.for_bid(bid)
        if formal_sources:
            current = catalog(ctx)
            anchors = current["company_sources"] + [
                source for cert in current["certificates"] for source in cert["sources"]
            ]
            if any(
                source["source_verification"] != "VERIFIED"
                or source["record_value_consistency"] != "MATCHES_REVIEW"
                for source in anchors
            ) or any(not cert["sources"] for cert in current["certificates"]):
                raise ValueError("정식 자료의 원본/수동 검토 메타데이터 대조에 실패했습니다.")
        if source_scoped and (ctx.test_reports or ctx.certificates or ctx.delivery_records):
            raise ValueError(
                "카탈로그 후보 전용 실행에 다른 정식 자료가 있습니다. 근거 범위를 다시 검토하세요."
            )
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
                if formal_sources:
                    result = rule_with_formal_sources(requirement, result, ctx)
            except Exception:  # a broken rule must not stop the whole bid
                logger.exception("rule failed for requirement %s", requirement.pk)
                result = None
            pending.append((requirement, result))

        if rules_first:
            pending.sort(key=lambda pair: pair[1] is None)
        use_llm = get_setting("evaluation.use_llm") and is_llm_configured()
        size = max(1, int(get_setting("evaluation.batch_size")))
        counts = {"rule": 0, "llm": 0}
        judge_batches = 0
        done = 0
        prepared = []
        for start in range(0, len(pending), size):
            batch = pending[start : start + size]
            outs, call_log = ({}, None)
            judge_batch = [(req, rr) for req, rr in batch if rr is None] if rules_first else batch
            if use_llm and judge_batch:
                report(10 + int(80 * done / max(1, len(pending))), "LLM 판정 중")
                if formal_sources:
                    outs, call_log = _judge(bid, judge_batch, ctx, job, formal_sources=True)
                else:
                    outs, call_log = _judge(bid, judge_batch, ctx, job)
                judge_batches += 1
            for requirement, result in batch:
                out = outs.get(requirement.pk)
                if out and source_scoped:
                    out = validate_judgment_sources(out, ctx, requirement)
                if out and formal_sources:
                    out = validate_judgment(out, ctx, requirement)
                prepared.append(
                    (requirement, merge(requirement, result, out), call_log if out else None)
                )
                counts["rule" if result else "llm"] += 1
            done += len(batch)
        with finish_run(run):
            for requirement, data, call_log in prepared:
                saved = save_evaluation(requirement, data, call_log, analysis_run=run)
                run.outputs[str(saved.pk)] = output_snapshot(saved)
            summary = refresh_counts(bid)
    except Exception as exc:
        if run:
            fail_run(
                run, "INPUTS_CHANGED" if isinstance(exc, InputsChanged) else "EXECUTION_FAILED"
            )
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
        "llm_used": bool(judge_batches),
        "judge_batches": judge_batches,
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
    last_ai = (
        evaluation.history.filter(changed_by__isnull=True)
        .exclude(snapshot__decided_by=RequirementEvaluation.DecidedBy.MANUAL)
        .first()
    )
    if last_ai is None:
        raise ValueError("되돌릴 자동 판정 기록이 없습니다.")
    evaluation.analysis_run_id = last_ai.snapshot.get("analysis_run_id")
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
