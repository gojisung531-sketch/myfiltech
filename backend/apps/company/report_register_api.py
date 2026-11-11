"""Admin-only stored register reads; no parsing, staging, mapping or evaluation."""

from functools import reduce
from operator import or_

from django.db.models import Count, F, Q
from rest_framework import serializers, viewsets

from apps.core.pagination import StandardPagination
from apps.core.permissions import IsAdminRole

from .models import ReportRegisterRow, ReportRegisterVersion

SUMMARY_FIELDS = ("report_no", "model", "sample_name", "test_standard", "lab_name", "issue_date")
SEARCH_FIELDS = SUMMARY_FIELDS[:-1]
REVIEW_FIELDS = (
    "review_status",
    "ownership",
    "test_target",
    "is_lab_accredited",
    "is_official_certification",
    "original_report_verified",
)


class PageQuery(serializers.Serializer):
    page = serializers.IntegerField(min_value=1, max_value=9223372036854775807, required=False)
    page_size = serializers.IntegerField(min_value=1, max_value=9223372036854775807, required=False)


class RowQuery(PageQuery):
    file_version = serializers.IntegerField(
        min_value=1, max_value=9223372036854775807, required=False
    )
    sheet_name = serializers.CharField(
        max_length=128, allow_blank=False, trim_whitespace=False, required=False
    )
    review_status = serializers.ChoiceField(
        choices=ReportRegisterRow.ReviewStatus.choices, required=False
    )
    ownership = serializers.ChoiceField(choices=ReportRegisterRow.Ownership.choices, required=False)
    test_target = serializers.ChoiceField(
        choices=ReportRegisterRow.TestTarget.choices, required=False
    )
    q = serializers.CharField(max_length=200, allow_blank=True, required=False)


class RegisterVersionSerializer(serializers.ModelSerializer):
    row_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = ReportRegisterVersion
        fields = [
            "id",
            "sha256",
            "display_name",
            "parser_version",
            "row_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class RegisterVersionDetailSerializer(RegisterVersionSerializer):
    sheet_counts = serializers.SerializerMethodField()
    review_status_counts = serializers.SerializerMethodField()

    class Meta(RegisterVersionSerializer.Meta):
        fields = RegisterVersionSerializer.Meta.fields + ["sheet_counts", "review_status_counts"]
        read_only_fields = fields

    def get_sheet_counts(self, obj):
        return {
            r["sheet_name"]: r["count"]
            for r in obj.rows.order_by("sheet_name")
            .values("sheet_name")
            .annotate(count=Count("id"))
        }

    def get_review_status_counts(self, obj):
        return {
            r["review_status"]: r["count"]
            for r in obj.rows.order_by("review_status")
            .values("review_status")
            .annotate(count=Count("id"))
        }


class RegisterRowSerializer(serializers.ModelSerializer):
    source = serializers.SerializerMethodField()
    summary = serializers.SerializerMethodField()
    review = serializers.SerializerMethodField()
    warning_count = serializers.SerializerMethodField()
    warning_codes = serializers.SerializerMethodField()

    class Meta:
        model = ReportRegisterRow
        fields = [
            "id",
            "file_version",
            "source",
            "summary",
            "review",
            "warning_count",
            "warning_codes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_source(self, obj):
        return {"file_sha256": obj.register_sha256, "sheet": obj.sheet_name, "row": obj.row_number}

    def get_summary(self, obj):
        return {name: getattr(obj, f"summary_{name}") for name in SUMMARY_FIELDS}

    def get_review(self, obj):
        return {name: getattr(obj, name) for name in REVIEW_FIELDS}

    def get_warning_count(self, obj):
        return len(obj.register_warnings) if isinstance(obj.register_warnings, list) else 0

    def get_warning_codes(self, obj):
        warnings = obj.register_warnings if isinstance(obj.register_warnings, list) else []
        return sorted(
            {w["code"] for w in warnings if isinstance(w, dict) and isinstance(w.get("code"), str)}
        )


class RegisterRowDetailSerializer(RegisterRowSerializer):
    class Meta(RegisterRowSerializer.Meta):
        fields = RegisterRowSerializer.Meta.fields + ["payload"]
        read_only_fields = fields


class RegisterReadOnlyViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAdminRole]
    http_method_names = ["get", "head", "options"]
    pagination_class = StandardPagination
    query_serializer = PageQuery

    def list(self, request, *args, **kwargs):
        # QueryDict's HTML handling otherwise treats explicit empty optional filters as absent.
        query = self.query_serializer(data=dict(request.query_params.items()))
        query.is_valid(raise_exception=True)
        self.validated_query = query.validated_data
        return super().list(request, *args, **kwargs)


class ReportRegisterVersionViewSet(RegisterReadOnlyViewSet):
    def get_queryset(self):
        return (
            ReportRegisterVersion.objects.defer("source_metadata")
            .annotate(row_count=Count("rows"))
            .order_by("id")
        )

    def get_serializer_class(self):
        return (
            RegisterVersionDetailSerializer
            if self.action == "retrieve"
            else RegisterVersionSerializer
        )


class ReportRegisterRowViewSet(RegisterReadOnlyViewSet):
    query_serializer = RowQuery

    def get_queryset(self):
        annotations = {
            f"summary_{name}": F(f"payload__fields__{name}__value") for name in SUMMARY_FIELDS
        }
        qs = ReportRegisterRow.objects.annotate(
            **annotations,
            register_sha256=F("file_version__sha256"),
            register_warnings=F("payload__warnings"),
        ).order_by("file_version_id", "sheet_name", "row_number", "id")
        if self.action != "retrieve":
            qs = qs.defer("payload")
        params = getattr(self, "validated_query", {})
        for name in ("file_version", "sheet_name", "review_status", "ownership", "test_target"):
            if name in params:
                qs = qs.filter(**{name: params[name]})
        if params.get("q"):
            qs = qs.filter(
                reduce(
                    or_,
                    (
                        Q(**{f"payload__fields__{name}__value__icontains": params["q"]})
                        for name in SEARCH_FIELDS
                    ),
                )
            )
        return qs

    def get_serializer_class(self):
        return RegisterRowDetailSerializer if self.action == "retrieve" else RegisterRowSerializer
