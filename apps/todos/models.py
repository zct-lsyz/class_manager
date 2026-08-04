from django.conf import settings
from django.db import models

from apps.classes.models import SchoolClass
from apps.students.models import Student


class BaseModel(models.Model):
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        abstract = True


class TodoItem(BaseModel):
    """待办事项"""
    PRIORITY_CHOICES = [
        (1, "高"),
        (2, "中"),
        (3, "低"),
    ]
    PRIORITY_COLORS = {
        1: "#dc3545",
        2: "#f57c00",
        3: "#6c757d",
    }

    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE,
        related_name="todos", verbose_name="班级",
        null=True, blank=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="todos", verbose_name="创建人",
    )
    title = models.CharField("标题", max_length=200)
    priority = models.IntegerField(
        "优先级", choices=PRIORITY_CHOICES, default=2,
    )
    deadline = models.DateTimeField("截止时间", null=True, blank=True)
    student = models.ForeignKey(
        Student, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="todos", verbose_name="关联学生",
    )
    is_completed = models.BooleanField("已完成", default=False)
    completed_at = models.DateTimeField("完成时间", null=True, blank=True)
    is_deleted = models.BooleanField("已删除", default=False)
    source_type = models.CharField("来源类型", max_length=50, blank=True, default="")
    source_id = models.CharField("来源ID", max_length=50, blank=True, default="")

    class Meta:
        verbose_name = "待办事项"
        verbose_name_plural = "待办事项"
        ordering = ["is_completed", "priority", "deadline", "-created_at"]

    @property
    def priority_color(self):
        return self.PRIORITY_COLORS.get(self.priority, "#6c757d")

    @property
    def priority_label(self):
        return dict(self.PRIORITY_CHOICES).get(self.priority, "中")

    @property
    def is_overdue(self):
        if self.is_completed or not self.deadline:
            return False
        from django.utils import timezone
        return timezone.now() > self.deadline

    def __str__(self):
        return self.title
