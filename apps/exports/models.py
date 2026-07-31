from django.db import models
from django.utils import timezone

from apps.classes.models import SchoolClass
from django.conf import settings


class BaseModel(models.Model):
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        abstract = True


class ExportTask(BaseModel):
    """导出任务"""
    EXPORT_FORMATS = [
        ("xlsx", "Excel"),
        ("csv", "CSV"),
        ("pdf", "PDF"),
        ("json", "JSON"),
        ("zip", "ZIP"),
    ]
    EXPORT_STATUS = [
        ("pending", "等待中"),
        ("processing", "处理中"),
        ("completed", "已完成"),
        ("failed", "失败"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, verbose_name="导出人",
    )
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE,
        related_name="export_tasks", verbose_name="班级",
    )
    module = models.CharField("导出模块", max_length=50)
    export_format = models.CharField(
        "导出格式", max_length=10, choices=EXPORT_FORMATS,
        default="xlsx",
    )
    status = models.CharField(
        "状态", max_length=20, choices=EXPORT_STATUS,
        default="pending",
    )
    file_path = models.CharField("文件路径", max_length=500, blank=True, default="")
    file_size = models.IntegerField("文件大小(bytes)", null=True, blank=True)
    record_count = models.IntegerField("记录数", null=True, blank=True)
    is_full_export = models.BooleanField("是否全量导出", default=False)
    include_sensitive = models.BooleanField("包含敏感数据", default=False)
    include_attachments = models.BooleanField("包含附件", default=False)
    error_message = models.TextField("错误信息", blank=True, default="")
    filters = models.JSONField("筛选条件", blank=True, default=dict)

    class Meta:
        verbose_name = "导出任务"
        verbose_name_plural = "导出任务"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.module} ({self.created_at:%Y-%m-%d %H:%M})"
