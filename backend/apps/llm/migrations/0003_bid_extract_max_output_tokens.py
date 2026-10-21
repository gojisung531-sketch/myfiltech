"""Give bid.extract a 32000-token output budget on existing DBs (specs/07 §3).

Only fills the value when the admin has not set one."""

from django.db import migrations


def forwards(apps, schema_editor):
    LLMSettings = apps.get_model("llm", "LLMSettings")
    for row in LLMSettings.objects.all():
        overrides = dict(row.per_task_overrides or {})
        task = dict(overrides.get("bid.extract") or {})
        if "max_output_tokens" in task:
            continue
        task["max_output_tokens"] = 32000
        overrides["bid.extract"] = task
        row.per_task_overrides = overrides
        row.save(update_fields=["per_task_overrides"])


class Migration(migrations.Migration):
    dependencies = [("llm", "0002_prompttemplate_llmcalllog_and_more")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
