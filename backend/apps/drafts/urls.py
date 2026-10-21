from django.urls import path

from .views import (
    BidReportPdfView,
    DraftDetailView,
    DraftGenerateView,
    DraftListView,
    DraftPdfView,
    DraftVersionsView,
    DraftXlsxView,
)

urlpatterns = [
    path("bids/<int:bid_pk>/drafts", DraftListView.as_view(), name="drafts"),
    path("bids/<int:bid_pk>/drafts/<str:doc_type>", DraftDetailView.as_view(), name="draft"),
    path(
        "bids/<int:bid_pk>/drafts/<str:doc_type>/generate",
        DraftGenerateView.as_view(),
        name="draft-generate",
    ),
    path(
        "bids/<int:bid_pk>/drafts/<str:doc_type>/versions",
        DraftVersionsView.as_view(),
        name="draft-versions",
    ),
    path("bids/<int:bid_pk>/drafts/<str:doc_type>/pdf", DraftPdfView.as_view(), name="draft-pdf"),
    path(
        "bids/<int:bid_pk>/drafts/<str:doc_type>/xlsx", DraftXlsxView.as_view(), name="draft-xlsx"
    ),
    path("bids/<int:bid_pk>/report.pdf", BidReportPdfView.as_view(), name="bid-report-pdf"),
]
