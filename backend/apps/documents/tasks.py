"""Background job handlers for documents (registered in DocumentsConfig.ready)."""

from apps.core.jobs import JobError, job_handler

from .loader import COMPANY_SEED_BLOCKED_MESSAGE, load_company
from .models import Document
from .pipeline import run_pipeline


@job_handler("EXTRACT_DOCUMENT")
def extract_document(job, report):
    document = Document.objects.filter(pk=job.target_id).first()
    if document is None:
        raise JobError("문서를 찾을 수 없습니다.")
    payload = job.payload or {}
    return run_pipeline(
        document,
        from_step=payload.get("from_step", "parse"),
        apply=payload.get("apply"),
        report=report,
        job=job,
    )


@job_handler("LOAD_INITIAL_DATA")
def load_initial_data(job, report):
    from apps.bids.loader import load_bids

    payload = job.payload or {}
    only, mode = payload.get("only"), payload.get("mode", "skip")
    result = {}
    try:
        if only in (None, "company"):
            # Personal build: virtual company seed is blocked; load_company() stays for tests.
            result["company"] = {"blocked": True, "message": COMPANY_SEED_BLOCKED_MESSAGE}
        if only in (None, "bids"):
            result["bids"] = load_bids(
                mode=mode,
                use_llm=payload.get("use_llm", True),
                report=lambda p, m="": report(50 + p // 2, m),
            )
    except FileNotFoundError as exc:
        raise JobError(str(exc)) from exc
    return result
