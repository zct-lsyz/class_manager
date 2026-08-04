from datetime import date, datetime, time
from decimal import Decimal

from django.db import models
from django.utils import timezone


def scalar(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        if timezone.is_aware(value):
            value = timezone.localtime(value)
        return value.isoformat()
    if isinstance(value, (date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def object_label(value):
    return str(value) if value is not None else ""


def serialize_instance(instance, fields):
    result = {"id": instance.pk, "display": str(instance)}
    for name in fields:
        field = instance._meta.get_field(name)
        value = getattr(instance, name)
        if isinstance(field, (models.ForeignKey, models.OneToOneField)):
            result[name] = value.pk if value else None
            result[f"{name}_label"] = object_label(value)
        elif isinstance(field, models.ManyToManyField):
            values = list(value.all())
            result[name] = [item.pk for item in values]
            result[f"{name}_labels"] = [object_label(item) for item in values]
        elif isinstance(field, models.FileField):
            result[name] = value.name if value else ""
        else:
            result[name] = scalar(value)
        display_method = getattr(instance, f"get_{name}_display", None)
        if display_method:
            result[f"{name}_display"] = display_method()
    return result


def field_schema(field, required=False):
    if isinstance(field, (models.ForeignKey, models.OneToOneField, models.ManyToManyField)):
        kind = "relation"
    elif isinstance(field, models.BooleanField):
        kind = "boolean"
    elif isinstance(field, models.DateTimeField):
        kind = "datetime"
    elif isinstance(field, models.DateField):
        kind = "date"
    elif isinstance(field, models.TimeField):
        kind = "time"
    elif isinstance(field, (models.IntegerField, models.FloatField, models.DecimalField)):
        kind = "number"
    elif isinstance(field, models.TextField):
        kind = "multiline"
    elif isinstance(field, models.FileField):
        kind = "file"
    else:
        kind = "text"
    choices = [{"value": value, "label": label} for value, label in field.flatchoices] if field.choices else []
    return {
        "name": field.name,
        "label": str(field.verbose_name),
        "type": kind,
        "required": required,
        "read_only": not field.editable,
        "choices": choices,
    }
