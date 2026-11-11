"""Background job registry, enqueueing and execution (specs/01 §5).

Handlers are registered with @job_handler("TYPE") (each app imports its `tasks` module in
AppConfig.ready) and receive (job, report), where report(progress, message) updates progress.
"""

import logging
import traceback
from collections.abc import Callable

from django.db import connection, transaction
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
    with transaction.atomic():
        if target is not None and target._meta.label == "bids.BidNotice":
            type(target).objects.select_for_update().get(pk=target.pk)
            existing = (
                Job.objects.filter(
                    type=job_type,
                    target_type=target._meta.label,
                    target_id=target.pk,
                    status__in=[Job.Status.PENDING, Job.Status.RUNNING],
                    payload=payload or {},
                )
                .order_by("id")
                .first()
            )
            if existing:
                return existing
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


def claim_next(queryset=None) -> Job | None:
    """Atomically take the oldest PENDING job (SELECT ... FOR UPDATE SKIP LOCKED)."""
    with transaction.atomic():
        job = (
            (queryset if queryset is not None else Job.objects.all())
            .select_for_update(skip_locked=True)
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
        job._claimed_here = True
        return job


def execute(job: Job) -> bool:
    """Claim pending work atomically; never execute a stale/finished/running object twice."""
    advisory = connection.vendor == "postgresql"
    if advisory:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s, %s)", [74126, job.pk])
            if not cursor.fetchone()[0]:
                return False
    try:
        with transaction.atomic():
            current = Job.objects.select_for_update().get(pk=job.pk)
            claimed = getattr(job, "_claimed_here", False)
            if current.status != (Job.Status.RUNNING if claimed else Job.Status.PENDING):
                return False
            if not claimed:
                current.status = Job.Status.RUNNING
                current.started_at = timezone.now()
                current.attempts += 1
                current.save(update_fields=["status", "started_at", "attempts", "updated_at"])
            job.__dict__.update(current.__dict__)
            job._claimed_here = False
        _execute_claimed(job)
        return True
    finally:
        if advisory:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s, %s)", [74126, job.pk])


def _execute_claimed(job):

    handler = _HANDLERS.get(job.type)

    def report(progress: int, message: str = "") -> None:
        Job.objects.filter(pk=job.pk).update(
            progress=max(0, min(100, int(progress))),
            message=message[:255],
            updated_at=timezone.now(),
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
            message="작업 완료",
            updated_at=timezone.now(),
        )
    except JobError as exc:
        _fail(job, str(exc))
    except Exception as exc:  # noqa: BLE001 — a failing job must not kill the worker
        from apps.llm.providers.base import LLMError

        from .logging import mask_secrets

        logger.exception("Job %s failed", job)
        message = (
            mask_secrets(str(exc))[:1000]
            if isinstance(exc, LLMError)
            else "작업 중 오류가 발생했습니다. 관리자에게 문의하세요."
        )
        _fail(job, message, traceback.format_exc())


def _fail(job: Job, message: str, detail: str = "") -> None:
    if detail:
        logger.error("Job %s detail:\n%s", job, detail)
    Job.objects.filter(pk=job.pk).update(
        status=Job.Status.FAILED,
        error=message,
        message=message[:255],
        finished_at=timezone.now(),
        updated_at=timezone.now(),
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
