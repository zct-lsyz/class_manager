from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator
from django.utils import timezone

from apps.classes.models import SchoolClass
from apps.students.validators import phone_validator, student_id_validator


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
    student_id = models.CharField("学号", max_length=20, unique=True, validators=[student_id_validator])
    name = models.CharField("姓名", max_length=50)
    gender = models.CharField("性别", max_length=10, choices=GENDER_CHOICES)
    birth_date = models.DateField("出生日期", null=True, blank=True)
    height = models.IntegerField("身高(cm)", null=True, blank=True, validators=[MinValueValidator(50), MaxValueValidator(250)])
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
        "主要联系电话", max_length=20, blank=True, default="", validators=[phone_validator]
    )
    secondary_contact = models.CharField(
        "备用联系人", max_length=50, blank=True, default=""
    )
    secondary_phone = models.CharField(
        "备用联系电话", max_length=20, blank=True, default="", validators=[phone_validator]
    )
    remarks = models.TextField("备注", blank=True, default="")
    sort_order = models.IntegerField("排序", default=0)

    class Meta:
        verbose_name = "学生"
        verbose_name_plural = "学生"
        ordering = ["sort_order", "student_id"]

    def __str__(self):
        return f"{self.name} ({self.student_id})"

    @property
    def display_class_position(self):
        if not self.pk:
            return self.class_position
        roles = self.committee_memberships.filter(
            is_active=True, role__is_active=True,
        ).select_related("role").values_list("role__name", flat=True)
        return "、".join(roles) or self.class_position

    @property
    def current_dorm_assignment(self):
        if not self.pk:
            return None
        return self.dorm_assignments.filter(is_current=True).select_related(
            "room__building", "bed",
        ).first()

    @property
    def display_dormitory(self):
        assignment = self.current_dorm_assignment
        return str(assignment.room) if assignment else self.dormitory

    @property
    def display_bed_number(self):
        assignment = self.current_dorm_assignment
        return assignment.bed.bed_number if assignment and assignment.bed else self.bed_number

    @property
    def display_primary_contact(self):
        if not self.pk:
            return self.primary_contact
        guardian = Guardian.objects.filter(student=self, is_deleted=False).first()
        if not guardian:
            return self.primary_contact
        names = {
            "father": guardian.father_name or "父亲",
            "mother": guardian.mother_name or "母亲",
            "other": guardian.other_guardian or "其他监护人",
        }
        return names.get(guardian.primary_contact, self.primary_contact)

    @property
    def display_primary_phone(self):
        if not self.pk:
            return self.primary_phone
        guardian = Guardian.objects.filter(student=self, is_deleted=False).first()
        if not guardian:
            return self.primary_phone
        phones = {
            "father": guardian.father_phone,
            "mother": guardian.mother_phone,
        }
        return phones.get(guardian.primary_contact, "") or self.primary_phone


class Guardian(BaseModel):
    """家长/监护人联系方式"""
    student = models.OneToOneField(
        Student, on_delete=models.CASCADE,
        related_name="guardian", verbose_name="学生",
    )
    father_name = models.CharField("父亲姓名", max_length=50, blank=True, default="")
    father_phone = models.CharField("父亲电话", max_length=20, blank=True, default="", validators=[phone_validator])
    mother_name = models.CharField("母亲姓名", max_length=50, blank=True, default="")
    mother_phone = models.CharField("母亲电话", max_length=20, blank=True, default="", validators=[phone_validator])
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

    def get_primary_contact_display(self):
        return {
            "father": "父亲",
            "mother": "母亲",
            "other": "其他监护人",
        }.get(self.primary_contact, "未设置")
