from django import template

register = template.Library()


@register.filter
def get_item(mapping, key):
    return (mapping or {}).get(key)


@register.filter
def krw(value):
    return f"{int(value):,}원" if isinstance(value, (int, float)) else "-"
