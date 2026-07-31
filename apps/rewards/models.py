from django.db import models
from django.utils import timezone

from apps.classes.models import SchoolClass, Semester
from apps.students.models import Student


class BaseModel(models.Model):
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        abstract = True


class RewardItem(BaseModel):
    """奖励条目（可配置）"""
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE,
        related_name="reward_items", verbose_name="班级",
    )
    name = models.CharField("奖励名称", max_length=100)
    default_points = models.IntegerField("默认加分", default=1)
    category = models.CharField("分类", max_length=50, blank=True, default="")
    is_active = models.BooleanField("启用", default=True)
    sort_order = models.IntegerField("排序", default=0)

    class Meta:
        verbose_name = "奖励条目"
        verbose_name_plural = "奖励条目"
        ordering = ["sort_order"]

    def __str__(self):
        return self.name


class RewardRecord(BaseModel):
    """奖励与表扬记录"""
    RECORD_TYPE_CHOICES = [
        ("reward", "奖励/表扬"),
        ("penalty", "违纪惩罚"),
    ]
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE,
        related_name="reward_records", verbose_name="班级",
    )
    semester = models.ForeignKey(
        Semester, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="学期",
    )
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE,
        related_name="reward_records", verbose_name="学生",
    )
    date = models.DateField("日期", db_index=True)
    record_type = models.CharField(
        "奖惩类型", max_length=20, choices=RECORD_TYPE_CHOICES, default="reward",
    )
    item = models.ForeignKey(
        RewardItem, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="records", verbose_name="奖励条目",
    )
    custom_name = models.CharField("自定义名称", max_length=200, blank=True, default="")
    level = models.CharField(
        "奖励等级", max_length=20,
        choices=[
            ("class", "班级表扬"),
            ("school", "校级荣誉"),
            ("other", "其他"),
        ],
        default="class",
    )
    points = models.IntegerField("加分", default=1)
    description = models.TextField("奖励说明", blank=True, default="")
    certificate_photo = models.FileField(
        "奖状照片", upload_to="rewards/", blank=True,
    )
    is_deleted = models.BooleanField("已删除", default=False)

    class Meta:
        verbose_name = "奖励记录"
        verbose_name_plural = "奖励记录"
        ordering = ["-date"]

    def __str__(self):
        return f"{self.student.name} - {self.item or self.custom_name}"


class PointRecord(BaseModel):
    """积分明细"""
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE,
        related_name="point_records", verbose_name="学生",
    )
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE,
        related_name="point_records", verbose_name="班级",
    )
    semester = models.ForeignKey(
        Semester, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="学期",
    )
    date = models.DateField("日期", db_index=True)
    points = models.IntegerField("分值")
    reason = models.TextField("原因")
    source_type = models.CharField(
        "来源类型", max_length=50,
        choices=[
            ("reward", "奖惩记录"),
            ("classroom_discipline", "课堂纪律扣分"),
            ("dorm_discipline", "宿舍纪律扣分"),
            ("hygiene", "卫生扣分/加分"),
            ("manual", "手工调整"),
        ],
        default="manual",
    )
    source_id = models.IntegerField("来源ID", null=True, blank=True)
    manual_reason = models.TextField("手工调整原因", blank=True, default="")
    is_deleted = models.BooleanField("已删除", default=False)

    class Meta:
        verbose_name = "积分记录"
        verbose_name_plural = "积分记录"
        ordering = ["-date"]
        indexes = [
            models.Index(fields=["student", "semester"]),
        ]

    def __str__(self):
        return f"{self.student.name} {self.points:+d}分 - {self.reason[:30]}"
