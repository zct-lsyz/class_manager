from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models

import apps.students.validators


class Migration(migrations.Migration):

    dependencies = [
        ("students", "0002_student_secondary_contact_student_secondary_phone"),
    ]

    operations = [
        migrations.AlterField(
            model_name="student",
            name="student_id",
            field=models.CharField(max_length=20, unique=True, validators=[apps.students.validators.student_id_validator], verbose_name="学号"),
        ),
        migrations.AlterField(
            model_name="student",
            name="height",
            field=models.IntegerField(blank=True, null=True, validators=[MinValueValidator(50), MaxValueValidator(250)], verbose_name="身高(cm)"),
        ),
        migrations.AlterField(
            model_name="student",
            name="primary_phone",
            field=models.CharField(blank=True, default="", max_length=20, validators=[apps.students.validators.phone_validator], verbose_name="主要联系电话"),
        ),
        migrations.AlterField(
            model_name="student",
            name="secondary_phone",
            field=models.CharField(blank=True, default="", max_length=20, validators=[apps.students.validators.phone_validator], verbose_name="备用联系电话"),
        ),
        migrations.AlterField(
            model_name="guardian",
            name="father_phone",
            field=models.CharField(blank=True, default="", max_length=20, validators=[apps.students.validators.phone_validator], verbose_name="父亲电话"),
        ),
        migrations.AlterField(
            model_name="guardian",
            name="mother_phone",
            field=models.CharField(blank=True, default="", max_length=20, validators=[apps.students.validators.phone_validator], verbose_name="母亲电话"),
        ),
    ]
