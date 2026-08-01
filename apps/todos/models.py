from django.conf import settings
from django.db import models

from apps.classes.models import SchoolClass


class BaseModel(models.Model):
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        abstract = True


class TodoItem(BaseModel):
    """待办事项"""
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE,
        related_name="todos", verbose_name="班级",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="todos", verbose_name="创建人",
    )
    title = models.CharField("标题", max_length=200)
    deadline = models.DateTimeField("截止时间", null=True, blank=True)
    is_completed = models.BooleanField("已完成", default=False)
    is_deleted = models.BooleanField("已删除", default=False)

    class Meta:
        verbose_name = "待办事项"
        verbose_name_plural = "待办事项"
        ordering = ["is_completed", "deadline", "-created_at"]

    def __str__(self):
        return self.title
