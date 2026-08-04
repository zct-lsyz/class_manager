from django.db import models
from django.utils import timezone

from apps.classes.models import SchoolClass
from apps.students.models import Student


class BaseModel(models.Model):
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        abstract = True


class DormBuilding(BaseModel):
    """宿舍楼"""
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE,
        related_name="dorm_buildings", verbose_name="班级",
    )
    name = models.CharField("宿舍楼名称", max_length=100)
    floors = models.IntegerField("楼层数", default=6)
    sort_order = models.IntegerField("排序", default=0)

    class Meta:
        verbose_name = "宿舍楼"
        verbose_name_plural = "宿舍楼"
        ordering = ["sort_order"]

    def __str__(self):
        return self.name


class DormRoom(BaseModel):
    """宿舍"""
    building = models.ForeignKey(
        DormBuilding, on_delete=models.CASCADE,
        related_name="rooms", verbose_name="宿舍楼",
    )
    room_number = models.CharField("宿舍编号", max_length=20)
    floor = models.IntegerField("楼层", default=1)
    room_type = models.CharField(
        "宿舍类型", max_length=50,
        choices=[
            ("standard", "标准间"),
            ("suite", "套间"),
            ("other", "其他"),
        ],
        default="standard",
    )
    bed_count = models.IntegerField("床位数", default=8)
    monitor = models.ForeignKey(
        Student, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="monitored_rooms", verbose_name="宿舍长",
    )
    is_active = models.BooleanField("启用", default=True)
    remarks = models.TextField("备注", blank=True, default="")

    class Meta:
        verbose_name = "宿舍"
        verbose_name_plural = "宿舍"
        ordering = ["building", "floor", "room_number"]
        unique_together = ["building", "room_number"]

    def __str__(self):
        return f"{self.building.name} {self.room_number}"


class DormBed(BaseModel):
    """床位"""
    room = models.ForeignKey(
        DormRoom, on_delete=models.CASCADE,
        related_name="beds", verbose_name="宿舍",
    )
    bed_number = models.CharField("床位编号", max_length=20)
    is_active = models.BooleanField("启用", default=True)

    class Meta:
        verbose_name = "床位"
        verbose_name_plural = "床位"
        ordering = ["room", "bed_number"]
        unique_together = ["room", "bed_number"]

    def __str__(self):
        return f"{self.room.room_number} - {self.bed_number}"


class DormAssignment(BaseModel):
    """学生住宿分配"""
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE,
        related_name="dorm_assignments", verbose_name="学生",
    )
    room = models.ForeignKey(
        DormRoom, on_delete=models.CASCADE,
        related_name="assignments", verbose_name="宿舍",
    )
    bed = models.OneToOneField(
        DormBed, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="assignment", verbose_name="床位",
    )
    semester = models.ForeignKey(
        "classes.Semester", on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="学期",
    )
    is_current = models.BooleanField("当前分配", default=True)
    assigned_date = models.DateField("分配日期", auto_now_add=True)
    end_date = models.DateField("结束日期", null=True, blank=True)

    class Meta:
        verbose_name = "住宿分配"
        verbose_name_plural = "住宿分配"
        indexes = [
            models.Index(fields=["student", "is_current"]),
        ]

    def __str__(self):
        return f"{self.student.name} -> {self.room.room_number}"


class DormHygieneItem(BaseModel):
    """卫生检查项目（可配置）"""
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE,
        related_name="hygiene_items", verbose_name="班级",
    )
    name = models.CharField("项目名称", max_length=100)
    full_score = models.IntegerField("满分", default=10)
    default_deduction = models.IntegerField("默认扣分", default=0)
    is_active = models.BooleanField("启用", default=True)
    sort_order = models.IntegerField("排序", default=0)

    class Meta:
        verbose_name = "卫生项目"
        verbose_name_plural = "卫生项目"
        ordering = ["sort_order"]

    def __str__(self):
        return self.name


class DormHygieneCheck(BaseModel):
    """宿舍卫生检查"""
    room = models.ForeignKey(
        DormRoom, on_delete=models.CASCADE,
        related_name="hygiene_checks", verbose_name="宿舍",
    )
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE,
        related_name="hygiene_checks", verbose_name="班级",
    )
    semester = models.ForeignKey(
        "classes.Semester", on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="学期",
    )
    date = models.DateField("检查日期", db_index=True)
    check_time = models.TimeField("检查时间", null=True, blank=True)
    inspector = models.CharField("检查人", max_length=50, blank=True, default="")
    total_score = models.IntegerField("总分", default=0)
    grade = models.CharField(
        "等级", max_length=20,
        choices=[
            ("excellent", "优秀"),
            ("good", "良好"),
            ("fair", "一般"),
            ("poor", "差"),
            ("needs_improvement", "需整改"),
        ],
        blank=True, default="",
    )
    rectification = models.TextField("整改要求", blank=True, default="")
    rectification_deadline = models.DateField("整改期限", null=True, blank=True)
    rectification_result = models.TextField("整改结果", blank=True, default="")
    needs_follow_up = models.BooleanField("需要跟进", default=False)
    follow_up_date = models.DateField("跟进日期", null=True, blank=True)
    photo = models.FileField("照片", upload_to="hygiene/", blank=True)
    remarks = models.TextField("备注", blank=True, default="")
    is_deleted = models.BooleanField("已删除", default=False)

    class Meta:
        verbose_name = "卫生检查"
        verbose_name_plural = "卫生检查"
        ordering = ["-date"]

    def __str__(self):
        return f"{self.room.room_number} - {self.date} - {self.total_score}分"


class DormHygienePhoto(BaseModel):
    """宿舍卫生检查的多张现场照片。"""
    check_record = models.ForeignKey(
        DormHygieneCheck, on_delete=models.CASCADE,
        related_name="photos", verbose_name="检查记录",
    )
    image = models.ImageField("现场照片", upload_to="hygiene/%Y/%m/")
    original_name = models.CharField("原文件名", max_length=255, blank=True, default="")
    original_size = models.PositiveBigIntegerField("原文件大小(bytes)", default=0)
    stored_size = models.PositiveBigIntegerField("存储大小(bytes)", default=0)

    class Meta:
        verbose_name = "卫生检查照片"
        verbose_name_plural = "卫生检查照片"
        ordering = ["pk"]


class DormHygieneItemScore(BaseModel):
    """卫生检查项目得分"""
    check_record = models.ForeignKey(
        DormHygieneCheck, on_delete=models.CASCADE,
        related_name="item_scores", verbose_name="检查记录",
    )
    item = models.ForeignKey(
        DormHygieneItem, on_delete=models.SET_NULL,
        null=True, verbose_name="检查项目",
    )
    score = models.IntegerField("得分", default=0)
    deduction_reason = models.TextField("扣分原因", blank=True, default="")

    class Meta:
        verbose_name = "卫生项目得分"
        verbose_name_plural = "卫生项目得分"

    def __str__(self):
        return f"{self.item.name}: {self.score}分"
