from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("scores", "0002_aianalysisrecord_aianalysisconfig"),
    ]

    operations = [
        migrations.AddField(
            model_name="exam",
            name="is_deleted",
            field=models.BooleanField(default=False, verbose_name="已删除"),
        ),
        migrations.AddField(
            model_name="score",
            name="is_deleted",
            field=models.BooleanField(default=False, verbose_name="已删除"),
        ),
    ]

