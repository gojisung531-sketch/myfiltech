"""Structured company data (specs/02-data-model.md §4)."""

from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel


class Company(TimeStampedModel):
    """Singleton (pk=1)."""

    name = models.CharField(max_length=100, blank=True)
    ceo = models.CharField(max_length=50, blank=True)
    business_no = models.CharField(max_length=20, blank=True)
    address = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    homepage = models.CharField(max_length=255, blank=True)
    established_date = models.DateField(null=True, blank=True)
    employees = models.PositiveIntegerField(null=True, blank=True)
    is_sme = models.BooleanField(null=True)
    sme_cert_valid_until = models.DateField(null=True, blank=True)
    g2b_registered_items = models.JSONField(default=list, blank=True)
    main_products = models.TextField(blank=True)
    description = models.TextField(blank=True)
    source_documents = models.ManyToManyField("documents.Document", blank=True, related_name="+")

    class Meta:
        verbose_name_plural = "companies"

    def __str__(self):
        return self.name or "회사"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "Company":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class FilterType(models.TextChoices):
    PANEL = "PANEL", "패널형"
    POCKET_BAG = "POCKET_BAG", "포켓/백필터"
    V_BANK = "V_BANK", "V-bank"
    MINI_PLEAT_HEPA = "MINI_PLEAT_HEPA", "미니플리트/HEPA"
    CARTRIDGE_PULSE = "CARTRIDGE_PULSE", "펄스 카트리지"
    DEMISTER = "DEMISTER", "데미스터"
    CARBON = "CARBON", "카본(활성탄)"
    OTHER = "OTHER", "기타"


class Product(TimeStampedModel):
    model_no = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=200, blank=True)
    filter_type = models.CharField(
        max_length=20, choices=FilterType.choices, default=FilterType.OTHER
    )
    application = models.TextField(blank=True)
    width_mm = models.FloatField(null=True, blank=True)
    height_mm = models.FloatField(null=True, blank=True)
    depth_mm = models.FloatField(null=True, blank=True)
    diameter_mm = models.FloatField(null=True, blank=True)
    diameter2_mm = models.FloatField(null=True, blank=True)
    length_mm = models.FloatField(null=True, blank=True)
    dimension_text = models.CharField(max_length=255, blank=True)
    dimension_variants = models.JSONField(default=list, blank=True)
    media = models.CharField(max_length=200, blank=True)
    frame_material = models.CharField(max_length=200, blank=True)
    frame_options = models.JSONField(default=list, blank=True)
    gasket = models.CharField(max_length=200, blank=True)
    rated_airflow_m3h = models.FloatField(null=True, blank=True)
    initial_dp_pa = models.FloatField(null=True, blank=True)
    final_dp_pa = models.FloatField(null=True, blank=True)
    airflow_dp_curve = models.JSONField(default=list, blank=True)
    iso16890_class = models.CharField(max_length=50, blank=True)
    iso29461_class = models.CharField(max_length=20, blank=True)
    en1822_class = models.CharField(max_length=20, blank=True)
    en779_class = models.CharField(max_length=20, blank=True)
    ashrae_merv = models.PositiveSmallIntegerField(null=True, blank=True)
    max_temp_c = models.FloatField(null=True, blank=True)
    max_rh = models.FloatField(null=True, blank=True)
    fire_rating = models.CharField(max_length=200, blank=True)
    revision = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)
    source_document = models.ForeignKey(
        "documents.Document", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    extra = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["model_no"]

    def __str__(self):
        return self.model_no


class StandardFamily(models.TextChoices):
    ISO16890 = "ISO16890", "ISO 16890"
    ISO29461 = "ISO29461", "ISO 29461-1"
    EN1822 = "EN1822", "EN 1822"
    EN779 = "EN779", "EN 779"
    ASHRAE52_1 = "ASHRAE52_1", "ASHRAE 52.1"
    ASHRAE52_2 = "ASHRAE52_2", "ASHRAE 52.2"
    UL900 = "UL900", "UL 900"
    KS = "KS", "KS"
    OTHER = "OTHER", "기타"


class TestReport(TimeStampedModel):
    report_no = models.CharField(max_length=50, unique=True)
    product = models.ForeignKey(
        Product, null=True, blank=True, on_delete=models.SET_NULL, related_name="test_reports"
    )
    model_no_text = models.CharField(max_length=50, blank=True)
    sample_name = models.CharField(max_length=200, blank=True)
    sample_dimension = models.CharField(max_length=255, blank=True)
    standard = models.CharField(max_length=100, blank=True)
    standard_family = models.CharField(
        max_length=20, choices=StandardFamily.choices, default=StandardFamily.OTHER
    )
    is_obsolete_standard = models.BooleanField(default=False)
    test_date = models.DateField(null=True, blank=True)
    issue_date = models.DateField(null=True, blank=True)
    lab_name = models.CharField(max_length=200, blank=True)
    lab_accreditation = models.CharField(max_length=200, blank=True)
    is_official_certification = models.BooleanField(default=True)
    result_class = models.CharField(max_length=100, blank=True)
    test_airflow_m3h = models.FloatField(null=True, blank=True)
    initial_dp_pa = models.FloatField(null=True, blank=True)
    results = models.JSONField(default=dict, blank=True)
    conditions = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)
    source_document = models.ForeignKey(
        "documents.Document", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["-issue_date", "report_no"]

    def __str__(self):
        return self.report_no


class CertType(models.TextChoices):
    ISO9001 = "ISO9001", "ISO 9001"
    ISO14001 = "ISO14001", "ISO 14001"
    ISO45001 = "ISO45001", "ISO 45001"
    DIRECT_PRODUCTION = "DIRECT_PRODUCTION", "직접생산확인"
    SME = "SME", "중소기업확인"
    KS = "KS", "KS"
    PATENT = "PATENT", "특허"
    WOMEN_ENTERPRISE = "WOMEN_ENTERPRISE", "여성기업확인"
    INNOBIZ = "INNOBIZ", "기술혁신형 중소기업"
    POWER_DEVELOPMENT = "POWER_DEVELOPMENT", "발전사 개발선정품 등록"
    MAINTENANCE = "MAINTENANCE", "정비적격기업"
    SUPPLIER = "SUPPLIER", "기자재 공급 유자격 등록"
    TECHNOLOGY_MARKET = "TECHNOLOGY_MARKET", "중소기업기술마켓"
    ORIGIN_EXPORTER = "ORIGIN_EXPORTER", "품목별 원산지인증수출자"
    KEPCO_PARTNER = "KEPCO_PARTNER", "한전 우수협력사"
    OTHER = "OTHER", "기타"


class Certificate(TimeStampedModel):
    class Status(models.TextChoices):
        VALID = "VALID", "유효"
        EXPIRING = "EXPIRING", "만료 임박"
        EXPIRED = "EXPIRED", "만료"
        UNKNOWN = "UNKNOWN", "확인 필요"

    cert_no = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=200, blank=True)
    cert_type = models.CharField(max_length=20, choices=CertType.choices, default=CertType.OTHER)
    standard = models.CharField(max_length=200, blank=True)
    holder = models.CharField(max_length=200, blank=True)
    scope = models.TextField(blank=True)
    product_codes = models.JSONField(default=list, blank=True)
    issuer = models.CharField(max_length=200, blank=True)
    issue_date = models.DateField(null=True, blank=True)
    valid_from = models.DateField(null=True, blank=True)
    valid_until = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    source_document = models.ForeignKey(
        "documents.Document", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["cert_type", "cert_no"]

    def __str__(self):
        return f"{self.name or self.cert_type} ({self.cert_no})"

    def status_on(self, reference: date | None = None, expiring_days: int = 90) -> str:
        """VALID / EXPIRING / EXPIRED relative to `reference` (default: today)."""
        reference = reference or timezone.localdate()
        if self.valid_until is None:
            return self.Status.UNKNOWN
        if self.valid_until < reference:
            return self.Status.EXPIRED
        if self.valid_until <= reference + timedelta(days=expiring_days):
            return self.Status.EXPIRING
        return self.Status.VALID


class PlantType(models.TextChoices):
    CCPP = "CCPP", "복합화력"
    THERMAL = "THERMAL", "화력"
    CHP = "CHP", "열병합/지역난방"
    OTHER = "OTHER", "기타"


class DeliveryRecord(TimeStampedModel):
    delivered_ym = models.CharField(max_length=10)
    client = models.CharField(max_length=200)
    project_name = models.CharField(max_length=255, blank=True)
    item_desc = models.CharField(max_length=200, blank=True)
    model_nos = models.JSONField(default=list, blank=True)
    products = models.ManyToManyField(Product, blank=True, related_name="delivery_records")
    quantity = models.JSONField(default=list, blank=True)
    amount_krw = models.BigIntegerField(null=True, blank=True)
    is_power_plant = models.BooleanField(default=False)
    plant_type = models.CharField(max_length=10, choices=PlantType.choices, default=PlantType.OTHER)
    notes = models.TextField(blank=True)
    source_document = models.ForeignKey(
        "documents.Document", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["-delivered_ym", "id"]

    def __str__(self):
        return f"{self.delivered_ym} {self.client} {self.project_name}"


class ReportRegisterVersion(TimeStampedModel):
    """One register byte version; deliberately separate from formal company evidence."""

    sha256 = models.CharField(
        max_length=64,
        unique=True,
        validators=[RegexValidator(r"^[0-9a-f]{64}$", "소문자 SHA256 값이어야 합니다.")],
    )
    display_name = models.CharField(max_length=255)
    parser_version = models.CharField(max_length=100)
    source_metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(sha256__regex=r"^[0-9a-f]{64}$"),
                name="report_register_sha256_valid",
            ),
        ]

    def __str__(self):
        return f"{self.display_name} ({self.sha256[:12]})"


class ReportRegisterRow(TimeStampedModel):
    """A source row awaiting review. Its payload never promotes itself to TestReport."""

    class ReviewStatus(models.TextChoices):
        PENDING = "PENDING", "검토 대기"
        NEEDS_CONFIRMATION = "NEEDS_CONFIRMATION", "확인 필요"

    class Ownership(models.TextChoices):
        UNKNOWN = "UNKNOWN", "불명"
        FILTECH = "FILTECH", "필텍 당사"
        THIRD_PARTY = "THIRD_PARTY", "타사"

    class TestTarget(models.TextChoices):
        UNKNOWN = "UNKNOWN", "불명"
        MEDIA = "MEDIA", "여재"
        FINISHED_PRODUCT = "FINISHED_PRODUCT", "완제품"
        OTHER = "OTHER", "그 밖의 시료"

    file_version = models.ForeignKey(
        ReportRegisterVersion, on_delete=models.PROTECT, related_name="rows"
    )
    sheet_name = models.CharField(max_length=128)
    row_number = models.PositiveIntegerField()
    payload = models.JSONField(default=dict, blank=True)
    review_status = models.CharField(
        max_length=20, choices=ReviewStatus.choices, default=ReviewStatus.PENDING
    )
    ownership = models.CharField(
        max_length=12, choices=Ownership.choices, default=Ownership.UNKNOWN
    )
    test_target = models.CharField(
        max_length=20, choices=TestTarget.choices, default=TestTarget.UNKNOWN
    )
    is_lab_accredited = models.BooleanField(null=True, blank=True, default=None)
    is_official_certification = models.BooleanField(null=True, blank=True, default=None)
    original_report_verified = models.BooleanField(null=True, blank=True, default=None)

    class Meta:
        ordering = ["file_version_id", "sheet_name", "row_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["file_version", "sheet_name", "row_number"],
                name="report_register_source_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(row_number__gte=1, row_number__lte=1048576),
                name="report_register_row_in_range",
            ),
            models.CheckConstraint(
                condition=~models.Q(sheet_name=""), name="report_register_sheet_not_empty"
            ),
        ]

    def clean(self):
        """Reject contradictory coordinates without rewriting any original payload."""
        super().clean()
        if not isinstance(self.payload, dict):
            raise ValidationError({"payload": "원본 행 payload는 JSON 객체여야 합니다."})
        if not self.payload:
            return  # An empty default is not evidence and is never eligible for evaluation.
        source = self.payload.get("source")
        if not isinstance(source, dict):
            raise ValidationError({"payload": "원본 source 객체가 필요합니다."})
        try:
            file_sha256 = self.file_version.sha256
        except ReportRegisterVersion.DoesNotExist:
            file_sha256 = None  # full_clean() reports an absent/invalid FK separately.
        if (
            source.get("sheet") != self.sheet_name
            or source.get("row") != self.row_number
            or (file_sha256 is not None and source.get("file_sha256") != file_sha256)
        ):
            raise ValidationError({"payload": "원본 출처와 파일 버전·시트·행 좌표가 다릅니다."})

    def __str__(self):
        return f"{self.file_version_id}: {self.sheet_name}!{self.row_number}"
