from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _seed_settings(sender, **kwargs):
    from .app_settings import seed_app_settings

    seed_app_settings()


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    verbose_name = "공통"

    def ready(self):
        post_migrate.connect(_seed_settings, sender=self, dispatch_uid="core_seed_app_settings")
