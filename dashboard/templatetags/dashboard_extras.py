import datetime as dt
from decimal import Decimal

from django import template


register = template.Library()


@register.filter
def field_display(field):
    value = field.value()
    if value in (None, ""):
        return "—"
    if getattr(field.field.widget, "input_type", "") == "checkbox":
        return "Sí" if value else "No"
    if isinstance(value, dt.datetime):
        return value.strftime("%H:%M")
    if isinstance(value, dt.time):
        return value.strftime("%H:%M")
    choices = list(getattr(field.field, "choices", ()) or ())
    for key, label in choices:
        if str(key) == str(value):
            return label
    return value


@register.filter
def get_item(mapping, key):
    return (mapping or {}).get(key)


@register.filter
def minutes_hm(value):
    try:
        minutes = int(value or 0)
    except (TypeError, ValueError):
        return "0 min"
    hours, remainder = divmod(minutes, 60)
    return f"{hours} h {remainder:02d} min" if hours else f"{remainder} min"


@register.filter
def signed(value, digits=2):
    try:
        number = Decimal(str(value or 0))
        return f"{number:+.{int(digits)}f}"
    except Exception:
        return value


@register.filter
def money(value, digits=2):
    try:
        number = Decimal(str(value or 0))
        amount = f"${abs(number):,.{int(digits)}f}"
        return f"-{amount}" if number < 0 else f"+{amount}" if number > 0 else amount
    except Exception:
        return value


@register.filter
def pct(value, goal):
    try:
        return min(max(float(value or 0) / float(goal or 1) * 100, 0), 140)
    except (TypeError, ValueError, ZeroDivisionError):
        return 0


@register.filter
def mul(value, multiplier):
    try:
        return Decimal(str(value or 0)) * Decimal(str(multiplier))
    except Exception:
        return 0


@register.filter
def neg(value):
    try:
        return -Decimal(str(value or 0))
    except Exception:
        return 0


@register.filter
def absnum(value):
    try:
        return abs(Decimal(str(value or 0)))
    except Exception:
        return 0
