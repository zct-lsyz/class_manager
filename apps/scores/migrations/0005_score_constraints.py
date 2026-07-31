from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("scores", "0004_aiexamanalysissource_aiquestionweakness"),
    ]

    operations = [
        migrations.AlterField(
            model_name="examsubject",
            name="full_score",
            field=models.IntegerField(default=100, validators=[MinValueValidator(1)], verbose_name="满分"),
        ),
        migrations.AddConstraint(
            model_name="score",
            constraint=models.CheckConstraint(
                condition=models.Q(("score__gte", 0), ("score__isnull", True), _connector="OR"),
                name="score_non_negative_or_null",
            ),
        ),
    ]
