from django.db import models, transaction

from apps.core.models import TimeStampedModel

from . import crypto


class Provider(models.TextChoices):
    OPENAI = "OPENAI", "ChatGPT (OpenAI)"
    ANTHROPIC = "ANTHROPIC", "Claude (Anthropic)"
    GEMINI = "GEMINI", "Gemini (Google)"


class LLMProviderConfig(TimeStampedModel):
    """Per-provider API key (Fernet-encrypted) and connection status (specs/02 §8)."""

    provider = models.CharField(max_length=20, choices=Provider.choices, unique=True)
    api_key_encrypted = models.TextField(blank=True)
    api_key_last4 = models.CharField(max_length=4, blank=True)
    base_url = models.CharField(max_length=255, blank=True)
    is_enabled = models.BooleanField(default=False)
    last_verified_at = models.DateTimeField(null=True, blank=True)
    last_verify_ok = models.BooleanField(null=True)
    last_verify_error = models.TextField(blank=True)

    class Meta:
        ordering = ["provider"]

    def __str__(self):
        return self.get_provider_display()

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key_encrypted)

    @property
    def api_key_masked(self) -> str:
        return f"••••{self.api_key_last4}" if self.has_api_key else ""

    def set_api_key(self, raw_key: str) -> None:
        raw_key = raw_key.strip()
        self.api_key_encrypted = crypto.encrypt(raw_key)
        self.api_key_last4 = raw_key[-4:]

    def get_api_key(self) -> str:
        return crypto.decrypt(self.api_key_encrypted) if self.has_api_key else ""


class LLMModelOption(TimeStampedModel):
    provider = models.CharField(max_length=20, choices=Provider.choices)
    model_id = models.CharField(max_length=100)
    display_name = models.CharField(max_length=100)
    supports_pdf_input = models.BooleanField(default=False)
    max_output_tokens = models.PositiveIntegerField(null=True, blank=True)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["provider", "order", "model_id"]
        constraints = [
            models.UniqueConstraint(fields=["provider", "model_id"], name="uniq_provider_model")
        ]

    def __str__(self):
        return f"{self.provider}:{self.model_id}"

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if self.is_default:
                LLMModelOption.objects.filter(provider=self.provider, is_default=True).exclude(
                    pk=self.pk
                ).update(is_default=False)
            super().save(*args, **kwargs)


def default_task_overrides():
    return {
        "evaluation.judge": {"temperature": 0.0, "max_output_tokens": 32000},
        "bid.extract": {"temperature": 0.0, "max_output_tokens": 32000},
        "draft.*": {"temperature": 0.3, "max_output_tokens": 32000},
    }


class LLMSettings(TimeStampedModel):
    """Singleton (pk=1) holding the active provider/model and generation parameters."""

    active_provider = models.CharField(
        max_length=20, choices=Provider.choices, default=Provider.ANTHROPIC
    )
    active_model = models.ForeignKey(
        LLMModelOption, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    temperature = models.FloatField(default=0.2)
    max_output_tokens = models.PositiveIntegerField(default=8192)
    timeout_sec = models.PositiveIntegerField(default=180)
    max_retries = models.PositiveIntegerField(default=2)
    json_mode = models.BooleanField(default=True)
    per_task_overrides = models.JSONField(default=default_task_overrides, blank=True)

    class Meta:
        verbose_name = "LLM settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "LLMSettings":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class PromptTemplate(TimeStampedModel):
    """Versioned prompt per task key; exactly one active version per key (specs/02 §8)."""

    key = models.CharField(max_length=100, db_index=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    system_prompt = models.TextField()
    user_prompt_template = models.TextField()
    output_schema = models.JSONField(null=True, blank=True)
    version = models.PositiveIntegerField()
    is_active = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    updated_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["key", "-version"]
        constraints = [
            models.UniqueConstraint(fields=["key", "version"], name="uniq_prompt_key_version"),
            models.UniqueConstraint(
                fields=["key"], condition=models.Q(is_active=True), name="uniq_active_prompt"
            ),
        ]

    def __str__(self):
        return f"{self.key} v{self.version}"

    @classmethod
    def active(cls, key: str) -> "PromptTemplate | None":
        return cls.objects.filter(key=key, is_active=True).first()

    def activate(self) -> None:
        with transaction.atomic():
            PromptTemplate.objects.filter(key=self.key, is_active=True).exclude(pk=self.pk).update(
                is_active=False
            )
            self.is_active = True
            self.save(update_fields=["is_active", "updated_at"])


class LLMCallLog(models.Model):
    """One LLM request. Never stores the API key (specs/02 §8)."""

    class Status(models.TextChoices):
        OK = "OK", "성공"
        ERROR = "ERROR", "오류"
        INVALID_JSON = "INVALID_JSON", "형식 오류"

    task_key = models.CharField(max_length=100, db_index=True)
    provider = models.CharField(max_length=20, choices=Provider.choices)
    model_id = models.CharField(max_length=100)
    prompt_template = models.ForeignKey(
        PromptTemplate, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    prompt_version = models.PositiveIntegerField(null=True, blank=True)
    request_tokens = models.PositiveIntegerField(null=True, blank=True)
    response_tokens = models.PositiveIntegerField(null=True, blank=True)
    latency_ms = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices)
    error = models.TextField(blank=True)
    request_excerpt = models.TextField(blank=True)
    response_text = models.TextField(blank=True)
    job = models.ForeignKey(
        "core.Job", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.task_key} {self.model_id} {self.status}"
