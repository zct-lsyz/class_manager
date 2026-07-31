from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("backups", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="StorageAlertRule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="创建时间")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="更新时间")),
                ("name", models.CharField(max_length=100, verbose_name="提醒名称")),
                ("category", models.CharField(choices=[("disk_free", "服务器剩余空间"), ("dormitory", "宿舍管理照片"), ("rewards", "奖惩照片"), ("activities", "文体活动照片")], max_length=30, verbose_name="提醒项")),
                ("threshold_mb", models.PositiveIntegerField(default=1024, verbose_name="阈值(MB)")),
                ("recipient_emails", models.TextField(verbose_name="收件邮箱")),
                ("is_active", models.BooleanField(default=True, verbose_name="启用")),
                ("last_notified_at", models.DateTimeField(blank=True, null=True, verbose_name="最近提醒时间")),
            ],
            options={"verbose_name": "存储空间提醒", "verbose_name_plural": "存储空间提醒", "ordering": ["category", "pk"]},
        ),
        migrations.CreateModel(
            name="MediaArchiveExport",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="创建时间")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="更新时间")),
                ("modules", models.JSONField(default=list, verbose_name="导出模块")),
                ("file_path", models.CharField(max_length=500, verbose_name="压缩包路径")),
                ("file_size", models.PositiveBigIntegerField(default=0, verbose_name="压缩包大小(bytes)")),
                ("record_count", models.PositiveIntegerField(default=0, verbose_name="媒体关联数")),
                ("cleared_at", models.DateTimeField(blank=True, null=True, verbose_name="清理时间")),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, verbose_name="操作人")),
            ],
            options={"verbose_name": "媒体数据归档", "verbose_name_plural": "媒体数据归档", "ordering": ["-created_at"]},
        ),
    ]
