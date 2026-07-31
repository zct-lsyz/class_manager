from django.db import models
from django.utils import timezone

from apps.classes.models import SchoolClass, Semester
from apps.students.models import Student


class BaseModel(models.Model):
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        abstract = True


class StudentConversation(BaseModel):
    """学生谈话记录"""
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE,
        related_name="conversations", verbose_name="班级",
    )
    semester = models.ForeignKey(
        Semester, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="学期",
    )
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE,
        related_name="conversations", verbose_name="学生",
    )
    date = models.DateField("日期")
    location = models.CharField("地点", max_length=100, blank=True, default="")
    reason = models.TextField("谈话原因", blank=True, default="")
    main_content = models.TextField("主要内容", blank=True, default="")
    student_feedback = models.TextField("学生反馈", blank=True, default="")
    follow_up_actions = models.TextField("后续措施", blank=True, default="")
    follow_up_date = models.DateField("跟进日期", null=True, blank=True)
    is_private = models.BooleanField("私密", default=False)
    is_deleted = models.BooleanField("已删除", default=False)

    class Meta:
        verbose_name = "学生谈话"
        verbose_name_plural = "学生谈话"
        ordering = ["-date"]

    def __str__(self):
        return f"{self.student.name} - {self.date}"


class HomeSchoolContact(BaseModel):
    """家校沟通记录"""
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE,
        related_name="home_school_contacts", verbose_name="班级",
    )
    semester = models.ForeignKey(
        Semester, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="学期",
    )
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE,
        related_name="home_school_contacts", verbose_name="学生",
    )
    contact_date = models.DateField("联系日期")
    contact_person = models.CharField("联系对象", max_length=100, blank=True, default="")
    contact_method = models.CharField(
        "联系方式", max_length=50,
        choices=[
            ("phone", "电话"),
            ("wechat", "微信"),
            ("in_person", "面谈"),
            ("online", "线上"),
            ("other", "其他"),
        ],
        default="phone",
    )
    reason = models.TextField("联系原因", blank=True, default="")
    summary = models.TextField("沟通摘要", blank=True, default="")
    parent_feedback = models.TextField("家长反馈", blank=True, default="")
    follow_up_items = models.TextField("后续事项", blank=True, default="")
    follow_up_date = models.DateField("跟进日期", null=True, blank=True)
    is_private = models.BooleanField("私密", default=False)
    is_deleted = models.BooleanField("已删除", default=False)

    class Meta:
        verbose_name = "家校沟通"
        verbose_name_plural = "家校沟通"
        ordering = ["-contact_date"]

    def __str__(self):
        return f"{self.student.name} - {self.contact_date}"


class ConcernRecord(BaseModel):
    """重点关注"""
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE,
        related_name="concern_records", verbose_name="班级",
    )
    semester = models.ForeignKey(
        Semester, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="学期",
    )
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE,
        related_name="concern_records", verbose_name="学生",
    )
    concern_type = models.CharField(
        "关注类型", max_length=50,
        choices=[
            ("academic", "学业"),
            ("psychological", "心理"),
            ("behavior", "行为"),
            ("family", "家庭"),
            ("health", "健康"),
            ("other", "其他"),
        ],
        default="other",
    )
    level = models.CharField(
        "关注等级", max_length=20,
        choices=[
            ("mild", "一般关注"),
            ("moderate", "重点关注"),
            ("serious", "高度关注"),
        ],
        default="mild",
    )
    observation = models.TextField("观察记录", blank=True, default="")
    conversation_notes = models.TextField("谈话记录", blank=True, default="")
    action_plan = models.TextField("后续计划", blank=True, default="")
    next_follow_up = models.DateField("下次跟进时间", null=True, blank=True)
    status = models.CharField(
        "状态", max_length=20,
        choices=[
            ("active", "关注中"),
            ("improving", "好转中"),
            ("resolved", "已结束"),
        ],
        default="active",
    )
    is_private = models.BooleanField("私密", default=True)
    end_date = models.DateField("结束关注日期", null=True, blank=True)

    class Meta:
        verbose_name = "重点关注"
        verbose_name_plural = "重点关注"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.student.name} - {self.get_concern_type_display()}"
