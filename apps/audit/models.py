from django.db import models
from django.conf import settings


class OperationLog(models.Model):
    """操作日志"""
    ACTION_CHOICES = [
        ("login", "登录"),
        ("login_failed", "登录失败"),
        ("logout", "登出"),
        ("create", "新增"),
        ("edit", "编辑"),
        ("delete", "删除"),
        ("batch_import", "批量导入"),
        ("export", "导出"),
        ("full_export", "全量导出"),
        ("backup", "创建备份"),
        ("restore", "恢复备份"),
        ("password_change", "修改密码"),
        ("username_change", "修改用户名"),
        ("archive", "归档"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="用户",
    )
    action = models.CharField("操作类型", max_length=50, choices=ACTION_CHOICES)
    module = models.CharField("所属模块", max_length=50, db_index=True)
    object_repr = models.CharField("操作对象", max_length=200, blank=True, default="")
    detail = models.TextField("操作详情", blank=True, default="")
    ip_address = models.GenericIPAddressField("IP 地址", blank=True, null=True)
    success = models.BooleanField("是否成功", default=True)
    created_at = models.DateTimeField("操作时间", auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "操作日志"
        verbose_name_plural = "操作日志"
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.created_at:%Y-%m-%d %H:%M}] {self.get_action_display()} - {self.module}"


class SoftDeleteRecord(models.Model):
    """回收站记录"""
    model_name = models.CharField("模型名称", max_length=100)
    object_id = models.IntegerField("对象ID")
    object_repr = models.CharField("对象描述", max_length=200)
    module = models.CharField("所属模块", max_length=50)
    serialized_data = models.JSONField("序列化数据", blank=True, default=dict)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, verbose_name="删除人",
    )
    deleted_at = models.DateTimeField("删除时间", auto_now_add=True)
    expires_at = models.DateTimeField("过期时间")
    is_permanently_deleted = models.BooleanField("已永久删除", default=False)

    class Meta:
        verbose_name = "回收站"
        verbose_name_plural = "回收站"
        ordering = ["-deleted_at"]

    def __str__(self):
        return f"{self.object_repr} ({self.deleted_at:%Y-%m-%d})"
