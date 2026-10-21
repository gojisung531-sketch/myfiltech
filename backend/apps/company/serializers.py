from rest_framework import serializers

from apps.core.app_settings import get_setting

from .models import Certificate, Company, DeliveryRecord, Product, TestReport


class CompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        exclude = ["source_documents", "created_at"]
        read_only_fields = ["id", "updated_at"]


class TestReportBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = TestReport
        fields = [
            "id",
            "report_no",
            "standard",
            "result_class",
            "issue_date",
            "is_obsolete_standard",
        ]


class DeliveryRecordBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryRecord
        fields = ["id", "delivered_ym", "client", "project_name", "quantity", "notes"]


class ProductSerializer(serializers.ModelSerializer):
    filter_type_label = serializers.CharField(source="get_filter_type_display", read_only=True)
    test_report_count = serializers.IntegerField(source="test_reports.count", read_only=True)

    class Meta:
        model = Product
        exclude = ["created_at"]
        read_only_fields = ["id", "updated_at", "source_document"]


class ProductDetailSerializer(ProductSerializer):
    test_reports = TestReportBriefSerializer(many=True, read_only=True)
    delivery_records = DeliveryRecordBriefSerializer(many=True, read_only=True)


class TestReportSerializer(serializers.ModelSerializer):
    product_model_no = serializers.CharField(
        source="product.model_no", read_only=True, default=None
    )
    standard_family_label = serializers.CharField(
        source="get_standard_family_display", read_only=True
    )

    class Meta:
        model = TestReport
        exclude = ["created_at"]
        read_only_fields = ["id", "updated_at", "source_document"]


class CertificateSerializer(serializers.ModelSerializer):
    cert_type_label = serializers.CharField(source="get_cert_type_display", read_only=True)
    status = serializers.SerializerMethodField()
    status_label = serializers.SerializerMethodField()

    class Meta:
        model = Certificate
        exclude = ["created_at"]
        read_only_fields = ["id", "updated_at", "source_document"]

    def _status(self, obj) -> str:
        return obj.status_on(expiring_days=get_setting("evaluation.cert_expiring_days"))

    def get_status(self, obj) -> str:
        return self._status(obj)

    def get_status_label(self, obj) -> str:
        return Certificate.Status(self._status(obj)).label

    def validate(self, attrs):
        start = attrs.get("valid_from", getattr(self.instance, "valid_from", None))
        end = attrs.get("valid_until", getattr(self.instance, "valid_until", None))
        if start and end and start > end:
            raise serializers.ValidationError(
                {"valid_until": ["유효 종료일이 시작일보다 빠릅니다."]}
            )
        return attrs


class DeliveryRecordSerializer(serializers.ModelSerializer):
    products = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Product.objects.all(), required=False
    )
    plant_type_label = serializers.CharField(source="get_plant_type_display", read_only=True)

    class Meta:
        model = DeliveryRecord
        exclude = ["created_at"]
        read_only_fields = ["id", "updated_at", "source_document"]
