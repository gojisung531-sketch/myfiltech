from django.apps import AppConfig


class BidsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.bids"
    verbose_name = "입찰 공고"

    def ready(self):
        from . import tasks  # noqa: F401  (registers job handlers)
