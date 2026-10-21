"""Background job handlers for evaluation (registered in EvaluationConfig.ready)."""

from apps.core.jobs import JobError, job_handler

from .service import evaluate_bid


@job_handler("EVALUATE_BID")
def evaluate_bid_job(job, report):
    from apps.bids.models import BidNotice

    bid = BidNotice.objects.filter(pk=job.target_id).first()
    if bid is None:
        raise JobError("입찰 공고를 찾을 수 없습니다.")
    payload = job.payload or {}
    return evaluate_bid(
        bid,
        keep_modified=payload.get("keep_modified", True),
        requirement_ids=payload.get("requirement_ids") or None,
        job=job,
        report=report,
    )
