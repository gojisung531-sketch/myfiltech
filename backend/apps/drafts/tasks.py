"""Background job handlers for drafts (registered in DraftsConfig.ready)."""

from apps.core.jobs import JobError, job_handler

from .models import DraftType
from .service import generate_draft


@job_handler("GENERATE_DRAFT")
def generate_draft_job(job, report):
    from apps.bids.models import BidNotice

    bid = BidNotice.objects.filter(pk=job.target_id).first()
    if bid is None:
        raise JobError("입찰 공고를 찾을 수 없습니다.")
    payload = job.payload or {}
    doc_type = payload.get("doc_type")
    if doc_type not in DraftType.values:
        raise JobError("알 수 없는 초안 유형입니다.")
    report(10, f"{DraftType(doc_type).label} 생성 중")
    draft = generate_draft(
        bid, doc_type, new_version=bool(payload.get("new_version")), user=job.created_by, job=job
    )
    report(100, "완료")
    return {
        "draft_id": draft.pk,
        "doc_type": doc_type,
        "version": draft.version,
        "used_llm": draft.used_llm,
    }
