from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _seed_llm_defaults(sender, **kwargs):
    from .defaults import seed_llm_defaults

    seed_llm_defaults()


class LlmConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.llm"
    verbose_name = "LLM"

    def ready(self):
        from . import checks  # noqa: F401  (registers system checks)

        post_migrate.connect(_seed_llm_defaults, sender=self, dispatch_uid="llm_seed_defaults")
