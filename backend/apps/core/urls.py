from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import AppSettingResetView, AppSettingsView, JobViewSet, SystemStatusView

router = SimpleRouter(trailing_slash=False)
router.register("jobs", JobViewSet, basename="job")

urlpatterns = [
    path("system/status", SystemStatusView.as_view(), name="system-status"),
    path("settings/app", AppSettingsView.as_view(), name="app-settings"),
    path("settings/app/<str:key>/reset", AppSettingResetView.as_view(), name="app-setting-reset"),
    *router.urls,
]
