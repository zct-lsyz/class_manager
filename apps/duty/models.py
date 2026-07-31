from django.db import models
from django.utils import timezone

from apps.classes.models import SchoolClass, Semester
from apps.students.models import Student


class BaseModel(models.Model):
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        abstract = True


class DutyTask(BaseModel):
    """值日任务（可配置）"""
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE,
        related_name="duty_tasks", verbose_name="班级",
    )
    name = models.CharField("任务名称", max_length=100)
    area = models.CharField("值日区域", max_length=100, blank=True, default="")
    is_active = models.BooleanField("启用", default=True)
    sort_order = models.IntegerField("排序", default=0)

    class Meta:
        verbose_name = "值日任务"
        verbose_name_plural = "值日任务"
        ordering = ["sort_order"]

    def __str__(self):
        return self.name


class DutyGroup(BaseModel):
    """值日小组"""
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE,
        related_name="duty_groups", verbose_name="班级",
    )
    semester = models.ForeignKey(
        Semester, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="学期",
    )
    name = models.CharField("组名", max_length=100)
    leader = models.ForeignKey(
        Student, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="led_duty_groups", verbose_name="组长",
    )
    members = models.ManyToManyField(
        Student, blank=True,
        related_name="duty_groups", verbose_name="成员",
    )
    tasks = models.ManyToManyField(
        DutyTask, blank=True,
        related_name="duty_groups", verbose_name="任务",
    )
    week = models.IntegerField("周次", default=1)
    is_active = models.BooleanField("当前小组", default=True)

    class Meta:
        verbose_name = "值日小组"
        verbose_name_plural = "值日小组"

    def __str__(self):
        return f"{self.name} (第{self.week}周)"


class DutyRecord(BaseModel):
    """值日记录"""
    group = models.ForeignKey(
        DutyGroup, on_delete=models.CASCADE,
        related_name="records", verbose_name="小组",
    )
    date = models.DateField("日期")
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE,
        related_name="duty_records", verbose_name="学生",
    )
    is_completed = models.BooleanField("已完成", default=False)
    is_absent = models.BooleanField("缺岗", default=False)
    evaluation = models.CharField(
        "评价", max_length=20,
        choices=[
            ("excellent", "优秀"),
            ("good", "良好"),
            ("fair", "一般"),
            ("poor", "差"),
        ],
        blank=True, default="",
    )
    remark = models.TextField("备注", blank=True, default="")

    class Meta:
        verbose_name = "值日记录"
        verbose_name_plural = "值日记录"
        unique_together = ["group", "date", "student"]
