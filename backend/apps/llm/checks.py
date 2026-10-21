from cryptography.fernet import Fernet
from django.conf import settings
from django.core.checks import Error, Tags, Warning, register


@register(Tags.security)
def check_field_encryption_key(app_configs, **kwargs):
    key = settings.FIELD_ENCRYPTION_KEY
    if not key:
        if settings.DEBUG:
            return [
                Warning(
                    "FIELD_ENCRYPTION_KEY is not set; deriving a key from DJANGO_SECRET_KEY.",
                    hint="Set FIELD_ENCRYPTION_KEY in backend/.env (see backend/.env.example).",
                    id="llm.W001",
                )
            ]
        return [Error("FIELD_ENCRYPTION_KEY is required when DEBUG is off.", id="llm.E001")]
    try:
        Fernet(key.encode())
    except ValueError:
        return [Error("FIELD_ENCRYPTION_KEY is not a valid Fernet key.", id="llm.E002")]
    return []
