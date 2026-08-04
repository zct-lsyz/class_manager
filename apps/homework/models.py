from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.classes.models import SchoolClass, Semester
from apps.students.models import Student


class BaseModel(models.Model):
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        abstract = True


class Subject(BaseModel):
    """科目"""
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        null=True, blank=True,
        related_name="subjects", verbose_name="创建者",
    )
    name = models.CharField("科目名称", max_length=50)
    short_name = models.CharField("简称", max_length=20, blank=True, default="")
    is_active = models.BooleanField("启用", default=True)
    sort_order = models.IntegerField("排序", default=0)

    class Meta:
        verbose_name = "科目"
        verbose_name_plural = "科目"
        ordering = ["sort_order"]

    def __str__(self):
        return self.name


class HomeworkStatus(BaseModel):
    """作业状态（可配置）"""
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE,
        related_name="homework_statuses", verbose_name="班级",
    )
    name = models.CharField("状态名称", max_length=50)
    is_positive = models.BooleanField("积极状态", default=False)
    is_active = models.BooleanField("启用", default=True)
    sort_order = models.IntegerField("排序", default=0)

    class Meta:
        verbose_name = "作业状态"
        verbose_name_plural = "作业状态"
        ordering = ["sort_order"]

    def __str__(self):
        return self.name


class HomeworkTask(BaseModel):
    """作业任务"""
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE,
        related_name="homework_tasks", verbose_name="班级",
    )
    semester = models.ForeignKey(
        Semester, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="学期",
    )
    subject = models.ForeignKey(
        Subject, on_delete=models.SET_NULL,
        null=True, verbose_name="科目",
    )
    title = models.CharField("作业名称", max_length=200)
    content = models.TextField("作业内容", blank=True, default="")
    assigned_date = models.DateField("布置日期")
    due_date = models.DateField("截止日期", null=True, blank=True)
    person_in_charge = models.CharField("负责人", max_length=50, blank=True, default="")
    remarks = models.TextField("备注", blank=True, default="")
    needs_follow_up = models.BooleanField("需要跟进", default=False)
    follow_up_date = models.DateField("跟进日期", null=True, blank=True)

    class Meta:
        verbose_name = "作业任务"
        verbose_name_plural = "作业任务"
        ordering = ["-assigned_date"]

    def __str__(self):
        return self.title


class HomeworkPointRule(BaseModel):
    """作业状态积分规则（可配置，按班级）：为某完成状态自定义加分/扣分。"""
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE,
        related_name="homework_point_rules", verbose_name="班级",
    )
    status = models.CharField("完成状态", max_length=30)
    points = models.PositiveIntegerField("分值（恒为正）", default=0)
    is_add = models.BooleanField("加分", default=True)  # False 表示扣分

    class Meta:
        verbose_name = "作业状态积分规则"
        verbose_name_plural = "作业状态积分规则"
        ordering = ["status"]
        unique_together = ["school_class", "status"]

    @property
    def signed_points(self):
        return self.points if self.is_add else -self.points

    def __str__(self):
        return f"{self.get_status_display_name()}：{self.signed_points:+d}"

    def get_status_display_name(self):
        return dict(HomeworkRecord.STATUS_CHOICES).get(self.status, self.status)


class HomeworkRecord(BaseModel):
    """学生作业完成状态"""
    STATUS_CHOICES = [
        ("submitted", "已交"),
        ("unsubmitted", "未交"),
        ("late", "迟交"),
        ("resubmitted", "补交"),
        ("needs_correction", "需订正"),
        ("corrected", "已订正"),
        ("excellent", "优秀"),
        ("poor", "差"),
        ("exempted", "免交"),
        ("other", "其他"),
    ]
    task = models.ForeignKey(
        HomeworkTask, on_delete=models.CASCADE,
        related_name="records", verbose_name="作业任务",
    )
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE,
        related_name="homework_records", verbose_name="学生",
    )
    status = models.CharField(
        "完成状态", max_length=30,
        choices=STATUS_CHOICES,
        default="submitted",
    )
    submission_date = models.DateField("提交日期", null=True, blank=True)
    correction_deadline = models.DateField("补交期限", null=True, blank=True)
    correction_result = models.CharField("补交结果", max_length=200, blank=True, default="")
    remark = models.TextField("备注", blank=True, default="")

    class Meta:
        verbose_name = "作业记录"
        verbose_name_plural = "作业记录"
        unique_together = ["task", "student"]

    def __str__(self):
        return f"{self.student.name} - {self.task.title} - {self.status_display}"

    @property
    def status_display(self):
        if self.status.startswith("custom:"):
            status_id = self.status.partition(":")[2]
            custom_status = HomeworkStatus.objects.filter(
                pk=status_id, school_class=self.task.school_class
            ).first()
            return custom_status.name if custom_status else "已停用的自定义状态"
        return dict(self._meta.get_field("status").choices).get(self.status, self.status)
