from rest_framework import serializers

from apps.company.models import Product
from apps.evaluation.context import reference_date
from apps.evaluation.models import RequirementEvaluation
from apps.evaluation.serializers import EvaluationSerializer

from .models import (
    BidAttachment,
    BidItem,
    BidNotice,
    BidProductMatch,
    BidRequirement,
    RequirementCategory,
)

EDITABLE_NOTICE_FIELDS = [
    "notice_no",
    "title",
    "buyer_org",
    "contracting_org",
    "buyer_contact",
    "contract_contact",
    "plant_name",
    "is_power_plant",
    "bid_method",
    "procurement_type",
    "item_category_code",
    "item_category_name",
    "budget_krw",
    "estimated_price_krw",
    "bid_open_at",
    "bid_close_at",
    "opening_at",
    "qualification_deadline_at",
    "delivery_terms",
    "delivery_place",
    "warranty_terms",
    "summary",
]


class BidListSerializer(serializers.ModelSerializer):
    outcome_label = serializers.CharField(source="get_outcome_display", read_only=True)
    review_status_label = serializers.CharField(source="get_review_status_display", read_only=True)
    processing_status_label = serializers.CharField(
        source="get_processing_status_display", read_only=True
    )
    item_count = serializers.IntegerField(read_only=True)
    requirement_count = serializers.IntegerField(read_only=True)
    attachment_count = serializers.IntegerField(read_only=True)
    matched_models = serializers.SerializerMethodField()
    verdict_counts = serializers.SerializerMethodField()

    class Meta:
        model = BidNotice
        fields = [
            "id",
            "notice_no",
            "source_ref",
            "title",
            "buyer_org",
            "bid_close_at",
            "budget_krw",
            "fit_score",
            "is_power_plant",
            "outcome",
            "outcome_label",
            "review_status",
            "review_status_label",
            "processing_status",
            "processing_status_label",
            "item_count",
            "requirement_count",
            "attachment_count",
            "matched_models",
            "verdict_counts",
            "created_at",
        ]

    def get_verdict_counts(self, obj) -> dict:
        return (obj.extra or {}).get("verdict_counts") or {}

    def get_matched_models(self, obj) -> list[str]:
        models = {
            item.matched_product.model_no for item in obj.items.all() if item.matched_product_id
        }
        return sorted(models)


class AttachmentSerializer(serializers.ModelSerializer):
    document_id = serializers.IntegerField(source="document.id", read_only=True)
    display_name = serializers.CharField(source="document.display_name", read_only=True)
    file_format = serializers.CharField(source="document.file_format", read_only=True)
    file_size = serializers.IntegerField(source="document.file_size", read_only=True)
    has_file = serializers.SerializerMethodField()
    status = serializers.CharField(source="document.status", read_only=True)
    status_label = serializers.CharField(source="document.get_status_display", read_only=True)
    error_message = serializers.CharField(source="document.error_message", read_only=True)
    category_name = serializers.CharField(
        source="document.category.name", read_only=True, default=None
    )
    metadata_count = serializers.IntegerField(source="document.metadata.count", read_only=True)

    class Meta:
        model = BidAttachment
        fields = [
            "id",
            "document_id",
            "display_name",
            "file_format",
            "file_size",
            "has_file",
            "status",
            "status_label",
            "error_message",
            "role",
            "category_name",
            "is_primary",
            "order",
            "metadata_count",
        ]
        read_only_fields = ["id", "role"]

    def get_has_file(self, obj) -> bool:
        return bool(obj.document.file)


class BidDetailSerializer(BidListSerializer):
    attachments = AttachmentSerializer(many=True, read_only=True)
    locked_fields = serializers.ListField(read_only=True)
    fit_breakdown = serializers.SerializerMethodField()
    placeholders = serializers.SerializerMethodField()
    reviewed_by_name = serializers.SerializerMethodField()
    reference = serializers.SerializerMethodField()
    modified_evaluation_count = serializers.SerializerMethodField()

    class Meta(BidListSerializer.Meta):
        fields = [
            *BidListSerializer.Meta.fields,
            *[f for f in EDITABLE_NOTICE_FIELDS if f not in BidListSerializer.Meta.fields],
            "fit_reason",
            "fit_breakdown",
            "placeholders",
            "processing_error",
            "reviewed_at",
            "reviewed_by_name",
            "reference",
            "modified_evaluation_count",
            "source_text",
            "attachments",
            "locked_fields",
            "updated_at",
        ]

    def get_fit_breakdown(self, obj) -> dict:
        return (obj.extra or {}).get("fit_breakdown") or {}

    def get_placeholders(self, obj) -> list:
        return (obj.extra or {}).get("placeholders") or []

    def get_reviewed_by_name(self, obj) -> str | None:
        user = obj.reviewed_by
        return (user.display_name or user.username) if user else None

    def get_reference(self, obj) -> dict:
        """판정 기준일 (specs/08 §5) — is_simulation shows the 'past notice' badge."""
        ref, simulation = reference_date(obj)
        return {"date": str(ref), "is_simulation": simulation}

    def get_modified_evaluation_count(self, obj) -> int:
        return RequirementEvaluation.objects.filter(requirement__bid=obj, is_modified=True).count()


class BidUpdateSerializer(serializers.ModelSerializer):
    unlock_fields = serializers.ListField(
        child=serializers.CharField(), required=False, write_only=True
    )

    class Meta:
        model = BidNotice
        fields = [*EDITABLE_NOTICE_FIELDS, "outcome", "unlock_fields"]

    def update(self, instance, validated_data):
        unlock = set(validated_data.pop("unlock_fields", []))
        changed = {
            name
            for name, value in validated_data.items()
            if name in EDITABLE_NOTICE_FIELDS and getattr(instance, name) != value
        }
        locked = (set(instance.locked_fields) | changed) - unlock
        instance = super().update(instance, validated_data)
        instance.extra = {**(instance.extra or {}), "locked_fields": sorted(locked)}
        instance.save(update_fields=["extra", "updated_at"])
        return instance


class ProductMatchSerializer(serializers.ModelSerializer):
    model_no = serializers.CharField(source="product.model_no", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = BidProductMatch
        fields = ["product", "model_no", "product_name", "score", "reason", "rank"]


class BidItemSerializer(serializers.ModelSerializer):
    matched_product = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all(), allow_null=True, required=False
    )
    matched_model_no = serializers.CharField(
        source="matched_product.model_no", read_only=True, default=None
    )
    candidates = ProductMatchSerializer(source="product_matches", many=True, read_only=True)
    filter_type_label = serializers.CharField(source="get_filter_type_display", read_only=True)

    class Meta:
        model = BidItem
        fields = [
            "id",
            "item_no",
            "name",
            "spec_text",
            "filter_type",
            "filter_type_label",
            "width_mm",
            "height_mm",
            "depth_mm",
            "depth_mm_max",
            "diameter_mm",
            "diameter2_mm",
            "length_mm",
            "quantity",
            "unit",
            "material_no",
            "notes",
            "matched_product",
            "matched_model_no",
            "match_score",
            "candidates",
        ]
        read_only_fields = ["id", "match_score"]


class BidRequirementSerializer(serializers.ModelSerializer):
    category_label = serializers.CharField(source="get_category_display", read_only=True)
    item_label = serializers.SerializerMethodField()
    source_attachment_name = serializers.CharField(
        source="source_attachment.document.display_name", read_only=True, default=None
    )
    category = serializers.ChoiceField(choices=RequirementCategory.choices)

    class Meta:
        model = BidRequirement
        fields = [
            "id",
            "item",
            "item_label",
            "category",
            "category_label",
            "title",
            "requirement_text",
            "normalized",
            "is_mandatory",
            "source_attachment",
            "source_attachment_name",
            "source_page",
            "source_quote",
            "order",
            "source",
            "is_locked",
            "updated_at",
        ]
        read_only_fields = ["id", "source", "updated_at"]

    def get_item_label(self, obj) -> str | None:
        return str(obj.item) if obj.item_id else None

    def validate_normalized(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("정규화 값은 JSON 객체여야 합니다.")
        return value

    def validate(self, attrs):
        bid = self.context["bid"]
        item = attrs.get("item")
        if item is not None and item.bid_id != bid.pk:
            raise serializers.ValidationError({"item": ["이 공고의 품목이 아닙니다."]})
        attachment = attrs.get("source_attachment")
        if attachment is not None and attachment.bid_id != bid.pk:
            raise serializers.ValidationError({"source_attachment": ["이 공고의 첨부가 아닙니다."]})
        return attrs


class RequirementWithEvaluationSerializer(BidRequirementSerializer):
    """`?include=evaluation` (specs/10)."""

    evaluation = serializers.SerializerMethodField()

    class Meta(BidRequirementSerializer.Meta):
        fields = [*BidRequirementSerializer.Meta.fields, "evaluation"]

    def get_evaluation(self, obj) -> dict | None:
        evaluation = getattr(obj, "evaluation", None)
        if evaluation is None:
            return None
        return EvaluationSerializer(
            evaluation, context={"doc_map": self.context.get("doc_map")}
        ).data
