from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import (
    LLMCallLogViewSet,
    LLMSettingsView,
    ModelOptionViewSet,
    PromptActivateView,
    PromptDetailView,
    PromptListView,
    PromptResetView,
    PromptTestView,
    ProviderConfigView,
    ProviderVerifyView,
)

router = SimpleRouter(trailing_slash=False)
router.register("settings/llm/models", ModelOptionViewSet, basename="llm-model")
router.register("llm-logs", LLMCallLogViewSet, basename="llm-log")

urlpatterns = [
    path("settings/llm", LLMSettingsView.as_view(), name="llm-settings"),
    path(
        "settings/llm/providers/<str:provider>",
        ProviderConfigView.as_view(),
        name="llm-provider",
    ),
    path(
        "settings/llm/providers/<str:provider>/verify",
        ProviderVerifyView.as_view(),
        name="llm-provider-verify",
    ),
    path("settings/prompts", PromptListView.as_view(), name="prompts"),
    path("settings/prompts/<str:key>", PromptDetailView.as_view(), name="prompt"),
    path(
        "settings/prompts/<str:key>/activate", PromptActivateView.as_view(), name="prompt-activate"
    ),
    path("settings/prompts/<str:key>/reset", PromptResetView.as_view(), name="prompt-reset"),
    path("settings/prompts/<str:key>/test", PromptTestView.as_view(), name="prompt-test"),
    *router.urls,
]
