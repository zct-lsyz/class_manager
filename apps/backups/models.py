from django.db import models
from django.utils import timezone

from apps.classes.models import SchoolClass
from django.conf import settings


class BaseModel(models.Model):
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        abstract = True


class BackupRecord(BaseModel):
    """备份记录"""
    BACKUP_TYPES = [
        ("manual", "手动备份"),
        ("auto_daily", "每日自动备份"),
        ("auto_weekly", "每周自动备份"),
        ("auto_monthly", "每月自动备份"),
        ("pre_restore", "恢复前安全备份"),
    ]
    BACKUP_STATUS = [
        ("running", "进行中"),
        ("completed", "已完成"),
        ("failed", "失败"),
    ]

    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="班级",
    )
    backup_type = models.CharField(
        "备份类型", max_length=30, choices=BACKUP_TYPES,
    )
    status = models.CharField(
        "状态", max_length=20, choices=BACKUP_STATUS,
        default="running",
    )
    file_path = models.CharField("文件路径", max_length=500, blank=True, default="")
    file_size = models.IntegerField("文件大小(bytes)", null=True, blank=True)
    checksum = models.CharField("SHA-256 校验值", max_length=128, blank=True, default="")
    db_path = models.CharField("数据库文件", max_length=500, blank=True, default="")
    version_info = models.CharField("系统版本", max_length=100, blank=True, default="")
    migration_version = models.CharField("迁移版本", max_length=100, blank=True, default="")
    record_count = models.IntegerField("学生数", null=True, blank=True)
    exam_count = models.IntegerField("考试数", null=True, blank=True)
    attachment_count = models.IntegerField("附件数", null=True, blank=True)
    downloaded = models.BooleanField("已下载到本地", default=False)
    error_message = models.TextField("错误信息", blank=True, default="")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="操作人",
    )

    class Meta:
        verbose_name = "备份记录"
        verbose_name_plural = "备份记录"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_backup_type_display()} ({self.created_at:%Y-%m-%d %H:%M}) - {self.get_status_display()}"
