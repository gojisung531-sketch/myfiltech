"""Bid notices, attachments, items and key requirements (specs/02-data-model.md §5)."""

from django.db import models

from apps.company.models import FilterType
from apps.core.models import TimeStampedModel


class BidNotice(TimeStampedModel):
    class Outcome(models.TextChoices):
        PENDING = "PENDING", "진행 중"
        WON = "WON", "낙찰"
        LOST = "LOST", "미낙찰"
        NOT_BID = "NOT_BID", "불참"

    class ReviewStatus(models.TextChoices):
        UNREVIEWED = "UNREVIEWED", "미확인"
        REVIEWED = "REVIEWED", "확인"

    class ProcessingStatus(models.TextChoices):
        DRAFT = "DRAFT", "등록됨"
        EXTRACTING = "EXTRACTING", "추출 중"
        EXTRACTED = "EXTRACTED", "추출 완료"
        EVALUATING = "EVALUATING", "판정 중"
        EVALUATED = "EVALUATED", "판정 완료"
        FAILED = "FAILED", "실패"

    notice_no = models.CharField(max_length=50, blank=True, db_index=True)
    source_ref = models.CharField(max_length=100, blank=True, db_index=True)
    title = models.CharField(max_length=300)
    buyer_org = models.CharField(max_length=200, blank=True)
    contracting_org = models.CharField(max_length=200, blank=True)
    buyer_contact = models.JSONField(default=dict, blank=True)
    contract_contact = models.JSONField(default=dict, blank=True)
    plant_name = models.CharField(max_length=200, blank=True)
    is_power_plant = models.BooleanField(null=True)
    bid_method = models.CharField(max_length=200, blank=True)
    procurement_type = models.CharField(max_length=50, blank=True)
    item_category_code = models.CharField(max_length=30, blank=True)
    item_category_name = models.CharField(max_length=100, blank=True)
    budget_krw = models.BigIntegerField(null=True, blank=True)
    estimated_price_krw = models.BigIntegerField(null=True, blank=True)
    bid_open_at = models.DateTimeField(null=True, blank=True)
    bid_close_at = models.DateTimeField(null=True, blank=True, db_index=True)
    opening_at = models.DateTimeField(null=True, blank=True)
    qualification_deadline_at = models.DateTimeField(null=True, blank=True)
    delivery_terms = models.CharField(max_length=300, blank=True)
    delivery_place = models.CharField(max_length=300, blank=True)
    warranty_terms = models.CharField(max_length=300, blank=True)
    summary = models.TextField(blank=True)
    fit_score = models.PositiveSmallIntegerField(null=True, blank=True)
    fit_reason = models.TextField(blank=True)
    outcome = models.CharField(max_length=10, choices=Outcome.choices, default=Outcome.PENDING)
    review_status = models.CharField(
        max_length=12, choices=ReviewStatus.choices, default=ReviewStatus.UNREVIEWED
    )
    reviewed_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    processing_status = models.CharField(
        max_length=12, choices=ProcessingStatus.choices, default=ProcessingStatus.DRAFT
    )
    processing_error = models.TextField(blank=True)
    source_text = models.TextField(blank=True)
    extra = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    @property
    def locked_fields(self) -> list[str]:
        return list((self.extra or {}).get("locked_fields", []))


class BidAttachment(TimeStampedModel):
    bid = models.ForeignKey(BidNotice, on_delete=models.CASCADE, related_name="attachments")
    document = models.OneToOneField(
        "documents.Document", on_delete=models.CASCADE, related_name="bid_attachment"
    )
    role = models.CharField(max_length=50, blank=True)
    is_primary = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["bid", "-is_primary", "order", "id"]

    def __str__(self):
        return self.document.display_name


class BidItem(TimeStampedModel):
    bid = models.ForeignKey(BidNotice, on_delete=models.CASCADE, related_name="items")
    item_no = models.CharField(max_length=30, blank=True)
    name = models.CharField(max_length=300)
    spec_text = models.TextField(blank=True)
    filter_type = models.CharField(max_length=20, choices=FilterType.choices, blank=True)
    width_mm = models.FloatField(null=True, blank=True)
    height_mm = models.FloatField(null=True, blank=True)
    depth_mm = models.FloatField(null=True, blank=True)
    depth_mm_max = models.FloatField(null=True, blank=True)
    diameter_mm = models.FloatField(null=True, blank=True)
    diameter2_mm = models.FloatField(null=True, blank=True)
    length_mm = models.FloatField(null=True, blank=True)
    quantity = models.FloatField(null=True, blank=True)
    unit = models.CharField(max_length=20, blank=True)
    material_no = models.CharField(max_length=50, blank=True)
    notes = models.TextField(blank=True)
    source_attachment = models.ForeignKey(
        BidAttachment, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    matched_product = models.ForeignKey(
        "company.Product", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    match_score = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ["bid", "id"]

    def __str__(self):
        return f"{self.item_no} {self.name}".strip()

    @property
    def dimension(self) -> dict:
        return {
            "w": self.width_mm,
            "h": self.height_mm,
            "d": self.depth_mm,
            "d_max": self.depth_mm_max,
            "dia": self.diameter_mm,
            "dia2": self.diameter2_mm,
            "len": self.length_mm,
        }


class BidProductMatch(models.Model):
    bid = models.ForeignKey(BidNotice, on_delete=models.CASCADE, related_name="product_matches")
    item = models.ForeignKey(BidItem, on_delete=models.CASCADE, related_name="product_matches")
    product = models.ForeignKey("company.Product", on_delete=models.CASCADE, related_name="+")
    score = models.FloatField()
    reason = models.TextField(blank=True)
    rank = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ["item", "rank"]
        constraints = [
            models.UniqueConstraint(fields=["item", "product"], name="uniq_item_product_match")
        ]

    def __str__(self):
        return f"{self.item} → {self.product} ({self.score:.2f})"


class RequirementCategory(models.TextChoices):
    DIMENSION = "DIMENSION", "제품 치수"
    FILTER_TYPE = "FILTER_TYPE", "필터 형식"
    FILTER_GRADE = "FILTER_GRADE", "필터 등급"
    EFFICIENCY = "EFFICIENCY", "효율"
    PRESSURE_DROP = "PRESSURE_DROP", "차압"
    AIRFLOW = "AIRFLOW", "풍량"
    MATERIAL = "MATERIAL", "재질"
    ENVIRONMENT = "ENVIRONMENT", "사용 환경"
    FIRE_RATING = "FIRE_RATING", "난연"
    TEST_STANDARD = "TEST_STANDARD", "시험 규격"
    CERTIFICATION = "CERTIFICATION", "인증·자격"
    TRACK_RECORD = "TRACK_RECORD", "납품실적"
    DELIVERY = "DELIVERY", "납기"
    SUBMISSION_DOC = "SUBMISSION_DOC", "제출서류"
    WARRANTY = "WARRANTY", "하자보증"
    INSPECTION = "INSPECTION", "시험·검사"
    OTHER = "OTHER", "기타"


class BidRequirement(TimeStampedModel):
    class Source(models.TextChoices):
        LLM = "LLM", "LLM"
        RULE = "RULE", "규칙"
        MANUAL = "MANUAL", "수동"

    bid = models.ForeignKey(BidNotice, on_delete=models.CASCADE, related_name="requirements")
    item = models.ForeignKey(
        BidItem, null=True, blank=True, on_delete=models.SET_NULL, related_name="requirements"
    )
    category = models.CharField(max_length=20, choices=RequirementCategory.choices)
    title = models.CharField(max_length=200)
    requirement_text = models.TextField(blank=True)
    normalized = models.JSONField(default=dict, blank=True)
    is_mandatory = models.BooleanField(default=True)
    source_attachment = models.ForeignKey(
        BidAttachment, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    source_page = models.PositiveIntegerField(null=True, blank=True)
    source_quote = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.LLM)
    is_locked = models.BooleanField(default=False)

    class Meta:
        ordering = ["bid", "order", "id"]

    def __str__(self):
        return f"[{self.category}] {self.title}"
