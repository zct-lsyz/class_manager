from django.db import models
from django.utils import timezone

from apps.classes.models import SchoolClass, Semester
from apps.students.models import Student
from apps.homework.models import Subject


class BaseModel(models.Model):
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        abstract = True


class Exam(BaseModel):
    """考试"""
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE,
        related_name="exams", verbose_name="班级",
    )
    semester = models.ForeignKey(
        Semester, on_delete=models.CASCADE,
        related_name="exams", verbose_name="学期",
    )
    name = models.CharField("考试名称", max_length=200)
    exam_type = models.CharField(
        "考试类型", max_length=50,
        choices=[
            ("regular", "常规考试"),
            ("midterm", "期中考试"),
            ("final", "期末考试"),
            ("quiz", "随堂测验"),
            ("mock", "模拟考试"),
            ("other", "其他"),
        ],
        default="regular",
    )
    date = models.DateField("考试日期")
    total_score = models.IntegerField("总分", null=True, blank=True)
    is_published = models.BooleanField("已发布", default=False)
    remarks = models.TextField("备注", blank=True, default="")

    class Meta:
        verbose_name = "考试"
        verbose_name_plural = "考试"
        ordering = ["-date"]

    def __str__(self):
        return f"{self.name} ({self.date})"


class ExamSubject(BaseModel):
    """考试科目及满分"""
    exam = models.ForeignKey(
        Exam, on_delete=models.CASCADE,
        related_name="exam_subjects", verbose_name="考试",
    )
    subject = models.ForeignKey(
        Subject, on_delete=models.CASCADE,
        related_name="exam_subjects", verbose_name="科目",
    )
    full_score = models.IntegerField("满分", default=100)
    sort_order = models.IntegerField("排序", default=0)

    class Meta:
        verbose_name = "考试科目"
        verbose_name_plural = "考试科目"
        unique_together = ["exam", "subject"]
        ordering = ["sort_order"]

    def __str__(self):
        return f"{self.exam.name} - {self.subject.name}"


class Score(BaseModel):
    """学生成绩"""
    STATUS_CHOICES = [
        ("normal", "正常"),
        ("absent", "缺考"),
        ("deferred", "缓考"),
        ("exempted", "免考"),
        ("invalid", "成绩无效"),
        ("other", "其他"),
    ]

    exam = models.ForeignKey(
        Exam, on_delete=models.CASCADE,
        related_name="scores", verbose_name="考试",
    )
    exam_subject = models.ForeignKey(
        ExamSubject, on_delete=models.CASCADE,
        related_name="scores", verbose_name="考试科目",
    )
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE,
        related_name="scores", verbose_name="学生",
    )
    score = models.DecimalField("成绩", max_digits=7, null=True, blank=True, decimal_places=1)
    status = models.CharField(
        "成绩状态", max_length=20, choices=STATUS_CHOICES,
        default="normal",
    )
    rank = models.IntegerField("班级名次", null=True, blank=True)
    remarks = models.TextField("备注", blank=True, default="")

    class Meta:
        verbose_name = "成绩"
        verbose_name_plural = "成绩"
        unique_together = ["exam_subject", "student"]
        indexes = [
            models.Index(fields=["exam", "student"]),
        ]

    def __str__(self):
        return f"{self.student.name} - {self.exam_subject.subject.name}: {self.score or self.get_status_display()}"


class SupportPlan(BaseModel):
    """培优补差计划"""
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE,
        related_name="support_plans", verbose_name="班级",
    )
    semester = models.ForeignKey(
        Semester, on_delete=models.CASCADE,
        related_name="support_plans", verbose_name="学期",
    )
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE,
        related_name="support_plans", verbose_name="学生",
    )
    plan_type = models.CharField(
        "计划类型", max_length=20,
        choices=[("excellent", "培优"), ("remedial", "补差")],
    )
    subject = models.ForeignKey(
        Subject, on_delete=models.CASCADE,
        related_name="support_plans", verbose_name="目标科目",
    )
    target_score = models.IntegerField("目标分数", null=True, blank=True)
    stage_goal = models.TextField("阶段目标", blank=True, default="")
    is_active = models.BooleanField("进行中", default=True)
    start_date = models.DateField("开始日期", auto_now_add=True)
    end_date = models.DateField("结束日期", null=True, blank=True)

    class Meta:
        verbose_name = "培优补差计划"
        verbose_name_plural = "培优补差计划"

    def __str__(self):
        return f"{self.student.name} - {self.get_plan_type_display()}({self.subject.name})"


class SupportFollowUp(BaseModel):
    """培优补差跟进记录"""
    plan = models.ForeignKey(
        SupportPlan, on_delete=models.CASCADE,
        related_name="follow_ups", verbose_name="计划",
    )
    date = models.DateField("跟进日期")
    content = models.TextField("跟进内容")
    effect = models.TextField("效果", blank=True, default="")
    next_step = models.TextField("下一步计划", blank=True, default="")

    class Meta:
        verbose_name = "培优补差跟进"
        verbose_name_plural = "培优补差跟进"
        ordering = ["-date"]

    def __str__(self):
        return f"{self.plan.student.name} - {self.date}"

# ====== AI 成绩分析模型 ======
from apps.scores.ai_models import AIAnalysisConfig, AIAnalysisRecord

