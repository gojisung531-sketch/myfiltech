"""Draft generators (specs/09). Each builds a deterministic draft from requirements and
evaluations, then (when `evaluation.use_llm` and an API key are set) lets the LLM polish it.
An LLM failure never blocks a draft — the deterministic content is kept."""

import hashlib
import json
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
    from apps.documents.models import Document
    from apps.evaluation.evidence import evidence_document_map

    doc_map = evidence_document_map([evaluation.evidences])
    docs = Document.objects.in_bulk(doc_map.values())
    labels = []
    for e in evaluation.evidences or []:
        if e.get("type") == "bid_quote":
            continue
        page = f" p.{e['page']}" if e.get("page") else ""
        document = docs.get(doc_map.get((e.get("type"), e.get("id"))))
        name = f" · {document.display_name}" if document else ""
        labels.append(f"{e.get('label', '')}{name}{page}")
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


def output_notice(bid) -> str:
    configured = get_setting("report.disclaimer") or ""
    if (bid.extra or {}).get("b5c_run"):
        configured = configured.replace("가상 자료 기반", "실제 등록 자료 기반")
    return (
        f"{configured} · 미확정 후보·조건 포함 · 직원 검토용이며 최종 입찰 결정/제출본이 아닙니다."
    )


def candidate_details(evaluation) -> list[dict]:
    from apps.company.models import Product

    trace = evaluation.rule_trace if evaluation else {}
    rows = (trace or {}).get("candidate_comparisons") or []
    products = Product.objects.in_bulk([r["product_id"] for r in rows])
    labels = {
        "MET": "후보 기재값 일치",
        "NEEDS_SUPPLEMENT": "후보 기재값 차이",
        "NEEDS_CONFIRMATION": "후보 조건 미확인",
    }
    return [
        {
            **r,
            "model_no": products[r["product_id"]].model_no
            if r["product_id"] in products
            else "모델 미확인",
            "comparison_label": labels.get(r.get("candidate_verdict"), "후보 조건 미확인"),
            "scope_notice": "제안 제품 미확정; 최종 공고 판정과 별개",
        }
        for r in rows
    ]


def analysis_snapshot(bid) -> dict:
    rows = []
    for requirement in _requirements(bid):
        evaluation = _evaluation(requirement)
        if evaluation:
            rows.append(
                {
                    "requirement_id": requirement.pk,
                    "normalized": requirement.normalized,
                    "evaluation": evaluation.snapshot(),
                    "trace": evaluation.rule_trace,
                }
            )
    run = (bid.extra or {}).get("b5c_run") or {}
    return {
        "saved_evaluation_date": run.get("reference_date", "미기록"),
        "is_simulation": run.get("is_simulation"),
        "counts": verdict_counts(bid),
        "input_sha256": hashlib.sha256(
            json.dumps(rows, ensure_ascii=False, sort_keys=True, default=str).encode()
        ).hexdigest(),
        "generation_mode": "STORED_RESULTS_NO_REEVALUATION",
        "candidate_links_confirmed": run.get("confirmed_item_product_links"),
        "source_revision_tracking": "미구현",
    }


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
                "remark": (requirement.normalized or {})
                .get("interpretation_review", {})
                .get("reason", ""),
                "candidate_comparisons": candidate_details(evaluation),
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
        if "제작" in timing:
            return ["제작 전 승인"]
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
    sections["제작 전 승인"] = []
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
                    note="; ".join(
                        filter(
                            None,
                            [
                                "조건부 적용: " + str(requirement.normalized["applicability"])
                                if requirement.normalized.get("applicability")
                                else "",
                                evaluation.action_items[0]
                                if evaluation and evaluation.action_items
                                else "",
                            ],
                        )
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
    return {
        "sections": [
            {"title": t, "items": items}
            for t, items in sections.items()
            if items or t != "제작 전 승인"
        ]
    }


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
    questions, internal = [], []
    selected_items = set()
    for requirement, evaluation in query_candidates(bid):
        question = buyer_question(requirement)
        if (
            requirement.item_id
            and requirement.category in ("DIMENSION", "FILTER_TYPE")
            and candidate_details(evaluation)
        ):
            if requirement.item_id in selected_items:
                continue
            selected_items.add(requirement.item_id)
            question = "제공 카탈로그에서 후보의 형식·치수는 비교했습니다. 실제 제안할 모델과 재질·개스킷 옵션을 내부에서 선택·확인해 주세요."
            target = internal
        elif question:
            target = questions
        else:
            target = internal
            action = (
                "; ".join(evaluation.action_items)
                or "해당 요구의 회사 적용·이행 범위와 직접 자료 확인"
            )
            question = f"[{requirement.title}] 기존 제공 자료를 먼저 대조해 주세요. {action}"
        target.append(
            {
                "no": len(target) + 1,
                "reference": _clause(requirement) or requirement.get_category_display(),
                "question": question,
                "background": ""
                if (evaluation.rule_trace or {}).get("unjudged")
                else evaluation.rationale,
                "proposed_alternative": "; ".join(evaluation.action_items)
                if evaluation.verdict == "NEEDS_SUPPLEMENT"
                else "",
                "requirement_id": requirement.pk,
                "audience": "BUYER" if target is questions else "INTERNAL",
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
            "from": company.name or "작성 담당자 미확인",
            "date": timezone.localdate().isoformat(),
            "subject": subject,
        },
        "intro": f"「{bid.title}」의 내부 확인과 발주처 확인 초안을 구분했습니다. 내부 자료 확인 후 필요한 발주처 항목만 직원이 검토·선택하며, 자동 발송하지 않습니다.",
        "questions": questions,
        "internal_questions": internal,
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
            "internal_questions": internal,
        }, True
    return content, False


def buyer_question(requirement) -> str:
    """Only unresolved source interpretation belongs in the buyer-facing draft.

    Missing company evidence and an unselected model are internal checks. Explicit
    dimensions, OR alternatives, test endpoints and published dates are not re-asked.
    """
    norm = requirement.normalized or {}
    if not norm.get("interpretation_review"):
        return ""
    if (
        requirement.category == "ENVIRONMENT"
        and "min_temp_c" in norm
        and norm["min_temp_c"] is None
    ):
        return "원문 사용온도 하한의 선행 부호와 적용 범위를 확인해 주십시오."
    if (
        requirement.category == "PRESSURE_DROP"
        and norm.get("metric") == "initial_dp"
        and norm.get("at_airflow_m3h") is None
    ):
        return (
            "초기 차압의 병기 풍량 단위 및 시험대상(개별 필터/페어)의 적용 기준을 확인해 주십시오."
        )
    if norm.get("comparison_scope") == "PAIR_NET_EFFECTIVE" and norm.get("unit") is None:
        return "페어 순유효여과면적의 단위와 적용 정의를 확인해 주십시오."
    if requirement.category == "MATERIAL" and norm.get("part") == "gasket" and norm.get("note"):
        return "개스킷 재질 지정과 제작자 기준 비고 중 우선 적용할 조건을 확인해 주십시오."
    return ""


# ---- 4. Review report ----------------------------------------------------------------


def _first_line(text: str) -> str:
    return next((line.strip() for line in (text or "").splitlines() if line.strip()), "-")


def rule_recommendation(bid, stats: dict) -> tuple[str, str]:
    high_supplement = stats["high_supplement"]
    if bid.fit_score is not None and bid.fit_score < 40:
        return (
            "CONDITIONAL",
            f"참고 적합도 {bid.fit_score}점의 산정 근거와 미확정 조건을 직원이 검토해야 합니다. 점수만으로 입찰 불가를 확정하지 않습니다.",
        )
    if (
        high_supplement
        or stats["high_risk"]
        or stats.get("needs_confirmation")
        or not any(stats.get(k) for k in ("met", "needs_supplement", "needs_confirmation"))
    ):
        return (
            "CONDITIONAL",
            "미확정 제안 제품·자료·적용 조건을 추가 확인한 뒤 직원이 판단해야 합니다. 확인 필요는 회사 미보유·실제 미달·입찰 불가의 확정이 아닙니다.",
        )
    return (
        "BID",
        "현재 등록 근거에서 확인된 범위의 검토 의견입니다. 최종 입찰 결정은 직원이 수행합니다.",
    )


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
        "decision_notice": "직원 판단 지원용 검토 초안이며 최종 입찰 결정이 아닙니다.",
        "candidate_review": [
            {
                "requirement_id": r.pk,
                "title": r.title,
                "final_verdict": VERDICT_LABELS.get(_evaluation(r).verdict, ""),
                **detail,
            }
            for r in requirements
            if _evaluation(r)
            for detail in candidate_details(_evaluation(r))
        ],
        "unresolved_conditions": [
            f"{r.title}: {r.normalized['interpretation_review']['reason']}"
            for r in requirements
            if (r.normalized or {}).get("interpretation_review")
        ],
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
