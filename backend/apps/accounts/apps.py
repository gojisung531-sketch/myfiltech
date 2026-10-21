from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _ensure_default_admin(sender, **kwargs):
    from .services import ensure_default_admin

    ensure_default_admin()


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    verbose_name = "계정"

    def ready(self):
        post_migrate.connect(
            _ensure_default_admin, sender=self, dispatch_uid="accounts_ensure_default_admin"
        )
