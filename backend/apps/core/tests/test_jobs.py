import threading

import pytest
from django.core.management import call_command
from django.db import connection

from apps.core import jobs
from apps.core.models import Job

pytestmark = pytest.mark.django_db


@pytest.fixture
def handlers():
    calls = []

    @jobs.job_handler("TEST_OK")
    def ok(job, report):
        report(50, "half")
        calls.append(job.pk)
        return {"echo": job.payload.get("x")}

    @jobs.job_handler("TEST_USER_ERROR")
    def user_error(job, report):
        raise jobs.JobError("사용자용 메시지")

    @jobs.job_handler("TEST_CRASH")
    def crash(job, report):
        raise RuntimeError("secret internal detail")

    return calls


def test_enqueue_runs_inline_when_requested(handlers):
    job = jobs.enqueue("TEST_OK", payload={"x": 1}, run_inline=True)
    assert job.status == Job.Status.SUCCEEDED
    assert job.result == {"echo": 1}
    assert job.progress == 100
    assert job.attempts == 1


def test_enqueue_defers_by_default(handlers):
    job = jobs.enqueue("TEST_OK")
    assert job.status == Job.Status.PENDING
    assert handlers == []


def test_worker_processes_queue_in_order(handlers):
    first = jobs.enqueue("TEST_OK")
    second = jobs.enqueue("TEST_OK")
    call_command("run_jobs", "--once")
    assert handlers == [first.pk, second.pk]
    assert set(Job.objects.values_list("status", flat=True)) == {Job.Status.SUCCEEDED}


def test_failures_keep_internal_details_out_of_error(handlers):
    user = jobs.enqueue("TEST_USER_ERROR", run_inline=True)
    assert user.status == Job.Status.FAILED and user.error == "사용자용 메시지"
    crash = jobs.enqueue("TEST_CRASH", run_inline=True)
    assert crash.status == Job.Status.FAILED
    assert "secret" not in crash.error
    unknown = jobs.enqueue("NO_SUCH_TYPE", run_inline=True)
    assert "알 수 없는 작업 유형" in unknown.error


def test_retry_and_cancel(handlers):
    failed = jobs.enqueue("TEST_USER_ERROR", run_inline=True)
    jobs.retry(failed)
    failed.refresh_from_db()
    assert failed.status == Job.Status.PENDING and failed.error == ""

    pending = jobs.enqueue("TEST_OK")
    assert jobs.cancel(pending) is True
    pending.refresh_from_db()
    assert pending.status == Job.Status.CANCELLED
    assert jobs.cancel(pending) is False


@pytest.mark.django_db(transaction=True)
def test_claim_next_skips_locked_rows(handlers):
    first = jobs.enqueue("TEST_OK")
    second = jobs.enqueue("TEST_OK")
    claimed = []
    barrier = threading.Barrier(2)

    def worker():
        try:
            barrier.wait()
            job = jobs.claim_next()
            claimed.append(job.pk if job else None)
        finally:
            connection.close()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(claimed) == sorted([first.pk, second.pk])


def test_job_api_permissions(api_client, admin_client, manager_client, manager_user, handlers):
    own = jobs.enqueue("TEST_OK", user=manager_user)
    other = jobs.enqueue("TEST_OK")
    assert manager_client.get(f"/api/jobs/{own.pk}").status_code == 200
    assert manager_client.get(f"/api/jobs/{other.pk}").status_code == 404
    assert manager_client.get("/api/jobs").status_code == 403
    assert admin_client.get(f"/api/jobs/{other.pk}").status_code == 200
    res = admin_client.get("/api/jobs?status=PENDING")
    assert res.data["count"] == 2
    assert admin_client.post(f"/api/jobs/{other.pk}/cancel").data["status"] == "CANCELLED"
    assert admin_client.post(f"/api/jobs/{other.pk}/retry").data["status"] == "PENDING"
    assert admin_client.post(f"/api/jobs/{own.pk}/retry").status_code == 400
