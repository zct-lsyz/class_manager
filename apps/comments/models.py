from django.db import models
from django.utils import timezone

from apps.classes.models import SchoolClass, Semester
from apps.students.models import Student


class BaseModel(models.Model):
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        abstract = True


class CommentTemplate(BaseModel):
    """评语模板"""
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE,
        related_name="comment_templates", verbose_name="班级",
    )
    title = models.CharField("模板标题", max_length=200)
    content = models.TextField("模板内容")
    category = models.CharField(
        "分类", max_length=50,
        choices=[
            ("learning", "学习"),
            ("discipline", "纪律"),
            ("labor", "劳动"),
            ("cooperation", "合作"),
            ("talent", "特长"),
            ("comprehensive", "综合"),
        ],
        default="comprehensive",
    )
    is_active = models.BooleanField("启用", default=True)

    class Meta:
        verbose_name = "评语模板"
        verbose_name_plural = "评语模板"

    def __str__(self):
        return self.title


class StudentComment(BaseModel):
    """学生评语"""
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE,
        related_name="comments", verbose_name="班级",
    )
    semester = models.ForeignKey(
        Semester, on_delete=models.CASCADE,
        related_name="comments", verbose_name="学期",
    )
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE,
        related_name="comments", verbose_name="学生",
    )
    comment_type = models.CharField(
        "评语类型", max_length=30,
        choices=[
            ("daily", "日常简评"),
            ("monthly", "月度评语"),
            ("midterm", "期中评语"),
            ("final", "期末评语"),
            ("yearly", "学年评语"),
            ("custom", "自定义"),
        ],
        default="daily",
    )
    content = models.TextField("评语内容", blank=True, default="")
    status = models.CharField(
        "状态", max_length=20,
        choices=[
            ("draft", "草稿"),
            ("pending", "待确认"),
            ("completed", "已完成"),
            ("confirmed", "已确认"),
        ],
        default="draft",
    )
    template = models.ForeignKey(
        CommentTemplate, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="使用的模板",
    )
    is_deleted = models.BooleanField("已删除", default=False)

    class Meta:
        verbose_name = "学生评语"
        verbose_name_plural = "学生评语"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["student", "semester", "comment_type"]),
        ]

    def __str__(self):
        return f"{self.student.name} - {self.get_comment_type_display()}"
