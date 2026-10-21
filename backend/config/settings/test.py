from .base import *  # noqa: F403

DEBUG = False

# Faster hashing in tests only.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

MEDIA_ROOT = BACKEND_DIR / ".pytest_media"  # noqa: F405
