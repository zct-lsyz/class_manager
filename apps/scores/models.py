from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.utils import timezone

from apps.classes.models import SchoolClass, Semester
from apps.students.models import Student
from apps.classes.subjects import Subject


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
    is_deleted = models.BooleanField("已删除", default=False)
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
    full_score = models.IntegerField("满分", default=100, validators=[MinValueValidator(1)])
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
    grade_rank = models.IntegerField("级部/年级名次", null=True, blank=True)
    city_rank = models.IntegerField("市名次", null=True, blank=True)
    remarks = models.TextField("备注", blank=True, default="")
    is_deleted = models.BooleanField("已删除", default=False)

    class Meta:
        verbose_name = "成绩"
        verbose_name_plural = "成绩"
        unique_together = ["exam_subject", "student"]
        indexes = [
            models.Index(fields=["exam", "student"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(score__gte=0) | models.Q(score__isnull=True),
                name="score_non_negative_or_null",
            ),
        ]

    def __str__(self):
        value = self.score if self.score is not None else self.get_status_display()
        return f"{self.student.name} - {self.exam_subject.subject.name}: {value}"

    def clean(self):
        errors = {}
        if self.exam_subject_id and self.exam_id:
            if self.exam_subject.exam_id != self.exam_id:
                errors["exam"] = "考试必须与考试科目所属考试一致。"
        if self.score is not None and self.exam_subject_id:
            if self.score < 0:
                errors["score"] = "成绩不能小于 0。"
            elif self.score > self.exam_subject.full_score:
                errors["score"] = (
                    f"成绩不能超过该科目满分 {self.exam_subject.full_score}。"
                )
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


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


class ExternalClass(BaseModel):
    """外部班级（用于多班成绩对比，导入其他班成绩时创建）"""
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE,
        related_name="external_comparisons", verbose_name="所属班级",
    )
    name = models.CharField("班级名称", max_length=100)
    school_name = models.CharField("学校名称", max_length=200, blank=True, default="")

    class Meta:
        verbose_name = "外部对比班级"
        verbose_name_plural = "外部对比班级"
        ordering = ["school_name", "name"]

    def __str__(self):
        prefix = f"{self.school_name} " if self.school_name else ""
        return f"{prefix}{self.name}"


class ExternalScore(BaseModel):
    """外部班级的单科成绩（脱敏，仅用于统计对比）"""
    external_class = models.ForeignKey(
        ExternalClass, on_delete=models.CASCADE,
        related_name="scores", verbose_name="外部班级",
    )
    exam = models.ForeignKey(
        Exam, on_delete=models.CASCADE,
        related_name="external_scores", verbose_name="考试",
    )
    exam_subject = models.ForeignKey(
        ExamSubject, on_delete=models.CASCADE,
        related_name="external_scores", verbose_name="考试科目",
    )
    student_label = models.CharField("学生标识", max_length=50, blank=True, default="")
    score = models.FloatField("分数", null=True, blank=True)
    class_rank = models.IntegerField("班级名次", null=True, blank=True)
    grade_rank = models.IntegerField("级部名次", null=True, blank=True)
    city_rank = models.IntegerField("市名次", null=True, blank=True)

    class Meta:
        verbose_name = "外部班级成绩"
        verbose_name_plural = "外部班级成绩"
        ordering = ["external_class", "exam_subject", "student_label"]

    def __str__(self):
        return f"{self.external_class} - {self.exam_subject.subject.name}: {self.score}"

# ====== AI 成绩分析模型 ======
from apps.scores.ai_models import AIAnalysisConfig, AIAnalysisRecord, AIExamAnalysisSource, AIQuestionWeakness

