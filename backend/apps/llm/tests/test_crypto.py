import pytest
from cryptography.fernet import Fernet
from django.core.exceptions import ImproperlyConfigured

from apps.llm import crypto
from apps.llm.checks import check_field_encryption_key


def test_encrypt_decrypt_roundtrip():
    token = crypto.encrypt("sk-ant-secret-1234")
    assert token != "sk-ant-secret-1234"
    assert crypto.decrypt(token) == "sk-ant-secret-1234"


def test_decrypt_with_other_key_fails(settings):
    token = crypto.encrypt("secret")
    settings.FIELD_ENCRYPTION_KEY = Fernet.generate_key().decode()
    with pytest.raises(crypto.DecryptionError):
        crypto.decrypt(token)


def test_missing_key_derives_in_debug_and_fails_otherwise(settings):
    settings.FIELD_ENCRYPTION_KEY = ""
    settings.DEBUG = True
    assert crypto.decrypt(crypto.encrypt("x")) == "x"
    settings.DEBUG = False
    with pytest.raises(ImproperlyConfigured):
        crypto.encrypt("x")


def test_system_check(settings):
    settings.FIELD_ENCRYPTION_KEY = Fernet.generate_key().decode()
    assert check_field_encryption_key(None) == []
    settings.FIELD_ENCRYPTION_KEY = "not-a-key"
    assert [m.id for m in check_field_encryption_key(None)] == ["llm.E002"]
    settings.FIELD_ENCRYPTION_KEY = ""
    settings.DEBUG = True
    assert [m.id for m in check_field_encryption_key(None)] == ["llm.W001"]
    settings.DEBUG = False
    assert [m.id for m in check_field_encryption_key(None)] == ["llm.E001"]
