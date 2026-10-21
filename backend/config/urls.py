from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path

# API routes under /api/ (specs/10-api.md).
urlpatterns = [
    path("api/", include("apps.core.urls")),
    path("api/", include("apps.accounts.urls")),
    path("api/", include("apps.llm.urls")),
    path("api/", include("apps.documents.urls")),
    path("api/", include("apps.company.urls")),
    path("api/", include("apps.bids.urls")),
    path("api/", include("apps.evaluation.urls")),
    path("api/", include("apps.drafts.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
