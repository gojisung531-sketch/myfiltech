from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _seed_schemas(sender, **kwargs):
    from .defaults import seed_metadata_schemas

    seed_metadata_schemas()


class DocumentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.documents"
    verbose_name = "문서"

    def ready(self):
        from . import tasks  # noqa: F401  (registers job handlers)

        post_migrate.connect(_seed_schemas, sender=self, dispatch_uid="documents_seed_schemas")
