from django.db import migrations, models
from pypinyin import lazy_pinyin


def populate_name_pinyin(apps, schema_editor):
    Student = apps.get_model("students", "Student")
    for student in Student.objects.all().only("pk", "name"):
        student.name_pinyin = "".join(lazy_pinyin(student.name)).casefold()
        student.save(update_fields=["name_pinyin"])


class Migration(migrations.Migration):
    dependencies = [("students", "0006_alter_student_options")]

    operations = [
        migrations.AddField(
            model_name="student",
            name="name_pinyin",
            field=models.CharField(blank=True, db_index=True, default="", editable=False, max_length=200, verbose_name="姓名拼音"),
        ),
        migrations.RunPython(populate_name_pinyin, migrations.RunPython.noop),
        migrations.AlterModelOptions(
            name="student",
            options={"ordering": ["name_pinyin", "name", "student_id"], "verbose_name": "学生", "verbose_name_plural": "学生"},
        ),
    ]
