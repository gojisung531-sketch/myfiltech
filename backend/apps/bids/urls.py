from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import (
    AttachmentViewSet,
    BidItemViewSet,
    BidRequirementViewSet,
    BidViewSet,
    DashboardSummaryView,
)

router = SimpleRouter(trailing_slash=False)
router.register("bids", BidViewSet, basename="bid")
router.register(r"bids/(?P<bid_pk>\d+)/attachments", AttachmentViewSet, basename="bid-attachment")
router.register(r"bids/(?P<bid_pk>\d+)/items", BidItemViewSet, basename="bid-item")
router.register(
    r"bids/(?P<bid_pk>\d+)/requirements", BidRequirementViewSet, basename="bid-requirement"
)

urlpatterns = [
    path("dashboard/summary", DashboardSummaryView.as_view(), name="dashboard-summary"),
    *router.urls,
]
