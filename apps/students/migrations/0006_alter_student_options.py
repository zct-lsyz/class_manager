from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("students", "0005_add_home_address_league_boarder"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="student",
            options={"ordering": ["name", "student_id"], "verbose_name": "学生", "verbose_name_plural": "学生"},
        ),
    ]
