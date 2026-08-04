from django.db import models
from django.utils import timezone

from apps.classes.models import SchoolClass, Semester
from apps.students.models import Student
from django.core.validators import MaxValueValidator, MinValueValidator


class BaseModel(models.Model):
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        abstract = True


class AttendanceRecord(BaseModel):
    """考勤记录"""
    STATUS_CHOICES = [
        ("normal", "正常"),
        ("late", "迟到"),
        ("early_leave", "早退"),
        ("sick", "病假"),
        ("personal", "事假"),
        ("official", "公假"),
        ("absent", "缺勤"),
        ("other", "其他"),
    ]
    PERIOD_CHOICES = [
        ("full_day", "全天"),
        ("morning_reading", "早读"),
        ("morning", "上午"),
        ("afternoon", "下午"),
        ("evening_study", "晚自习"),
    ]

    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE,
        related_name="attendance_records", verbose_name="班级",
    )
    semester = models.ForeignKey(
        Semester, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="学期",
    )
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE,
        related_name="attendance_records", verbose_name="学生",
    )
    date = models.DateField("日期", db_index=True)
    period = models.CharField(
        "时段", max_length=30, choices=PERIOD_CHOICES,
        default="full_day",
    )
    status = models.CharField(
        "状态", max_length=20, choices=STATUS_CHOICES,
        default="normal",
    )
    reason = models.TextField("原因/备注", blank=True, default="")
    points_deducted = models.IntegerField(
        "加减分", default=0,
        help_text="正数加分、负数扣分（如迟到扣1填 -1，全勤奖励加2填 2）",
    )
    leave_proof = models.FileField(
        "请假证明", upload_to="attendance/", blank=True,
    )
    needs_follow_up = models.BooleanField("需要跟进", default=False)
    follow_up_date = models.DateField("跟进日期", null=True, blank=True)

    class Meta:
        verbose_name = "考勤记录"
        verbose_name_plural = "考勤记录"
        ordering = ["-date", "student"]
        indexes = [
            models.Index(fields=["date", "status"]),
            models.Index(fields=["student", "date"]),
        ]

    def __str__(self):
        return f"{self.student.name} - {self.date} - {self.get_status_display()}"


class AttendanceReason(BaseModel):
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE,
        related_name="attendance_reasons", verbose_name="班级",
    )
    name = models.CharField("原因项", max_length=100)
    is_active = models.BooleanField("启用", default=True)
    sort_order = models.IntegerField("排序", default=0)

    class Meta:
        verbose_name = "考勤原因项"
        verbose_name_plural = "考勤原因项"
        ordering = ["sort_order", "pk"]
        unique_together = ["school_class", "name"]


class WarningRule(BaseModel):
    CONTENT_CHOICES = [
        ("attendance", "考勤管理"),
        ("discipline", "课堂纪律"),
        ("homework", "作业检查"),
        ("dormitory", "宿舍管理"),
        ("rewards", "奖惩管理"),
        ("duty", "值日管理"),
    ]
    UNIT_CHOICES = [("count", "次"), ("points", "分")]
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE,
        related_name="warning_rules", verbose_name="班级",
    )
    name = models.CharField("预警名称", max_length=100)
    content = models.CharField("内容", max_length=30, choices=CONTENT_CHOICES)
    unit = models.CharField("单位", max_length=10, choices=UNIT_CHOICES, default="count")
    threshold = models.PositiveSmallIntegerField(
        "数量", default=2, validators=[MinValueValidator(1), MaxValueValidator(20)],
    )
    is_active = models.BooleanField("启用", default=True)

    class Meta:
        verbose_name = "预警条目"
        verbose_name_plural = "预警条目"
        ordering = ["pk"]
