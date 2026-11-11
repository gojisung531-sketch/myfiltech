from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AppSetting(TimeStampedModel):
    """Tunable key-value setting editable by admins (specs/02 §2, specs/07 §6)."""

    class ValueType(models.TextChoices):
        INT = "int", "정수"
        FLOAT = "float", "실수"
        BOOL = "bool", "참/거짓"
        STR = "str", "문자열"
        JSON = "json", "JSON"

    key = models.CharField(max_length=100, unique=True)
    value = models.JSONField(null=True, blank=True)
    value_type = models.CharField(max_length=10, choices=ValueType.choices)
    group = models.CharField(max_length=50, db_index=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["group", "key"]

    def __str__(self):
        return self.key


class Job(TimeStampedModel):
    """DB-backed background job (specs/01 §5). Executed by `manage.py run_jobs`."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "대기"
        RUNNING = "RUNNING", "실행 중"
        SUCCEEDED = "SUCCEEDED", "완료"
        FAILED = "FAILED", "실패"
        CANCELLED = "CANCELLED", "취소"

    type = models.CharField(max_length=50, db_index=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    target_type = models.CharField(max_length=50, blank=True)
    target_id = models.BigIntegerField(null=True, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    progress = models.PositiveSmallIntegerField(default=0)
    message = models.CharField(max_length=255, blank=True)
    result = models.JSONField(null=True, blank=True)
    error = models.TextField(blank=True)
    created_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.type}#{self.pk} {self.status}"

    @property
    def is_finished(self) -> bool:
        return self.status in (self.Status.SUCCEEDED, self.Status.FAILED, self.Status.CANCELLED)


class AnalysisRun(models.Model):
    """Prospective execution provenance; never backfilled from current business data."""

    bid = models.ForeignKey(
        "bids.BidNotice", on_delete=models.CASCADE, related_name="analysis_runs"
    )
    kind = models.CharField(max_length=20, choices=[("EVALUATION", "판정"), ("DRAFT", "초안")])
    inputs = models.JSONField()
    input_hash = models.CharField(max_length=64)
    guard_hash = models.CharField(max_length=64)
    options = models.JSONField(default=dict)
    outputs = models.JSONField(default=dict)
    started_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True)
    state = models.CharField(max_length=20, default="STARTED")
    failure_code = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return f"{self.bid_id} {self.kind} {self.state} {self.pk}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            old = type(self).objects.get(pk=self.pk)
            for field in (
                "bid_id",
                "kind",
                "inputs",
                "input_hash",
                "guard_hash",
                "options",
                "started_at",
            ):
                if getattr(old, field) != getattr(self, field):
                    raise ValueError("Analysis input provenance is immutable")
            if old.state == "COMPLETED" and (
                self.outputs != old.outputs or self.state != old.state
            ):
                raise ValueError("Completed execution provenance is immutable")
        super().save(*args, **kwargs)
