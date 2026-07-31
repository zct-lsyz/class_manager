from django.db import models
from django.utils import timezone

from apps.classes.models import SchoolClass, Semester
from apps.students.models import Student


class BaseModel(models.Model):
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        abstract = True


class ClassroomLayout(BaseModel):
    """教室布局"""
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE,
        related_name="layouts", verbose_name="班级",
    )
    name = models.CharField("布局名称", max_length=100, default="默认布局")
    rows = models.IntegerField("排数", default=8)
    cols = models.IntegerField("每排座位数", default=6)
    seats_per_desk = models.IntegerField("每桌人数", default=1)
    has_middle_aisle = models.BooleanField("中间过道", default=True)
    has_left_aisle = models.BooleanField("左边过道", default=False)
    has_right_aisle = models.BooleanField("右边过道", default=False)
    podium_position = models.CharField(
        "讲台位置", max_length=20,
        choices=[("front", "前方"), ("back", "后方")],
        default="front",
    )
    is_current = models.BooleanField("当前布局", default=True)

    class Meta:
        verbose_name = "教室布局"
        verbose_name_plural = "教室布局"

    def __str__(self):
        return f"{self.name} ({self.rows}x{self.cols})"


class SeatPlan(BaseModel):
    """座位方案"""
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE,
        related_name="seat_plans", verbose_name="班级",
    )
    semester = models.ForeignKey(
        Semester, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="学期",
    )
    layout = models.ForeignKey(
        ClassroomLayout, on_delete=models.SET_NULL,
        null=True, verbose_name="教室布局",
    )
    version = models.CharField("版本号", max_length=50, blank=True, default="")
    reason = models.TextField("调整原因", blank=True, default="")
    is_active = models.BooleanField("当前方案", default=True)

    class Meta:
        verbose_name = "座位方案"
        verbose_name_plural = "座位方案"
        ordering = ["-created_at"]

    def __str__(self):
        return f"座位方案 v{self.version or self.pk} ({self.created_at:%Y-%m-%d})"


class SeatAssignment(BaseModel):
    """学生座位分配"""
    seat_plan = models.ForeignKey(
        SeatPlan, on_delete=models.CASCADE,
        related_name="assignments", verbose_name="座位方案",
    )
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE,
        related_name="seat_assignments", verbose_name="学生",
    )
    row = models.IntegerField("排")
    col = models.IntegerField("列")
    is_locked = models.BooleanField("锁定位置", default=False)

    class Meta:
        verbose_name = "座位分配"
        verbose_name_plural = "座位分配"
        unique_together = ["seat_plan", "row", "col"]

    def __str__(self):
        return f"{self.student.name} - 第{self.row}排第{self.col}列"
