from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dormitory", "0004_dormhygienecheck_follow_up_date_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="dormhygieneitem",
            name="default_severity",
            field=models.CharField(choices=[("mild", "轻微"), ("moderate", "一般"), ("serious", "严重"), ("critical", "非常严重")], default="moderate", max_length=20, verbose_name="默认严重程度"),
        ),
    ]
