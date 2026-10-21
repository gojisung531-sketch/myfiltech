"""Draft documents (specs/02 §7, specs/09)."""

from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class DraftType(models.TextChoices):
    COMPLIANCE_MATRIX = "COMPLIANCE_MATRIX", "Compliance Matrix"
    BID_CHECKLIST = "BID_CHECKLIST", "입찰 체크리스트"
    TECHNICAL_QUERY = "TECHNICAL_QUERY", "발주처 기술질의서"
    REVIEW_REPORT = "REVIEW_REPORT", "검토 보고서"


class DraftDocument(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "초안"
        FINAL = "FINAL", "확정"

    class GeneratedBy(models.TextChoices):
        AUTO = "AUTO", "자동 생성"
        MANUAL = "MANUAL", "직접 작성"

    bid = models.ForeignKey("bids.BidNotice", on_delete=models.CASCADE, related_name="drafts")
    doc_type = models.CharField(max_length=20, choices=DraftType.choices)
    title = models.CharField(max_length=300)
    content = models.JSONField(default=dict)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    version = models.PositiveIntegerField(default=1)
    generated_by = models.CharField(
        max_length=10, choices=GeneratedBy.choices, default=GeneratedBy.AUTO
    )
    is_modified = models.BooleanField(default=False)
    used_llm = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["bid_id", "doc_type", "-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["bid", "doc_type", "version"], name="unique_draft_version"
            )
        ]

    def __str__(self):
        return f"{self.bid_id} {self.doc_type} v{self.version}"

    @classmethod
    def latest(cls, bid, doc_type: str) -> "DraftDocument | None":
        return cls.objects.filter(bid=bid, doc_type=doc_type).order_by("-version").first()
