"""Draft generators (specs/09). Each builds a deterministic draft from requirements and
evaluations, then (when `evaluation.use_llm` and an API key are set) lets the LLM polish it.
An LLM failure never blocks a draft — the deterministic content is kept."""

import logging
import re

from django.utils import timezone

from apps.bids.models import RequirementCategory
from apps.company.models import Company
from apps.core.app_settings import get_setting
from apps.evaluation.service import verdict_counts
from apps.llm.providers import LLMError
from apps.llm.services import LLMNotConfigured, is_llm_configured, run_task

from .models import DraftType

logger = logging.getLogger(__name__)

VERDICT_LABELS = {"MET": "충족", "NEEDS_SUPPLEMENT": "보완 필요", "NEEDS_CONFIRMATION": "확인 필요"}
CATEGORY_ORDER = {value: i for i, value in enumerate(RequirementCategory.values)}
CHECKLIST_SECTIONS = [
    "입찰 참가 자격",
    "입찰 시 제출서류",
    "실적심사 / 적격심사",
    "계약 시 제출서류",
    "납품 시 제출서류",
    "시험 · 검사 준비",
    "주요 일정",
]
# NEEDS_SUPPLEMENT items for which an alternative can be proposed to the buyer (specs/09 §3).
QUERY_SUPPLEMENT_CATEGORIES = {
    "FILTER_GRADE",
    "DIMENSION",
    "MATERIAL",
    "TEST_STANDARD",
    "EFFICIENCY",
}


def use_llm() -> bool:
    return bool(get_setting("evaluation.use_llm")) and is_llm_configured()


def _llm(
    task_key: str, variables: dict, job=None, allow: bool = True, required: str | None = None
) -> dict | None:
    """Run a draft task. With `required`, an empty list in that key (seen with real calls:
    a schema-valid but empty letter) is retried once, then treated as no LLM result."""
    if not (allow and use_llm()):
        return None
    for _ in range(2 if required else 1):
        try:
            data = run_task(task_key, variables, job=job).data
        except (LLMError, LLMNotConfigured) as exc:
            logger.warning("%s failed: %s", task_key, exc)
            return None
        if not required or data.get(required):
            return data
        logger.warning("%s returned no %s; retrying", task_key, required)
    return None


def _date(value) -> str:
    return timezone.localtime(value).strftime("%Y-%m-%d %H:%M") if value else ""


def _requirements(bid) -> list:
    """Requirements ordered item → category (specs/09 §1)."""
    requirements = list(
        bid.requirements.select_related("item", "source_attachment__document", "evaluation")
    )
    return sorted(
        requirements,
        key=lambda r: (
            r.item.item_no if r.item_id else "~",  # bid-level rows after item rows
            CATEGORY_ORDER.get(r.category, 99),
            r.order,
            r.pk,
        ),
    )


def _evaluation(requirement):
    return getattr(requirement, "evaluation", None)


def _clause(requirement) -> str:
    attachment = requirement.source_attachment
    if attachment is None:
        return ""
    page = f" p.{requirement.source_page}" if requirement.source_page else ""
    return f"{attachment.document.display_name}{page}"


def _evidence_text(evaluation) -> str:
    if evaluation is None:
        return ""
    labels = []
    for e in evaluation.evidences or []:
        if e.get("type") == "bid_quote":
            continue
        page = f" p.{e['page']}" if e.get("page") else ""
        labels.append(f"{e.get('label', '')}{page}")
    return "; ".join(labels)


def bid_info(bid) -> dict:
    return {
        "title": bid.title,
        "notice_no": bid.notice_no,
        "buyer_org": bid.buyer_org,
        "contracting_org": bid.contracting_org,
        "bid_close_at": _date(bid.bid_close_at),
        "bid_open_at": _date(bid.bid_open_at),
        "opening_at": _date(bid.opening_at),
        "qualification_deadline_at": _date(bid.qualification_deadline_at),
        "budget_krw": bid.budget_krw,
        "estimated_price_krw": bid.estimated_price_krw,
        "bid_method": bid.bid_method,
        "delivery_terms": bid.delivery_terms,
        "delivery_place": bid.delivery_place,
        "warranty_terms": bid.warranty_terms,
        "summary": bid.summary,
    }


def _prepared_by(user) -> str:
    return (user.display_name or user.username) if user else ""


# ---- 1. Compliance Matrix ------------------------------------------------------------


def compliance_matrix(bid, user=None, job=None, allow_llm: bool = True) -> tuple[dict, bool]:
    company = Company.load()
    rows = []
    for no, requirement in enumerate(_requirements(bid), start=1):
        evaluation = _evaluation(requirement)
        rows.append(
            {
                "no": no,
                "requirement_id": requirement.pk,
                "item": str(requirement.item) if requirement.item_id else "공통",
                "category": requirement.get_category_display(),
                "clause": _clause(requirement),
                "requirement": requirement.requirement_text or requirement.title,
                "offered": evaluation.company_value if evaluation else "",
                "compliance": VERDICT_LABELS.get(evaluation.verdict, "")
                if evaluation
                else "미판정",
                "risk": evaluation.risk_level if evaluation else "",
                "response": evaluation.auto_answer if evaluation else "",
                "evidence": _evidence_text(evaluation),
                "remark": "",
            }
        )
    content = {
        "header": {
            "bid_title": bid.title,
            "notice_no": bid.notice_no,
            "buyer_org": bid.buyer_org,
            "prepared_by": _prepared_by(user),
            "prepared_at": timezone.localdate().isoformat(),
            "company": company.name,
        },
        "rows": rows,
    }
    data = _llm(
        "draft.compliance_matrix",
        {
            "bid": bid_info(bid),
            "rows": [
                {
                    "id": r["requirement_id"],
                    "requirement": r["requirement"],
                    "compliance": r["compliance"],
                    "offered": r["offered"],
                    "response": r["response"],
                }
                for r in rows
            ],
        },
        job,
        allow_llm,
    )
    if data:
        polished = {o["id"]: o for o in data.get("rows") or [] if isinstance(o, dict)}
        for row in rows:
            out = polished.get(row["requirement_id"])
            if out:
                row["response"] = out.get("response") or row["response"]
                row["remark"] = out.get("remark") or ""
    return content, bool(data)


# ---- 2. Checklist --------------------------------------------------------------------


def _item(text, *, due="", verdict="", note="") -> dict:
    return {
        "text": text,
        "due": due,
        "owner": "",
        "status": "TODO",
        "verdict": verdict,
        "note": note,
    }


def _section_for(requirement) -> list[str]:
    category = requirement.category
    if category == "CERTIFICATION":
        return ["입찰 참가 자격"]
    if category == "TRACK_RECORD":
        return ["입찰 참가 자격", "실적심사 / 적격심사"]
    if category == "SUBMISSION_DOC":
        timing = (requirement.normalized or {}).get("timing") or ""
        text = f"{timing} {requirement.title} {requirement.requirement_text}"
        if "실적" in text or "적격" in text or "심사" in text:
            return ["실적심사 / 적격심사"]
        if "계약" in timing:
            return ["계약 시 제출서류"]
        if "납품" in timing:
            return ["납품 시 제출서류"]
        return ["입찰 시 제출서류"]
    if category in ("INSPECTION", "TEST_STANDARD"):
        return ["시험 · 검사 준비"]
    if category == "DELIVERY":
        return ["주요 일정"]
    return []


def base_checklist(bid) -> dict:
    sections = {title: [] for title in CHECKLIST_SECTIONS}
    for requirement in _requirements(bid):
        evaluation = _evaluation(requirement)
        verdict = VERDICT_LABELS.get(evaluation.verdict, "") if evaluation else ""
        for title in _section_for(requirement):
            sections[title].append(
                _item(
                    requirement.title
                    + (
                        f" — {requirement.requirement_text}" if requirement.requirement_text else ""
                    ),
                    verdict=verdict,
                    note=(
                        evaluation.action_items[0] if evaluation and evaluation.action_items else ""
                    ),
                )
            )
        if evaluation and evaluation.verdict == "NEEDS_SUPPLEMENT":
            for action in evaluation.action_items:
                if re.search(r"시험|성적서", action):
                    sections["시험 · 검사 준비"].append(_item(action, verdict=verdict))
    schedule = [
        ("자격(실적) 서류 제출 마감", bid.qualification_deadline_at),
        ("입찰 개시", bid.bid_open_at),
        ("전자입찰서 제출 마감", bid.bid_close_at),
        ("개찰", bid.opening_at),
    ]
    sections["주요 일정"] = [_item(text, due=_date(at)) for text, at in schedule if at] + sections[
        "주요 일정"
    ]
    return {"sections": [{"title": t, "items": items} for t, items in sections.items()]}


def checklist(bid, user=None, job=None, allow_llm: bool = True) -> tuple[dict, bool]:
    content = base_checklist(bid)
    requirements = []
    for requirement in _requirements(bid):
        if requirement.category not in (
            "CERTIFICATION",
            "TRACK_RECORD",
            "SUBMISSION_DOC",
            "INSPECTION",
            "DELIVERY",
            "TEST_STANDARD",
        ):
            continue
        evaluation = _evaluation(requirement)
        requirements.append(
            {
                "category": requirement.get_category_display(),
                "title": requirement.title,
                "requirement_text": requirement.requirement_text,
                "normalized": requirement.normalized,
                "verdict": VERDICT_LABELS.get(evaluation.verdict, "") if evaluation else "",
                "action_items": evaluation.action_items if evaluation else [],
            }
        )
    from apps.company.models import Certificate, TestReport

    data = _llm(
        "draft.checklist",
        {
            "bid": bid_info(bid),
            "requirements": requirements,
            "evaluations": [],
            "company_docs": {
                "certificates": [
                    f"{c.name} {c.cert_no} (~{c.valid_until})" for c in Certificate.objects.all()
                ],
                "test_reports": [f"{t.report_no} {t.standard}" for t in TestReport.objects.all()],
            },
        },
        job,
        allow_llm,
        required="sections",
    )
    if data and data.get("sections"):
        by_title = {
            s.get("title"): s.get("items") or [] for s in data["sections"] if isinstance(s, dict)
        }
        merged = []
        for title in CHECKLIST_SECTIONS:
            merged.append({"title": title, "items": by_title.pop(title, None) or []})
        merged += [{"title": t, "items": items} for t, items in by_title.items() if t]
        # keep the deterministic schedule if the LLM left it out
        schedule = next(s for s in merged if s["title"] == "주요 일정")
        if not schedule["items"]:
            schedule["items"] = next(
                s["items"] for s in content["sections"] if s["title"] == "주요 일정"
            )
        return {"sections": merged}, True
    return content, False


# ---- 3. Technical query --------------------------------------------------------------


def query_candidates(bid) -> list:
    rows = []
    for requirement in _requirements(bid):
        evaluation = _evaluation(requirement)
        if evaluation is None:
            continue
        if evaluation.verdict == "NEEDS_CONFIRMATION" or (
            evaluation.verdict == "NEEDS_SUPPLEMENT"
            and requirement.category in QUERY_SUPPLEMENT_CATEGORIES
        ):
            rows.append((requirement, evaluation))
    return rows


def technical_query(bid, user=None, job=None, allow_llm: bool = True) -> tuple[dict, bool]:
    company = Company.load()
    questions = []
    for no, (requirement, evaluation) in enumerate(query_candidates(bid), start=1):
        question = evaluation.clarification_question or (
            f"'{requirement.title}' 요구사항({requirement.requirement_text or '-'})의 적용 기준을 확인 부탁드립니다."
        )
        questions.append(
            {
                "no": no,
                "reference": _clause(requirement) or requirement.get_category_display(),
                "question": question,
                "background": ""
                if (evaluation.rule_trace or {}).get("unjudged")
                else evaluation.rationale,
                "proposed_alternative": "; ".join(evaluation.action_items)
                if evaluation.verdict == "NEEDS_SUPPLEMENT"
                else "",
                "requirement_id": requirement.pk,
            }
        )
    subject = (
        f"[{bid.notice_no}] {bid.title} 관련 기술 질의"
        if bid.notice_no
        else f"{bid.title} 관련 기술 질의"
    )
    content = {
        "header": {
            "to": f"{bid.buyer_org or bid.contracting_org or '발주처'} 담당자 귀하",
            "from": f"{company.name} 기술영업부",
            "date": timezone.localdate().isoformat(),
            "subject": subject,
        },
        "intro": f"귀 기관의 「{bid.title}」 공고와 관련하여 아래와 같이 기술 사항을 질의드리오니 검토 후 회신 부탁드립니다.",
        "questions": questions,
        "closing": "바쁘신 중에도 검토해 주셔서 감사합니다. 회신 내용은 입찰 준비에 반영하겠습니다.",
    }
    if not questions:
        return content, False
    data = _llm(
        "draft.technical_query",
        {
            "bid": bid_info(bid),
            "questions": [{k: v for k, v in q.items() if k != "no"} for q in questions],
        },
        job,
        allow_llm,
        required="questions",
    )
    if data and data.get("questions"):
        valid_ids = {q["requirement_id"] for q in questions}
        llm_questions = []
        for no, q in enumerate(data["questions"], start=1):
            if not isinstance(q, dict) or not q.get("question"):
                continue
            q = {**q, "no": no}
            if q.get("requirement_id") not in valid_ids:
                q["requirement_id"] = 0
            llm_questions.append(q)
        header = {**content["header"], **{k: v for k, v in (data.get("header") or {}).items() if v}}
        return {
            "header": header,
            "intro": data.get("intro") or content["intro"],
            "questions": llm_questions or questions,
            "closing": data.get("closing") or content["closing"],
        }, True
    return content, False


# ---- 4. Review report ----------------------------------------------------------------


def _first_line(text: str) -> str:
    return next((line.strip() for line in (text or "").splitlines() if line.strip()), "-")


def rule_recommendation(bid, stats: dict) -> tuple[str, str]:
    high_supplement = stats["high_supplement"]
    if bid.fit_score is not None and bid.fit_score < 40:
        return "NO_BID", f"적합도 {bid.fit_score}점으로 낮아 입찰 실익이 적습니다."
    if high_supplement or stats["high_risk"]:
        return (
            "CONDITIONAL",
            f"HIGH 위험 요구사항 {stats['high_risk']}건의 보완·확인이 선행되어야 입찰할 수 있습니다.",
        )
    return "BID", "주요 요구사항을 충족하거나 보완 가능하여 입찰을 권고합니다."


def review_report(bid, user=None, job=None, allow_llm: bool = True) -> tuple[dict, bool]:
    counts = verdict_counts(bid)
    requirements = _requirements(bid)
    high = [
        (r, _evaluation(r))
        for r in requirements
        if _evaluation(r) and _evaluation(r).risk_level == "HIGH"
    ]
    stats = {
        "met": counts["MET"],
        "needs_supplement": counts["NEEDS_SUPPLEMENT"],
        "needs_confirmation": counts["NEEDS_CONFIRMATION"],
        "high_risk": counts["HIGH"],
        "high_supplement": sum(1 for _, e in high if e.verdict == "NEEDS_SUPPLEMENT"),
    }
    recommendation, reason = rule_recommendation(bid, stats)
    key_risks = [f"{r.title}: {_first_line(e.rationale or e.auto_answer)}" for r, e in high]
    next_actions = []
    for r, e in high:
        for action in e.action_items[:2]:
            next_actions.append({"action": f"[{r.title}] {action}", "owner": "", "due": ""})
    matched = sorted(
        {
            i.matched_product.model_no
            for i in bid.items.select_related("matched_product")
            if i.matched_product
        }
    )
    content = {
        "executive_summary": (
            f"{bid.buyer_org or '발주처'}의 「{bid.title}」 공고 검토 결과, 요구사항 {counts['total']}건 중 "
            f"충족 {stats['met']}건, 보완 필요 {stats['needs_supplement']}건, 확인 필요 {stats['needs_confirmation']}건"
            f"(HIGH 위험 {stats['high_risk']}건)입니다."
        ),
        "recommendation": recommendation,
        "recommendation_reason": reason,
        "bid_overview": bid_info(bid),
        "fit": {"score": bid.fit_score, "reason": bid.fit_reason, "matched_products": matched},
        "stats": {k: v for k, v in stats.items() if k != "high_supplement"},
        "key_risks": key_risks,
        "next_actions": next_actions,
        "requirements_table": "COMPLIANCE_MATRIX 참조",
    }
    data = _llm(
        "draft.report_summary",
        {
            "bid": bid_info(bid),
            "stats": {**content["stats"], "fit_score": bid.fit_score},
            "high_risks": [
                {
                    "title": r.title,
                    "verdict": VERDICT_LABELS[e.verdict],
                    "rationale": e.rationale,
                    "action_items": e.action_items,
                }
                for r, e in high
            ],
        },
        job,
        allow_llm,
    )
    if data:
        content.update(
            {
                "executive_summary": data.get("executive_summary") or content["executive_summary"],
                "recommendation": data.get("recommendation") or recommendation,
                "recommendation_reason": data.get("recommendation_reason") or reason,
                "key_risks": data.get("key_risks") or key_risks,
                "next_actions": data.get("next_actions") or next_actions,
            }
        )
    return content, bool(data)


GENERATORS = {
    DraftType.COMPLIANCE_MATRIX: compliance_matrix,
    DraftType.BID_CHECKLIST: checklist,
    DraftType.TECHNICAL_QUERY: technical_query,
    DraftType.REVIEW_REPORT: review_report,
}
