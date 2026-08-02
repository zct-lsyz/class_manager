"""评选管理：评选项目、评分规则、评选结果"""
from django.db import models

from apps.classes.models import SchoolClass, Semester
from apps.students.models import Student


class BaseModel(models.Model):
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        abstract = True


class EvaluationProject(BaseModel):
    """评选项目（如：三好学生、优秀班干部、文明之星）"""
    CYCLE_CHOICES = [
        ("weekly", "每周评选"),
        ("monthly", "每月评选"),
        ("semester", "每学期评选"),
    ]
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE,
        related_name="evaluation_projects", verbose_name="班级",
    )
    semester = models.ForeignKey(
        Semester, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="学期",
    )
    name = models.CharField("评选名称", max_length=100)
    description = models.TextField("项目描述", blank=True, default="")
    cycle = models.CharField(
        "评选周期", max_length=20, choices=CYCLE_CHOICES, default="monthly",
    )
    # 规则配置：[{key, label, weight, params}]
    rules_json = models.JSONField("评分规则", default=dict, blank=True)
    is_active = models.BooleanField("启用", default=True)
    sort_order = models.IntegerField("排序", default=0)

    class Meta:
        verbose_name = "评选项目"
        verbose_name_plural = "评选项目"
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.name

    def cycle_display(self):
        return dict(self.CYCLE_CHOICES).get(self.cycle, self.cycle)

    def rules(self):
        return self.rules_json.get("indicators", [])


class EvaluationResult(BaseModel):
    """评选结果（每次计算生成）"""
    project = models.ForeignKey(
        EvaluationProject, on_delete=models.CASCADE,
        related_name="results", verbose_name="评选项目",
    )
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE,
        related_name="evaluation_results", verbose_name="学生",
    )
    period_label = models.CharField("评选周期标签", max_length=100)
    total_score = models.FloatField("综合得分", default=0)
    rank = models.IntegerField("排名")
    # 各指标得分明细：{key: {raw, score, label}}
    score_details = models.JSONField("评分明细", default=dict, blank=True)

    class Meta:
        verbose_name = "评选结果"
        verbose_name_plural = "评选结果"
        ordering = ["-created_at", "rank"]
        unique_together = [("project", "student", "period_label")]

    def __str__(self):
        return f"{self.project.name} · {self.period_label} 第{self.rank}名 {self.student.name}"
