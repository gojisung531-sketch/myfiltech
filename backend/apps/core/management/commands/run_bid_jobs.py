"""Explicit root+child recovery or a high-water-mark bid-only worker. No old queue drain."""

import signal
import threading

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.core.jobs import claim_next, execute, retry
from apps.core.models import Job
from apps.llm.worker_budget import WorkerBudget


class Command(BaseCommand):
    help = "Run only an explicit bid job, or newly queued bid jobs above a specified ID."

    def add_arguments(self, parser):
        scope = parser.add_mutually_exclusive_group(required=True)
        scope.add_argument("--job-id", type=int)
        scope.add_argument("--after-id", type=int)
        parser.add_argument("--bid-id", type=int)
        parser.add_argument("--follow", action="store_true")
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--retry-failed", action="store_true")
        parser.add_argument("--budget-ledger", required=True)
        parser.add_argument("--budget-usd", required=True)
        parser.add_argument("--prior-spend-usd", required=True)

    def handle(self, *args, **options):
        if options["retry_failed"] and options["job_id"] is None:
            raise CommandError("--retry-failed requires an explicit --job-id and --bid-id")
        if options["job_id"] is not None and (not options["bid_id"] or options["job_id"] <= 0):
            raise CommandError("--job-id requires --bid-id and positive IDs")
        if options["after_id"] is not None and options["after_id"] < 0:
            raise CommandError("--after-id must be nonnegative")
        qs = Job.objects.filter(
            target_type="bids.BidNotice", type__in=["EXTRACT_BID", "EVALUATE_BID"]
        )
        if options["bid_id"] is not None:
            qs = qs.filter(target_id=options["bid_id"])
        try:
            budget = WorkerBudget(
                options["budget_ledger"], options["budget_usd"], options["prior_spend_usd"]
            )
            with budget.activate():
                if options["job_id"] is not None:
                    job = qs.filter(pk=options["job_id"]).first()
                    if not job:
                        raise CommandError("지정한 공고/작업 범위가 일치하지 않습니다.")
                    if options["retry_failed"]:
                        with transaction.atomic():
                            job = qs.select_for_update().get(pk=job.pk)
                            if job.status != Job.Status.FAILED or job.attempts != 1:
                                raise CommandError(
                                    "실패한 첫 시도만 명시적으로 한 번 재시도할 수 있습니다."
                                )
                            from apps.bids.models import BidNotice

                            bid = BidNotice.objects.get(pk=job.target_id)
                            job.payload = {
                                **job.payload,
                                "previous_attempts": [
                                    {
                                        "attempt": job.attempts,
                                        "error": job.error,
                                        "message": job.message,
                                        "bid_error": bid.processing_error,
                                        "finished_at": job.finished_at.isoformat()
                                        if job.finished_at
                                        else None,
                                    }
                                ],
                            }
                            retry(job)
                    self.run_job(job, budget)
                    if options["follow"]:
                        child_id = (job.result or {}).get("evaluate_job_id")
                        if child_id:
                            child = qs.filter(
                                pk=child_id,
                                type="EVALUATE_BID",
                                target_id=job.target_id,
                                payload__parent_job_id=job.pk,
                            ).first()
                            if not child:
                                raise CommandError(
                                    "같은 실행의 판정 후속 작업을 확인할 수 없습니다."
                                )
                            self.run_job(child, budget)
                    return
                qs = qs.filter(id__gt=options["after_id"])
                stop = threading.Event()
                if threading.current_thread() is threading.main_thread():
                    signal.signal(signal.SIGINT, lambda *_: stop.set())
                    signal.signal(signal.SIGTERM, lambda *_: stop.set())
                self.stdout.write(
                    f"Scoped bid worker: id > {options['after_id']}; old jobs excluded."
                )
                while not stop.is_set():
                    job = claim_next(qs)
                    if job:
                        self.run_job(job, budget, fail_command=False)
                    elif options["once"]:
                        return
                    else:
                        stop.wait(2)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

    def run_job(self, job, budget, fail_command=True):
        budget.job_id = job.pk
        if not execute(job):
            self.stdout.write(f"Job {job.pk}: already claimed/finished; no execution.")
            return
        job.refresh_from_db()
        self.stdout.write(f"Job {job.pk}: {job.status}; budget accounted ${budget.used()}")
        self.stdout.flush()
        if job.status == Job.Status.FAILED and fail_command:
            raise CommandError(f"Job {job.pk} failed: {job.error}")
