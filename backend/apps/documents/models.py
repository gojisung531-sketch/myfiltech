import uuid
from pathlib import Path

from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel


class OwnerType(models.TextChoices):
    COMPANY = "COMPANY", "회사 자료"
    BID = "BID", "입찰 첨부"


class FileFormat(models.TextChoices):
    TXT = "TXT"
    DOCX = "DOCX"
    DOC = "DOC"
    HWP = "HWP"
    HWPX = "HWPX"
    PDF = "PDF"
    XLS = "XLS"
    XLSX = "XLSX"


class MetadataSchema(TimeStampedModel):
    """Document category and its metadata field definitions (specs/02 §3, specs/06 §4)."""

    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    owner_type = models.CharField(max_length=10, choices=OwnerType.choices)
    description = models.TextField(blank=True)
    filename_patterns = models.JSONField(default=list, blank=True)
    fields = models.JSONField(default=list, blank=True)
    target_model = models.CharField(max_length=100, blank=True)
    priority = models.PositiveIntegerField(default=100)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["owner_type", "priority", "code"]

    def __str__(self):
        return f"{self.name} ({self.code})"

    def field(self, key: str) -> dict | None:
        return next((f for f in self.fields if f.get("key") == key), None)


def document_upload_to(instance, filename: str) -> str:
    ext = Path(filename).suffix.lower()
    now = timezone.now()
    return f"documents/{now:%Y}/{now:%m}/{uuid.uuid4().hex}{ext}"


class Document(TimeStampedModel):
    class Status(models.TextChoices):
        UPLOADED = "UPLOADED", "업로드됨"
        PARSING = "PARSING", "텍스트 추출 중"
        PARSED = "PARSED", "텍스트 추출됨"
        NEEDS_OCR = "NEEDS_OCR", "OCR 필요"
        EXTRACTING = "EXTRACTING", "메타데이터 추출 중"
        EXTRACTED = "EXTRACTED", "추출 완료"
        REVIEWED = "REVIEWED", "검토 완료"
        FAILED = "FAILED", "실패"

    class CategorySource(models.TextChoices):
        AUTO = "AUTO", "자동"
        MANUAL = "MANUAL", "수동"

    title = models.CharField(max_length=255, blank=True)
    file = models.FileField(upload_to=document_upload_to, blank=True)
    original_filename = models.CharField(max_length=255, blank=True)
    file_format = models.CharField(max_length=10, choices=FileFormat.choices)
    file_size = models.PositiveBigIntegerField(default=0)
    sha256 = models.CharField(max_length=64, blank=True, db_index=True)
    source_text = models.TextField(blank=True)
    extracted_text = models.TextField(blank=True)
    extracted_tables = models.JSONField(default=list, blank=True)
    page_count = models.PositiveIntegerField(null=True, blank=True)
    category = models.ForeignKey(
        MetadataSchema, null=True, blank=True, on_delete=models.SET_NULL, related_name="documents"
    )
    category_confidence = models.FloatField(null=True, blank=True)
    category_source = models.CharField(
        max_length=10, choices=CategorySource.choices, default=CategorySource.AUTO
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.UPLOADED)
    error_message = models.TextField(blank=True)
    owner_type = models.CharField(max_length=10, choices=OwnerType.choices)
    created_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.display_name

    @property
    def display_name(self) -> str:
        return self.title or self.original_filename or f"문서 #{self.pk}"


class DocumentMetadata(TimeStampedModel):
    class Source(models.TextChoices):
        RULE = "RULE", "규칙"
        LLM = "LLM", "LLM"
        MANUAL = "MANUAL", "수동"

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="metadata")
    key = models.CharField(max_length=100)
    label = models.CharField(max_length=100, blank=True)
    value = models.JSONField(null=True, blank=True)
    raw_value = models.TextField(blank=True)
    unit = models.CharField(max_length=20, blank=True)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.RULE)
    confidence = models.FloatField(null=True, blank=True)
    evidence_page = models.PositiveIntegerField(null=True, blank=True)
    evidence_quote = models.TextField(blank=True)
    is_locked = models.BooleanField(default=False)
    updated_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["document", "id"]
        constraints = [
            models.UniqueConstraint(fields=["document", "key"], name="uniq_document_metadata_key")
        ]

    def __str__(self):
        return f"{self.document_id}:{self.key}"
