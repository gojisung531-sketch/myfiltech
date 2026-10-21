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
