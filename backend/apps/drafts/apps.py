from django.apps import AppConfig


class DraftsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.drafts"
    verbose_name = "초안"

    def ready(self):
        from . import tasks  # noqa: F401  (registers job handlers)
