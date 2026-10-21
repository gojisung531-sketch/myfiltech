from django.apps import AppConfig


class EvaluationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.evaluation"
    verbose_name = "판정"

    def ready(self):
        from . import tasks  # noqa: F401  (registers job handlers)
