from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("dormitory", "0002_dormhygienecheck_is_deleted"),
    ]

    operations = [
        migrations.CreateModel(
            name="DormHygienePhoto",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="创建时间")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="更新时间")),
                ("image", models.ImageField(upload_to="hygiene/%Y/%m/", verbose_name="现场照片")),
                ("original_name", models.CharField(blank=True, default="", max_length=255, verbose_name="原文件名")),
                ("original_size", models.PositiveBigIntegerField(default=0, verbose_name="原文件大小(bytes)")),
                ("stored_size", models.PositiveBigIntegerField(default=0, verbose_name="存储大小(bytes)")),
                ("check_record", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="photos", to="dormitory.dormhygienecheck", verbose_name="检查记录")),
            ],
            options={
                "verbose_name": "卫生检查照片",
                "verbose_name_plural": "卫生检查照片",
                "ordering": ["pk"],
            },
        ),
    ]
