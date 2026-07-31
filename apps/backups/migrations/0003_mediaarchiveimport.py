from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("backups", "0002_storagealertrule_mediaarchiveexport"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="MediaArchiveImport",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="创建时间")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="更新时间")),
                ("file_names", models.JSONField(default=list, verbose_name="数据包文件")),
                ("package_count", models.PositiveIntegerField(default=0, verbose_name="数据包数量")),
                ("record_count", models.PositiveIntegerField(default=0, verbose_name="恢复媒体关联数")),
                ("status", models.CharField(choices=[("completed", "导入成功"), ("failed", "导入失败")], default="completed", max_length=20, verbose_name="状态")),
                ("error_message", models.TextField(blank=True, default="", verbose_name="错误信息")),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, verbose_name="操作人")),
            ],
            options={"verbose_name": "媒体数据导入历史", "verbose_name_plural": "媒体数据导入历史", "ordering": ["-created_at"]},
        ),
    ]
