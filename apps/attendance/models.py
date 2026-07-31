from django.db import models
from django.utils import timezone

from apps.classes.models import SchoolClass, Semester
from apps.students.models import Student


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
    leave_proof = models.FileField(
        "请假证明", upload_to="attendance/", blank=True,
    )

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
