"""Background job handlers for bids (registered in BidsConfig.ready)."""

from apps.core.app_settings import get_setting
from apps.core.jobs import JobError, enqueue, has_handler, job_handler
from apps.llm.services import LLMNotConfigured

from .extraction import BidExtractionError, extract_bid
from .models import BidNotice


@job_handler("EXTRACT_BID")
def extract_bid_job(job, report):
    bid = BidNotice.objects.filter(pk=job.target_id).first()
    if bid is None:
        raise JobError("입찰 공고를 찾을 수 없습니다.")
    try:
        result = extract_bid(bid, job=job, report=report)
    except LLMNotConfigured as exc:
        raise JobError("LLM API Key가 설정되지 않아 공고를 추출할 수 없습니다.") from exc
    except BidExtractionError as exc:
        raise JobError(str(exc)) from exc
    # Evaluation is added in Phase 6; chain it only once its handler exists (specs/04 §3.2).
    if get_setting("bid.auto_evaluate_after_extract") and has_handler("EVALUATE_BID"):
        result["evaluate_job_id"] = enqueue(
            "EVALUATE_BID", target=bid, payload={"keep_modified": True}, user=job.created_by
        ).pk
    return result
