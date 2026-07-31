from django.db import migrations, models
import django.db.models.deletion


def copy_subject_names(apps, schema_editor):
    source_model = apps.get_model("scores", "AIExamAnalysisSource")
    for source in source_model.objects.select_related("exam_subject__subject"):
        if source.exam_subject_id:
            source.subject_name = source.exam_subject.subject.name
            source.save(update_fields=["subject_name"])


class Migration(migrations.Migration):

    dependencies = [
        ("scores", "0005_score_constraints"),
    ]

    operations = [
        migrations.AddField(
            model_name="aiexamanalysissource",
            name="subject_name",
            field=models.CharField(blank=True, default="", max_length=50, verbose_name="科目"),
        ),
        migrations.RunPython(copy_subject_names, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="aiexamanalysissource",
            name="exam_subject",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="ai_exam_analysis_sources", to="scores.examsubject", verbose_name="考试科目"),
        ),
    ]
