from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import (
    CertificateViewSet,
    CompanyView,
    DeliveryRecordViewSet,
    ProductViewSet,
    TestReportViewSet,
)

router = SimpleRouter(trailing_slash=False)
router.register("products", ProductViewSet, basename="product")
router.register("test-reports", TestReportViewSet, basename="test-report")
router.register("certificates", CertificateViewSet, basename="certificate")
router.register("delivery-records", DeliveryRecordViewSet, basename="delivery-record")

urlpatterns = [
    path("company", CompanyView.as_view(), name="company"),
    *router.urls,
]
