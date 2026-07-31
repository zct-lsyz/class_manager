from django.db import models
from django.utils import timezone

from apps.classes.models import SchoolClass, Semester
from apps.students.models import Student
from apps.dormitory.models import DormRoom


class BaseModel(models.Model):
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        abstract = True


class ConfigurableItem(BaseModel):
    """可配置条目（通用，用于课堂纪律/宿舍纪律等）"""
    MODULE_CHOICES = [
        ("classroom_discipline", "课堂纪律"),
        ("dorm_discipline", "宿舍纪律"),
        ("dorm_hygiene", "宿舍卫生"),
        ("reward", "奖励"),
        ("duty_task", "值日任务"),
        ("homework_status", "作业状态"),
    ]
    SEVERITY_CHOICES = [
        ("mild", "轻微"),
        ("moderate", "一般"),
        ("serious", "严重"),
        ("critical", "非常严重"),
    ]

    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE,
        related_name="configurable_items", verbose_name="班级",
    )
    name = models.CharField("条目名称", max_length=100)
    module = models.CharField("所属模块", max_length=50, choices=MODULE_CHOICES)
    category = models.CharField("分类", max_length=50, blank=True, default="")
    default_severity = models.CharField(
        "默认严重程度", max_length=20,
        choices=SEVERITY_CHOICES, default="moderate",
    )
    default_points = models.IntegerField("默认分值", default=0)
    needs_follow_up = models.BooleanField("需要整改", default=False)
    is_active = models.BooleanField("启用", default=True)
    sort_order = models.IntegerField("排序", default=0)
    description = models.TextField("说明", blank=True, default="")

    class Meta:
        verbose_name = "可配置条目"
        verbose_name_plural = "可配置条目"
        ordering = ["module", "sort_order"]
        indexes = [
            models.Index(fields=["module", "is_active"]),
        ]

    def __str__(self):
        return f"[{self.get_module_display()}] {self.name}"


class ClassroomDisciplineRecord(BaseModel):
    """课堂纪律事件"""
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE,
        related_name="classroom_discipline_records", verbose_name="班级",
    )
    semester = models.ForeignKey(
        Semester, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="学期",
    )
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE,
        related_name="classroom_discipline_records", verbose_name="学生",
    )
    date = models.DateField("日期", db_index=True)
    time = models.TimeField("时间", null=True, blank=True)
    period = models.CharField("节次", max_length=50, blank=True, default="")
    subject = models.CharField("科目", max_length=50, blank=True, default="")
    item = models.ForeignKey(
        ConfigurableItem, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="classroom_discipline_records",
        verbose_name="纪律条目",
    )
    custom_content = models.TextField("自定义内容", blank=True, default="")
    severity = models.CharField(
        "严重程度", max_length=20,
        choices=ConfigurableItem.SEVERITY_CHOICES,
        default="moderate",
    )
    description = models.TextField("事件经过", blank=True, default="")
    action_taken = models.TextField("处理措施", blank=True, default="")
    points_deducted = models.IntegerField("扣分", default=0)
    needs_follow_up = models.BooleanField("需要跟进", default=False)
    follow_up_date = models.DateField("跟进日期", null=True, blank=True)
    follow_up_result = models.TextField("整改结果", blank=True, default="")
    remarks = models.TextField("备注", blank=True, default="")
    is_deleted = models.BooleanField("已删除", default=False)

    class Meta:
        verbose_name = "课堂纪律"
        verbose_name_plural = "课堂纪律"
        ordering = ["-date", "-time"]

    def __str__(self):
        return f"{self.student.name} - {self.date} - {self.item or self.custom_content}"


class DormDisciplineRecord(BaseModel):
    """宿舍纪律事件"""
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE,
        related_name="dorm_discipline_records", verbose_name="班级",
    )
    semester = models.ForeignKey(
        Semester, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="学期",
    )
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE,
        related_name="dorm_discipline_records", verbose_name="学生",
    )
    dorm_room = models.ForeignKey(
        DormRoom, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="discipline_records", verbose_name="宿舍",
    )
    date = models.DateField("日期", db_index=True)
    time = models.TimeField("时间", null=True, blank=True)
    item = models.ForeignKey(
        ConfigurableItem, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="dorm_discipline_records",
        verbose_name="纪律条目",
    )
    custom_content = models.TextField("自定义内容", blank=True, default="")
    severity = models.CharField(
        "严重程度", max_length=20,
        choices=ConfigurableItem.SEVERITY_CHOICES,
        default="moderate",
    )
    description = models.TextField("事件经过", blank=True, default="")
    action_taken = models.TextField("处理措施", blank=True, default="")
    points_deducted = models.IntegerField("扣分", default=0)
    needs_follow_up = models.BooleanField("需要跟进", default=False)
    follow_up_date = models.DateField("跟进日期", null=True, blank=True)
    follow_up_result = models.TextField("整改结果", blank=True, default="")
    remarks = models.TextField("备注", blank=True, default="")
    is_deleted = models.BooleanField("已删除", default=False)

    class Meta:
        verbose_name = "宿舍纪律"
        verbose_name_plural = "宿舍纪律"
        ordering = ["-date", "-time"]

    def __str__(self):
        return f"{self.student.name} - {self.date} - {self.item or self.custom_content}"
