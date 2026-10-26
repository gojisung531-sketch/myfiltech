"""Opt-in, durable HTTP-attempt budget for a single scoped development worker."""

import hashlib
import json
import os
from contextlib import contextmanager
from contextvars import ContextVar
from decimal import Decimal
from pathlib import Path

from django.db import connection

from .providers.base import LLMError

ACTIVE = ContextVar("scoped_worker_budget", default=None)
RATES = {
    "claude-sonnet-5-5": (Decimal("2"), Decimal("10"), Decimal("0.10")),
    "claude-sonnet-5": (Decimal("2"), Decimal("10"), Decimal("0.20")),
}


class WorkerBudget:
    def __init__(self, path, limit, prior):
        self.path = Path(path).resolve()
        self.limit, self.prior = Decimal(str(limit)), Decimal(str(prior))
        if (
            not self.limit.is_finite()
            or not self.prior.is_finite()
            or not 0 <= self.prior < self.limit
        ):
            raise ValueError("예산과 이전 사용액 범위를 확인하세요.")
        self.blocked = ""
        self.job_id = None

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        with temp.open("w", encoding="utf8") as stream:
            json.dump(self.data, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, self.path)

    @contextmanager
    def activate(self):
        # A process crash releases the lock, but never clears durable reservations.
        if connection.vendor != "postgresql":
            raise ValueError("Scoped paid workers require PostgreSQL")
        key = (
            int.from_bytes(hashlib.sha256(str(self.path).encode()).digest()[:4], "big") & 0x7FFFFFFF
        )
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s, %s)", [74127, key])
            if not cursor.fetchone()[0]:
                raise ValueError("같은 비용 대장을 사용하는 워커가 이미 실행 중입니다.")
            cursor.execute("SELECT pg_backend_pid()")
            self.backend_pid = cursor.fetchone()[0]
        token = None
        try:
            if self.path.exists():
                self.data = json.loads(self.path.read_text(encoding="utf8"))
                if self.data["limit_usd"] != str(self.limit) or self.data["prior_usd"] != str(
                    self.prior
                ):
                    raise ValueError("기존 비용 대장의 예산/이전 사용액을 바꾸지 마세요.")
                for attempt in self.data["attempts"]:
                    self._settle_known(attempt)
                self._save()
            else:
                self.data = {
                    "limit_usd": str(self.limit),
                    "prior_usd": str(self.prior),
                    "attempts": [],
                }
                self._save()
            token = ACTIVE.set(self)
            yield self
        finally:
            if token is not None:
                ACTIVE.reset(token)
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s, %s)", [74127, key])

    def used(self):
        return self.prior + sum(
            (Decimal(a.get("actual_usd", a["reserved_usd"])) for a in self.data["attempts"]),
            Decimal(0),
        )

    def request(self, request):
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_backend_pid()")
            if cursor.fetchone()[0] != self.backend_pid:
                self.blocked = (
                    "DB 연결이 바뀌어 단독 워커 잠금을 다시 확인해야 합니다. 전송을 중단했습니다."
                )
                raise LLMError(self.blocked)
        data = json.loads(request.content)
        if (
            request.url.host != "api.anthropic.com"
            or request.method != "POST"
            or not request.url.path.rstrip("/").endswith("/messages")
            or data.get("model") != "claude-sonnet-5-5"
            or any(
                k in data
                for k in ["tools", "speed", "inference_geo", "service_tier", "cache_control"]
            )
            or any(c.get("type") != "text" for m in data.get("messages", []) for c in m["content"])
        ):
            self.blocked = "예산 검증 범위 밖의 모델/기능/원본 PDF 요청을 차단했습니다."
            raise LLMError(self.blocked)
        # Bound UTF-8 text/schema bytes plus server overhead and primary+fallback output.
        bound = Decimal(len(request.content) + 20000) * Decimal(".000004") + Decimal(
            data["max_tokens"]
        ) * Decimal(".000020")
        if self.used() + bound > self.limit:
            self.blocked = "승인된 총예산 한도를 넘을 수 있어 다음 API 요청을 전송하지 않았습니다."
            raise LLMError(self.blocked)
        self.data["attempts"].append(
            {
                "job_id": self.job_id,
                "model": data["model"],
                "max_tokens": data["max_tokens"],
                "reserved_usd": str(bound),
                "sdk_retry": request.headers.get("x-stainless-retry-count", "unknown"),
            }
        )
        self._save()  # Durable reservation BEFORE every wire attempt, including SDK retries.

    def response(self, response):
        self.data["attempts"][-1]["http_status"] = response.status_code
        self._save()

    def receipt(self, message):
        attempt = self.data["attempts"][-1]
        usage = message.usage.model_dump()
        attempt["receipt"] = {
            "id": message.id,
            "model": message.model,
            "stop_reason": message.stop_reason,
            "usage": usage,
            "fallback": bool(getattr(message, "fallback", None)),
        }
        self._settle_known(attempt)
        self._save()

    def _settle_known(self, attempt):
        receipt = attempt.get("receipt")
        if not receipt:
            return
        usage = receipt["usage"]
        iterations = usage.get("iterations") or []
        primary_only = not iterations or (
            len(iterations) == 1
            and iterations[0].get("type") == "message"
            and iterations[0].get("model") in (None, receipt["model"])
            and all(
                iterations[0].get(k, 0) == usage.get(k, 0)
                for k in [
                    "input_tokens",
                    "output_tokens",
                    "cache_read_input_tokens",
                    "cache_creation_input_tokens",
                ]
            )
        )
        # Unknown failed/partial/fallback attempts retain their full reservation.
        if (
            receipt["model"] in RATES
            and not receipt.get("fallback")
            and not usage.get("fallback_credit")
            and primary_only
        ):
            input_rate, output_rate, cache_rate = RATES[receipt["model"]]
            actual = (
                Decimal(usage.get("input_tokens") or 0) * input_rate
                + Decimal(usage.get("output_tokens") or 0) * output_rate
                + Decimal(usage.get("cache_read_input_tokens") or 0) * cache_rate
                + Decimal(usage.get("cache_creation_input_tokens") or 0) * 4
            ) / 1000000
            if actual > Decimal(attempt["reserved_usd"]):
                self.blocked = "실제 사용량이 예약 상한을 초과해 후속 요청을 중단했습니다."
                self._save()
                raise LLMError(self.blocked)
            attempt["actual_usd"] = str(actual)


def active():
    return ACTIVE.get()
