"""Read/write helpers for AppSetting. Code must read tunables through these, not hardcode them."""

from django.core.exceptions import ValidationError

from .defaults import APP_SETTING_DEFAULTS
from .models import AppSetting

_UNSET = object()

_TYPE_CHECKS = {
    "int": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "float": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "bool": lambda v: isinstance(v, bool),
    "str": lambda v: isinstance(v, str),
    "json": lambda v: isinstance(v, (dict, list)),
}


def validate_value(value_type: str, value) -> None:
    if value is None:
        return
    check = _TYPE_CHECKS.get(value_type)
    if check is None:
        raise ValidationError(f"알 수 없는 값 타입: {value_type}")
    if not check(value):
        raise ValidationError(f"값이 타입 '{value_type}'과 맞지 않습니다: {value!r}")


def get_setting(key: str, default=_UNSET):
    """Return the stored value, falling back to the seed default, then `default`."""
    setting = AppSetting.objects.filter(key=key).first()
    if setting is not None:
        return setting.value
    if key in APP_SETTING_DEFAULTS:
        return APP_SETTING_DEFAULTS[key].value
    if default is _UNSET:
        raise KeyError(key)
    return default


def set_setting(key: str, value) -> AppSetting:
    seed = APP_SETTING_DEFAULTS.get(key)
    setting = AppSetting.objects.filter(key=key).first()
    if setting is None:
        if seed is None:
            raise KeyError(f"정의되지 않은 설정 키: {key}")
        setting = AppSetting(
            key=key,
            value_type=seed.value_type,
            group=key.split(".", 1)[0],
            description=seed.description,
        )
    validate_value(setting.value_type, value)
    setting.value = value
    setting.save()
    return setting


def seed_app_settings() -> int:
    """Create missing settings from defaults. Existing values are never overwritten."""
    existing = set(AppSetting.objects.values_list("key", flat=True))
    created = [
        AppSetting(
            key=key,
            value=seed.value,
            value_type=seed.value_type,
            group=key.split(".", 1)[0],
            description=seed.description,
        )
        for key, seed in APP_SETTING_DEFAULTS.items()
        if key not in existing
    ]
    AppSetting.objects.bulk_create(created)
    return len(created)
