"""Fernet encryption for LLM API keys (specs/01 §4, §7)."""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class DecryptionError(Exception):
    pass


def _derive_dev_key() -> bytes:
    digest = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    return base64.urlsafe_b64encode(digest)


def get_fernet() -> Fernet:
    key = settings.FIELD_ENCRYPTION_KEY
    if not key:
        if not settings.DEBUG:
            raise ImproperlyConfigured("FIELD_ENCRYPTION_KEY is not set")
        return Fernet(_derive_dev_key())
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt(plaintext: str) -> str:
    return get_fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    try:
        return get_fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise DecryptionError(
            "저장된 API Key를 복호화할 수 없습니다. "
            "FIELD_ENCRYPTION_KEY가 바뀌었다면 Key를 다시 입력하세요."
        ) from exc
