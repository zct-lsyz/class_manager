from django.db import models
from django.utils import timezone

from apps.classes.models import SchoolClass


class BaseModel(models.Model):
    """基类模型"""
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)
    is_deleted = models.BooleanField("已删除", default=False)
    deleted_at = models.DateTimeField("删除时间", null=True, blank=True)

    class Meta:
        abstract = True

    def soft_delete(self):
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=["is_deleted", "deleted_at"])

    def restore(self):
        self.is_deleted = False
        self.deleted_at = None
        self.save(update_fields=["is_deleted", "deleted_at"])


class Student(BaseModel):
    """学生基本信息"""
    GENDER_CHOICES = [
        ("male", "男"),
        ("female", "女"),
    ]

    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="students", verbose_name="班级",
    )
    student_id = models.CharField("学号", max_length=20, unique=True)
    name = models.CharField("姓名", max_length=50)
    gender = models.CharField("性别", max_length=10, choices=GENDER_CHOICES)
    birth_date = models.DateField("出生日期", null=True, blank=True)
    height = models.IntegerField("身高(cm)", null=True, blank=True)
    vision = models.CharField("视力情况", max_length=100, blank=True, default="")
    seat_requirement = models.CharField(
        "特殊座位需求", max_length=200, blank=True, default=""
    )
    class_position = models.CharField(
        "班级职务", max_length=100, blank=True, default=""
    )
    dormitory = models.CharField("宿舍", max_length=100, blank=True, default="")
    bed_number = models.CharField("床位", max_length=50, blank=True, default="")
    primary_contact = models.CharField(
        "主要联系人", max_length=50, blank=True, default=""
    )
    primary_phone = models.CharField(
        "主要联系电话", max_length=20, blank=True, default=""
    )
    remarks = models.TextField("备注", blank=True, default="")
    sort_order = models.IntegerField("排序", default=0)

    class Meta:
        verbose_name = "学生"
        verbose_name_plural = "学生"
        ordering = ["sort_order", "student_id"]

    def __str__(self):
        return f"{self.name} ({self.student_id})"


class Guardian(BaseModel):
    """家长/监护人联系方式"""
    student = models.OneToOneField(
        Student, on_delete=models.CASCADE,
        related_name="guardian", verbose_name="学生",
    )
    father_name = models.CharField("父亲姓名", max_length=50, blank=True, default="")
    father_phone = models.CharField("父亲电话", max_length=20, blank=True, default="")
    mother_name = models.CharField("母亲姓名", max_length=50, blank=True, default="")
    mother_phone = models.CharField("母亲电话", max_length=20, blank=True, default="")
    other_guardian = models.CharField(
        "其他监护人", max_length=50, blank=True, default=""
    )
    primary_contact = models.CharField(
        "主要联系人", max_length=50, blank=True, default=""
    )
    home_address = models.TextField("家庭地址", blank=True, default="")
    remarks = models.TextField("备注", blank=True, default="")

    class Meta:
        verbose_name = "家长联系方式"
        verbose_name_plural = "家长联系方式"

    def __str__(self):
        return f"{self.student.name} 的家长信息"
