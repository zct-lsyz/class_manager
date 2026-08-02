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
            ("attendance", "考勤扣分/加分"),
            ("homework", "作业检查"),
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


class RankingSetting(BaseModel):
    """积分排名设置：选择参与总体积分排名的来源模块。"""
    school_class = models.OneToOneField(
        SchoolClass, on_delete=models.CASCADE,
        related_name="ranking_setting", verbose_name="班级",
    )
    enable_reward = models.BooleanField("奖惩统计", default=True)
    enable_classroom_discipline = models.BooleanField("课堂纪律", default=True)
    enable_dorm_discipline = models.BooleanField("宿舍纪律", default=True)
    enable_hygiene = models.BooleanField("宿舍卫生", default=True)
    enable_attendance = models.BooleanField("考勤管理", default=True)
    enable_homework = models.BooleanField("作业检查", default=True)

    class Meta:
        verbose_name = "积分排名设置"
        verbose_name_plural = "积分排名设置"

    def enabled_source_types(self):
        types = []
        if self.enable_reward:
            types.append("reward")
        if self.enable_classroom_discipline:
            types.append("classroom_discipline")
        if self.enable_dorm_discipline:
            types.append("dorm_discipline")
        if self.enable_hygiene:
            types.append("hygiene")
        if self.enable_attendance:
            types.append("attendance")
        if self.enable_homework:
            types.append("homework")
        return types

    def enabled_labels(self):
        labels = []
        if self.enable_reward:
            labels.append("奖惩统计")
        if self.enable_classroom_discipline:
            labels.append("课堂纪律")
        if self.enable_dorm_discipline:
            labels.append("宿舍纪律")
        if self.enable_hygiene:
            labels.append("宿舍卫生")
        if self.enable_attendance:
            labels.append("考勤管理")
        if self.enable_homework:
            labels.append("作业检查")
        return labels
