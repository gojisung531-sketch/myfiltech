"""Give evaluation.judge and draft.* a 32000-token output budget on existing DBs (specs/07 §3).

Only fills the value when the admin has not set one."""

from django.db import migrations

TASKS = ("evaluation.judge", "draft.*")


def forwards(apps, schema_editor):
    LLMSettings = apps.get_model("llm", "LLMSettings")
    for row in LLMSettings.objects.all():
        overrides = dict(row.per_task_overrides or {})
        changed = False
        for key in TASKS:
            task = dict(overrides.get(key) or {})
            if "max_output_tokens" not in task:
                task["max_output_tokens"] = 32000
                overrides[key] = task
                changed = True
        if changed:
            row.per_task_overrides = overrides
            row.save(update_fields=["per_task_overrides"])


class Migration(migrations.Migration):
    dependencies = [("llm", "0003_bid_extract_max_output_tokens")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
