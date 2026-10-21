from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import (
    DocumentMetadataViewSet,
    DocumentViewSet,
    LoadInitialDataView,
    MetadataSchemaViewSet,
)

router = SimpleRouter(trailing_slash=False)
router.register("documents", DocumentViewSet, basename="document")
router.register(
    r"documents/(?P<document_pk>\d+)/metadata",
    DocumentMetadataViewSet,
    basename="document-metadata",
)
router.register("metadata-schemas", MetadataSchemaViewSet, basename="metadata-schema")

urlpatterns = [
    path("admin/load-initial-data", LoadInitialDataView.as_view(), name="load-initial-data"),
    *router.urls,
]
