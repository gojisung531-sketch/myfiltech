"""Background job registry, enqueueing and execution (specs/01 §5).

Handlers are registered with @job_handler("TYPE") (each app imports its `tasks` module in
AppConfig.ready) and receive (job, report), where report(progress, message) updates progress.
"""

import logging
import traceback
from collections.abc import Callable

from django.db import transaction
from django.utils import timezone

from .app_settings import get_setting
from .models import Job

logger = logging.getLogger(__name__)

_HANDLERS: dict[str, Callable] = {}


class JobError(Exception):
    """Raise from a handler to fail the job with a user-facing (Korean) message."""


def job_handler(job_type: str):
    def decorator(func):
        _HANDLERS[job_type] = func
        return func

    return decorator


def has_handler(job_type: str) -> bool:
    return job_type in _HANDLERS


def enqueue(
    job_type: str,
    *,
    target=None,
    payload: dict | None = None,
    user=None,
    run_inline: bool | None = None,
) -> Job:
    job = Job.objects.create(
        type=job_type,
        target_type=target._meta.label if target is not None else "",
        target_id=target.pk if target is not None else None,
        payload=payload or {},
        created_by=user if user is not None and user.is_authenticated else None,
    )
    inline = get_setting("jobs.run_inline") if run_inline is None else run_inline
    if inline:
        execute(job)
        job.refresh_from_db()
    return job


def claim_next() -> Job | None:
    """Atomically take the oldest PENDING job (SELECT ... FOR UPDATE SKIP LOCKED)."""
    with transaction.atomic():
        job = (
            Job.objects.select_for_update(skip_locked=True)
            .filter(status=Job.Status.PENDING)
            .order_by("created_at", "id")
            .first()
        )
        if job is None:
            return None
        job.status = Job.Status.RUNNING
        job.started_at = timezone.now()
        job.attempts += 1
        job.save(update_fields=["status", "started_at", "attempts", "updated_at"])
        return job


def execute(job: Job) -> None:
    if job.status == Job.Status.PENDING:
        job.status = Job.Status.RUNNING
        job.started_at = timezone.now()
        job.attempts += 1
        job.save(update_fields=["status", "started_at", "attempts", "updated_at"])

    handler = _HANDLERS.get(job.type)

    def report(progress: int, message: str = "") -> None:
        Job.objects.filter(pk=job.pk).update(
            progress=max(0, min(100, int(progress))), message=message[:255]
        )

    try:
        if handler is None:
            raise JobError(f"알 수 없는 작업 유형입니다: {job.type}")
        result = handler(job, report)
        Job.objects.filter(pk=job.pk).update(
            status=Job.Status.SUCCEEDED,
            progress=100,
            result=result,
            finished_at=timezone.now(),
        )
    except JobError as exc:
        _fail(job, str(exc))
    except Exception:  # noqa: BLE001 — a failing job must not kill the worker
        logger.exception("Job %s failed", job)
        _fail(job, "작업 중 오류가 발생했습니다. 관리자에게 문의하세요.", traceback.format_exc())


def _fail(job: Job, message: str, detail: str = "") -> None:
    if detail:
        logger.error("Job %s detail:\n%s", job, detail)
    Job.objects.filter(pk=job.pk).update(
        status=Job.Status.FAILED, error=message, finished_at=timezone.now()
    )


def run_once() -> bool:
    """Run one pending job. Returns False when the queue is empty."""
    job = claim_next()
    if job is None:
        return False
    execute(job)
    return True


def retry(job: Job) -> Job:
    job.status = Job.Status.PENDING
    job.progress = 0
    job.message = ""
    job.error = ""
    job.result = None
    job.started_at = None
    job.finished_at = None
    job.save()
    return job


def cancel(job: Job) -> bool:
    """Only PENDING jobs can be cancelled; running work is not interrupted."""
    updated = Job.objects.filter(pk=job.pk, status=Job.Status.PENDING).update(
        status=Job.Status.CANCELLED, finished_at=timezone.now()
    )
    return bool(updated)
