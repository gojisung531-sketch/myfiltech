import json
import threading
from decimal import Decimal
from io import StringIO
from types import SimpleNamespace

import httpx2
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection

from apps.bids.models import BidNotice
from apps.core import jobs
from apps.core.models import Job
from apps.llm.providers.base import LLMError
from apps.llm.worker_budget import WorkerBudget

pytestmark = pytest.mark.django_db


def options(tmp_path):
    return [
        "--budget-ledger",
        str(tmp_path / "budget.json"),
        "--budget-usd",
        "10",
        "--prior-spend-usd",
        "0.16715",
    ]


def test_pending_bid_enqueue_is_deduplicated():
    bid = BidNotice.objects.create(title="합성 공고")
    first = jobs.enqueue("EXTRACT_BID", target=bid, run_inline=False)
    again = jobs.enqueue("EXTRACT_BID", target=bid, run_inline=False)
    assert first.pk == again.pk and Job.objects.count() == 1


def test_stale_object_cannot_repeat_finished_job():
    calls = []
    jobs._HANDLERS["SCOPE_TEST"] = lambda job, report: calls.append(job.pk) or {}
    job = jobs.enqueue("SCOPE_TEST", run_inline=False)
    stale = Job.objects.get(pk=job.pk)
    assert jobs.execute(job) and not jobs.execute(stale)
    assert calls == [job.pk]
    job.refresh_from_db()
    assert job.attempts == 1


def test_explicit_root_only_follows_its_verified_child(tmp_path, monkeypatch):
    oldbid = BidNotice.objects.create(title="보존 공고")
    target = BidNotice.objects.create(title="합성 대상")
    old = jobs.enqueue("EXTRACT_BID", target=oldbid, run_inline=False)
    root = jobs.enqueue("EXTRACT_BID", target=target, run_inline=False)
    calls = []

    def extract(job, report):
        calls.append(job.pk)
        report(45, "합성 단계")
        child = jobs.enqueue(
            "EVALUATE_BID", target=target, payload={"parent_job_id": job.pk}, run_inline=False
        )
        return {"evaluate_job_id": child.pk}

    monkeypatch.setitem(jobs._HANDLERS, "EXTRACT_BID", extract)
    monkeypatch.setitem(
        jobs._HANDLERS, "EVALUATE_BID", lambda job, report: calls.append(job.pk) or {}
    )
    call_command(
        "run_bid_jobs",
        "--job-id",
        str(root.pk),
        "--bid-id",
        str(target.pk),
        "--follow",
        *options(tmp_path),
        stdout=StringIO(),
    )
    old.refresh_from_db()
    assert old.status == "PENDING" and old.attempts == 0
    assert calls == [root.pk, Job.objects.latest("id").pk]
    call_command(
        "run_bid_jobs",
        "--job-id",
        str(root.pk),
        "--bid-id",
        str(target.pk),
        "--follow",
        *options(tmp_path),
        stdout=StringIO(),
    )
    assert len(calls) == 2


def test_high_watermark_excludes_old_jobs(tmp_path, monkeypatch):
    bid = BidNotice.objects.create(title="합성")
    old = jobs.enqueue("EXTRACT_BID", target=bid, run_inline=False)
    newbid = BidNotice.objects.create(title="신규 합성")
    new = jobs.enqueue("EXTRACT_BID", target=newbid, run_inline=False)
    monkeypatch.setitem(jobs._HANDLERS, "EXTRACT_BID", lambda job, report: {})
    call_command(
        "run_bid_jobs", "--after-id", str(old.pk), "--once", *options(tmp_path), stdout=StringIO()
    )
    old.refresh_from_db()
    new.refresh_from_db()
    assert old.status == "PENDING" and new.status == "SUCCEEDED"


def test_wrong_target_and_unrelated_child_rejected(tmp_path, monkeypatch):
    bid = BidNotice.objects.create(title="합성")
    other = BidNotice.objects.create(title="다른 합성")
    job = jobs.enqueue("EXTRACT_BID", target=bid, run_inline=False)
    with pytest.raises(CommandError):
        call_command(
            "run_bid_jobs", "--job-id", str(job.pk), "--bid-id", str(other.pk), *options(tmp_path)
        )
    unrelated = jobs.enqueue("EVALUATE_BID", target=other, run_inline=False)
    monkeypatch.setitem(
        jobs._HANDLERS, "EXTRACT_BID", lambda job, report: {"evaluate_job_id": unrelated.pk}
    )
    with pytest.raises(CommandError):
        call_command(
            "run_bid_jobs",
            "--job-id",
            str(job.pk),
            "--bid-id",
            str(bid.pk),
            "--follow",
            *options(tmp_path),
        )
    unrelated.refresh_from_db()
    assert unrelated.status == "PENDING"


def test_llm_failure_visible_no_job_retry(tmp_path, monkeypatch):
    bid = BidNotice.objects.create(title="합성")
    job = jobs.enqueue("EXTRACT_BID", target=bid, run_inline=False)

    def failure(job, report):
        report(45, "처리 중")
        raise LLMError("예산 한도에 도달했습니다.")

    monkeypatch.setitem(jobs._HANDLERS, "EXTRACT_BID", failure)
    with pytest.raises(CommandError):
        call_command(
            "run_bid_jobs", "--job-id", str(job.pk), "--bid-id", str(bid.pk), *options(tmp_path)
        )
    job.refresh_from_db()
    assert (
        job.status == "FAILED" and job.attempts == 1 and "예산" in job.error and job.progress == 45
    )
    assert not jobs.execute(job)


def test_explicit_retry_keeps_failure_and_cannot_retry_twice(tmp_path, monkeypatch):
    bid = BidNotice.objects.create(title="합성")
    job = jobs.enqueue("EVALUATE_BID", target=bid, run_inline=False)
    Job.objects.filter(pk=job.pk).update(status="FAILED", attempts=1, error="중단 오류")
    monkeypatch.setitem(jobs._HANDLERS, "EVALUATE_BID", lambda job, report: {})
    args = ["--job-id", str(job.pk), "--bid-id", str(bid.pk), "--retry-failed", *options(tmp_path)]
    call_command("run_bid_jobs", *args, stdout=StringIO())
    job.refresh_from_db()
    assert job.attempts == 2 and job.status == "SUCCEEDED"
    assert job.payload["previous_attempts"][0]["error"] == "중단 오류"
    with pytest.raises(CommandError):
        call_command("run_bid_jobs", *args, stdout=StringIO())


def wire_request():
    return httpx2.Request(
        "POST",
        "https://api.anthropic.com/v1/messages",
        json={
            "model": "claude-sonnet-5-5",
            "max_tokens": 32000,
            "messages": [{"role": "user", "content": [{"type": "text", "text": "합성"}]}],
        },
    )


def test_budget_reserves_every_retry_before_transport_and_persists(tmp_path):
    path = tmp_path / "budget.json"
    b = WorkerBudget(path, 1, 0)
    with b.activate():
        b.request(wire_request())
        persisted = json.loads(path.read_text(encoding="utf8"))
        assert len(persisted["attempts"]) == 1 and "actual_usd" not in persisted["attempts"][0]
        with pytest.raises(LLMError):
            b.request(wire_request())
    again = WorkerBudget(path, 1, 0)
    with again.activate():
        with pytest.raises(LLMError):
            again.request(wire_request())


def test_receipt_settles_success_invalid_json_and_truncated_usage(tmp_path):
    b = WorkerBudget(tmp_path / "budget.json", 1, 0)
    with b.activate():
        b.request(wire_request())
        message = SimpleNamespace(
            id="test",
            model="claude-sonnet-5-5",
            stop_reason="max_tokens",
            usage=SimpleNamespace(model_dump=lambda: {"input_tokens": 100, "output_tokens": 200}),
        )
        b.receipt(message)
        assert b.used() == Decimal("0.0022")
        b.request(wire_request())
        assert len(b.data["attempts"]) == 2


def test_budget_rejects_other_features_and_configuration_reset(tmp_path):
    path = tmp_path / "budget.json"
    b = WorkerBudget(path, 10, 0)
    with b.activate():
        req = httpx2.Request(
            "POST",
            "https://api.anthropic.com/v1/messages",
            json={"model": "other", "max_tokens": 1, "messages": []},
        )
        with pytest.raises(LLMError):
            b.request(req)
        assert not b.data["attempts"]
    with pytest.raises(ValueError):
        with WorkerBudget(path, 20, 0).activate():
            pass


def test_single_primary_iteration_is_accounted_once_on_reopen(tmp_path):
    path = tmp_path / "budget.json"
    b = WorkerBudget(path, 10, 0)
    with b.activate():
        b.request(wire_request())
        b.data["attempts"][0]["receipt"] = {
            "id": "test",
            "model": "claude-sonnet-5-5",
            "stop_reason": "end_turn",
            "usage": {
                "input_tokens": 100,
                "output_tokens": 200,
                "iterations": [
                    {"type": "message", "model": None, "input_tokens": 100, "output_tokens": 200}
                ],
            },
        }
        b._save()
    with WorkerBudget(path, 10, 0).activate() as reopened:
        assert reopened.used() == Decimal("0.0022")


def test_unknown_fallback_or_partial_receipt_never_refunds_reservation(tmp_path):
    b = WorkerBudget(tmp_path / "budget.json", 10, 0)
    with b.activate():
        b.request(wire_request())
        original = b.used()
        b.data["attempts"][0]["receipt"] = {
            "id": "test",
            "model": "claude-sonnet-5-5",
            "fallback": True,
            "usage": {"input_tokens": 100, "output_tokens": 200},
        }
        b._settle_known(b.data["attempts"][0])
        assert b.used() == original


def test_anthropic_stream_http_hooks_capture_usage_before_json_handling(tmp_path, monkeypatch):
    import anthropic

    from apps.llm.providers.anthropic import AnthropicProvider
    from apps.llm.providers.base import LLMRequest

    events = [
        (
            "message_start",
            {
                "type": "message_start",
                "message": {
                    "id": "msg_test",
                    "type": "message",
                    "role": "assistant",
                    "content": [],
                    "model": "claude-sonnet-5-5",
                    "stop_reason": None,
                    "stop_sequence": None,
                    "usage": {"input_tokens": 100, "output_tokens": 0},
                },
            },
        ),
        (
            "content_block_start",
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "text", "text": ""},
            },
        ),
        (
            "content_block_delta",
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": '{"ok": true}'},
            },
        ),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        (
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                "usage": {"output_tokens": 10},
            },
        ),
        ("message_stop", {"type": "message_stop"}),
    ]
    sse = "".join(
        "event: " + event + "\ndata: " + json.dumps(data) + "\n\n" for event, data in events
    )

    def respond(request):
        assert len(json.loads((tmp_path / "budget.json").read_text())["attempts"]) == 1
        return httpx2.Response(
            200, headers={"content-type": "text/event-stream"}, content=sse.encode()
        )

    monkeypatch.setattr(
        anthropic,
        "DefaultHttpxClient",
        lambda **kwargs: httpx2.Client(transport=httpx2.MockTransport(respond), **kwargs),
    )
    budget = WorkerBudget(tmp_path / "budget.json", 10, 0)
    with budget.activate():
        result = AnthropicProvider(api_key="synthetic-key").generate(
            LLMRequest(
                system="synthetic",
                user="synthetic",
                model="claude-sonnet-5-5",
                max_output_tokens=100,
                max_retries=0,
            )
        )
    assert result.input_tokens == 100 and result.output_tokens == 10
    assert budget.data["attempts"][0]["actual_usd"] == "0.0003"


def test_broken_stream_is_visible_and_keeps_unknown_cost(tmp_path, monkeypatch):
    import anthropic

    from apps.llm.providers.anthropic import AnthropicProvider
    from apps.llm.providers.base import LLMRequest

    class Broken(httpx2.SyncByteStream):
        def __iter__(self):
            raise httpx2.RemoteProtocolError("synthetic broken stream")
            yield b""

    def respond(request):
        return httpx2.Response(200, headers={"content-type": "text/event-stream"}, stream=Broken())

    monkeypatch.setattr(
        anthropic,
        "DefaultHttpxClient",
        lambda **kwargs: httpx2.Client(transport=httpx2.MockTransport(respond), **kwargs),
    )
    budget = WorkerBudget(tmp_path / "budget.json", 10, 0)
    with budget.activate(), pytest.raises(LLMError, match="스트림이 중단"):
        AnthropicProvider(api_key="synthetic-key").generate(
            LLMRequest(
                system="test",
                user="test",
                model="claude-sonnet-5-5",
                max_output_tokens=100,
                max_retries=2,
            )
        )
    assert len(budget.data["attempts"]) == 1 and "actual_usd" not in budget.data["attempts"][0]


@pytest.mark.django_db(transaction=True)
def test_two_executors_only_one_handler(monkeypatch):
    job = jobs.enqueue("SCOPE_TEST", run_inline=False)
    barrier = threading.Barrier(2)
    calls = []
    monkeypatch.setitem(
        jobs._HANDLERS, "SCOPE_TEST", lambda job, report: calls.append(job.pk) or {}
    )

    def worker():
        try:
            copy = Job.objects.get(pk=job.pk)
            barrier.wait()
            jobs.execute(copy)
        finally:
            connection.close()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert calls == [job.pk]
