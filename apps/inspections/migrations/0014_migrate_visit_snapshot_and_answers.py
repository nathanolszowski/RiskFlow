import copy
import logging

from django.db import migrations

logger = logging.getLogger(__name__)


def _sorted_fields(schema):
    """Fields of a schema in display order, as the legacy skeleton was built from them."""
    fields = []
    for section in schema.get("sections", []):
        for field in section.get("fields", []):
            fields.append(field)
    return fields


def _coerce(field, value):
    """Legacy values were typed by hand in the admin, often as strings ("true", "12"): give them the type of the field."""
    if field.get("type") == "boolean" and isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "oui", "yes", "1"):
            return True
        if lowered in ("false", "non", "no", "0"):
            return False
    if field.get("type") == "number" and isinstance(value, str):
        try:
            number = float(value.replace(",", "."))
            return int(number) if number.is_integer() else number
        except ValueError:
            return value
    return value


def forwards(apps, schema_editor):
    VisitInstance = apps.get_model('inspections', 'VisitInstance')

    for visit in VisitInstance.objects.select_related('template').iterator():
        template = visit.template
        schema = copy.deepcopy(template.schema) if template and isinstance(template.schema, dict) else {}

        # Legacy skeleton: {"template_name", "sections": [{"title", "fields": [{"label", "type", "required", "value"}]}]}
        # It has no ids, but it was built from the template in the same order, so answers are matched by position.
        answers = {}
        data = visit.data if isinstance(visit.data, dict) else {}
        if "answers" in data:
            answers = data["answers"]
        else:
            legacy_values = [
                field.get("value")
                for section in data.get("sections", [])
                for field in section.get("fields", [])
            ]
            schema_fields = _sorted_fields(schema)
            if legacy_values and len(legacy_values) != len(schema_fields):
                logger.warning("Visit %s: legacy answers do not match its template, answers dropped.", visit.pk)
            else:
                for field, value in zip(schema_fields, legacy_values):
                    if value not in (None, ""):
                        answers[field["id"]] = _coerce(field, value)

        visit.template_name = template.name if template else visit.template_name
        visit.instance_schema = schema if not visit.instance_schema else visit.instance_schema
        visit.data = {"answers": answers}
        if visit.current_status == 'VALIDATED' and visit.completed_at is None:
            visit.completed_at = visit.updated_at
        visit.save(update_fields=['template_name', 'instance_schema', 'data', 'completed_at'])


class Migration(migrations.Migration):

    dependencies = [
        ('inspections', '0013_alter_visitinstance_template'),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
