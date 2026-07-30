from django.db import models
from django.utils import timezone


class BaseModel(models.Model):
    """基类模型"""
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        abstract = True


class SchoolClass(BaseModel):
    """班级"""
    name = models.CharField("班级名称", max_length=100)
    grade = models.CharField("年级", max_length=50, blank=True, default="")
    school_name = models.CharField("学校名称", max_length=200, blank=True, default="")
    head_teacher = models.CharField("班主任", max_length=50, blank=True, default="")
    classroom_name = models.CharField("教室名称", max_length=100, blank=True, default="")
    is_current = models.BooleanField("当前班级", default=True)
    sort_order = models.IntegerField("排序", default=0)

    class Meta:
        verbose_name = "班级"
        verbose_name_plural = "班级"
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class Semester(BaseModel):
    """学年与学期"""
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE,
        related_name="semesters", verbose_name="班级",
    )
    academic_year = models.CharField("学年", max_length=20, help_text="例如：2026-2027")
    semester_type = models.CharField(
        "学期",
        max_length=10,
        choices=[
            ("first", "第一学期"),
            ("second", "第二学期"),
        ],
    )
    is_current = models.BooleanField("当前学期", default=False)
    is_archived = models.BooleanField("已归档", default=False)
    start_date = models.DateField("开始日期", null=True, blank=True)
    end_date = models.DateField("结束日期", null=True, blank=True)

    class Meta:
        verbose_name = "学期"
        verbose_name_plural = "学期"
        ordering = ["-academic_year", "-semester_type"]
        unique_together = ["school_class", "academic_year", "semester_type"]

    def get_display_name(self):
        semester_display = dict(self._meta.get_field("semester_type").choices).get(
            self.semester_type, self.semester_type
        )
        return f"{self.academic_year}学年 {semester_display}"

    def __str__(self):
        return f"{self.school_class.name} - {self.get_display_name()}"
