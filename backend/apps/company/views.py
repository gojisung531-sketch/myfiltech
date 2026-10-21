from datetime import timedelta

from django.db.models import Q
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.app_settings import get_setting
from apps.core.permissions import ReadAnyWriteAdmin

from .models import Certificate, Company, DeliveryRecord, Product, TestReport
from .serializers import (
    CertificateSerializer,
    CompanySerializer,
    DeliveryRecordSerializer,
    ProductDetailSerializer,
    ProductSerializer,
    TestReportSerializer,
)


class CompanyView(APIView):
    """GET/PUT /api/company (singleton)."""

    permission_classes = [ReadAnyWriteAdmin]

    def get(self, request):
        return Response(CompanySerializer(Company.load()).data)

    def put(self, request):
        serializer = CompanySerializer(Company.load(), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class CompanyDataViewSet(viewsets.ModelViewSet):
    permission_classes = [ReadAnyWriteAdmin]
    http_method_names = ["get", "post", "patch", "delete"]
    search_fields: tuple[str, ...] = ()

    def get_queryset(self):
        qs = self.queryset.all()
        q = self.request.query_params.get("q")
        if q and self.search_fields:
            condition = Q()
            for name in self.search_fields:
                condition |= Q(**{f"{name}__icontains": q})
            qs = qs.filter(condition)
        return self.filter_queryset_extra(qs, self.request.query_params)

    def filter_queryset_extra(self, qs, params):
        return qs


class ProductViewSet(CompanyDataViewSet):
    queryset = Product.objects.all()
    search_fields = ("model_no", "name", "application")

    def get_serializer_class(self):
        return ProductDetailSerializer if self.action == "retrieve" else ProductSerializer

    def filter_queryset_extra(self, qs, params):
        if params.get("is_active") in ("true", "false"):
            qs = qs.filter(is_active=params["is_active"] == "true")
        if params.get("filter_type"):
            qs = qs.filter(filter_type=params["filter_type"])
        return qs


class TestReportViewSet(CompanyDataViewSet):
    queryset = TestReport.objects.select_related("product")
    serializer_class = TestReportSerializer
    search_fields = ("report_no", "model_no_text", "standard", "result_class")

    def filter_queryset_extra(self, qs, params):
        if params.get("product"):
            qs = qs.filter(product_id=params["product"])
        if params.get("standard_family"):
            qs = qs.filter(standard_family=params["standard_family"])
        return qs


class CertificateViewSet(CompanyDataViewSet):
    queryset = Certificate.objects.all()
    serializer_class = CertificateSerializer
    search_fields = ("cert_no", "name", "standard", "scope")

    def filter_queryset_extra(self, qs, params):
        status = params.get("status")
        if status:
            today = timezone.localdate()
            soon = today + timedelta(days=get_setting("evaluation.cert_expiring_days"))
            filters = {
                "EXPIRED": Q(valid_until__lt=today),
                "EXPIRING": Q(valid_until__gte=today, valid_until__lte=soon),
                "VALID": Q(valid_until__gt=soon),
                "UNKNOWN": Q(valid_until__isnull=True),
            }
            if status in filters:
                qs = qs.filter(filters[status])
        return qs


class DeliveryRecordViewSet(CompanyDataViewSet):
    queryset = DeliveryRecord.objects.prefetch_related("products")
    serializer_class = DeliveryRecordSerializer
    search_fields = ("client", "project_name", "item_desc", "notes")

    def filter_queryset_extra(self, qs, params):
        if params.get("is_power_plant") in ("true", "false"):
            qs = qs.filter(is_power_plant=params["is_power_plant"] == "true")
        if params.get("product"):
            qs = qs.filter(products__id=params["product"])
        return qs
