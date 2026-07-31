"""AI 成绩分析配置模型"""
from django.db import models
from django.conf import settings

from apps.classes.models import SchoolClass


class BaseModel(models.Model):
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        abstract = True


class AIAnalysisConfig(BaseModel):
    """AI 成绩分析配置（API Key + 模型 + 九科提示词）"""
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE,
        related_name="ai_configs", verbose_name="班级",
    )
    api_key_encrypted = models.TextField("API Key（加密存储）", blank=True, default="")
    model_name = models.CharField(
        "模型名称", max_length=100, default="deepseek-chat",
    )
    base_url = models.CharField(
        "API 地址", max_length=200,
        default="https://api.deepseek.com",
        help_text="OpenAI 兼容接口地址",
    )
    temperature = models.FloatField("温度", default=0.5)
    is_enabled = models.BooleanField("启用 AI 分析", default=False)
    # 每科提示词，JSON 格式 {"语文": "...", "数学": "..."}
    prompts = models.JSONField("科目提示词", blank=True, default=dict)
    last_used_at = models.DateTimeField("最后调用时间", null=True, blank=True)
    last_error = models.TextField("最后错误信息", blank=True, default="")

    class Meta:
        verbose_name = "AI 分析配置"
        verbose_name_plural = "AI 分析配置"
        unique_together = ["school_class"]

    def __str__(self):
        enabled = "启用" if self.is_enabled else "停用"
        return f"AI 成绩分析配置（{enabled}）"

    # ----- API Key 加密存储 -----
    def set_api_key(self, key):
        """保留兼容入口；密钥不再写入数据库。"""
        self.api_key_encrypted = ""

    def get_api_key(self):
        return ""

    def has_api_key(self):
        """是否有可用的 API Key（环境变量优先）"""
        import os
        return bool(os.environ.get("DEEPSEEK_API_KEY", "").strip())


class AIAnalysisRecord(BaseModel):
    """AI 分析结果记录"""
    ANALYSIS_TYPES = [
        ("subject", "单科分析"),
        ("comprehensive", "综合分析"),
        ("student", "学生个人分析"),
    ]

    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE,
        related_name="ai_analysis_records", verbose_name="班级",
    )
    exam = models.ForeignKey(
        "scores.Exam", on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="考试",
    )
    student = models.ForeignKey(
        "students.Student", on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="学生",
    )
    analysis_type = models.CharField(
        "分析类型", max_length=30, choices=ANALYSIS_TYPES,
    )
    subject_name = models.CharField("科目", max_length=50, blank=True, default="")
    prompt_used = models.TextField("使用的提示词", blank=True, default="")
    input_summary = models.TextField("输入数据摘要", blank=True, default="")
    result = models.TextField("分析结果", blank=True, default="")
    model_name = models.CharField("模型", max_length=100, blank=True, default="")
    duration_ms = models.IntegerField("耗时(ms)", null=True, blank=True)
    success = models.BooleanField("是否成功", default=True)
    error_message = models.TextField("错误信息", blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="操作人",
    )

    class Meta:
        verbose_name = "AI 分析记录"
        verbose_name_plural = "AI 分析记录"
        ordering = ["-created_at"]

    def __str__(self):
        target = self.subject_name or (self.student.name if self.student else "未指定")
        return f"{self.get_analysis_type_display()} - {target} ({self.created_at:%Y-%m-%d %H:%M})"


class AIExamAnalysisSource(BaseModel):
    """试卷原卷与小分表联合分析任务。"""
    STATUS_CHOICES = [
        ("uploaded", "已上传"),
        ("parsing", "解析中"),
        ("completed", "已完成"),
        ("failed", "失败"),
    ]

    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE,
        related_name="ai_exam_analysis_sources", verbose_name="班级",
    )
    exam_subject = models.ForeignKey(
        "scores.ExamSubject", on_delete=models.CASCADE,
        related_name="ai_exam_analysis_sources", verbose_name="考试科目",
    )
    paper_file = models.FileField("试卷原卷", upload_to="ai_exam/papers/%Y/%m/")
    score_file = models.FileField("小分表", upload_to="ai_exam/scores/%Y/%m/")
    paper_text = models.TextField("试卷解析文本", blank=True, default="")
    question_summary = models.JSONField("匿名逐题统计", blank=True, default=list)
    warnings = models.JSONField("解析警告", blank=True, default=list)
    analysis_result = models.JSONField("结构化分析结果", blank=True, default=dict)
    overall_summary = models.TextField("总体分析", blank=True, default="")
    status = models.CharField(
        "状态", max_length=20, choices=STATUS_CHOICES, default="uploaded",
    )
    error_message = models.TextField("错误信息", blank=True, default="")
    model_name = models.CharField("模型", max_length=100, blank=True, default="")
    duration_ms = models.IntegerField("耗时(ms)", null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="操作人",
    )

    class Meta:
        verbose_name = "AI 试卷小分分析"
        verbose_name_plural = "AI 试卷小分分析"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.exam_subject} - {self.created_at:%Y-%m-%d %H:%M}"


class AIQuestionWeakness(BaseModel):
    """逐题知识点薄弱情况。"""
    WEAKNESS_CHOICES = [
        ("high", "重点薄弱"),
        ("medium", "一般薄弱"),
        ("low", "掌握较好"),
    ]

    source = models.ForeignKey(
        AIExamAnalysisSource, on_delete=models.CASCADE,
        related_name="weaknesses", verbose_name="分析任务",
    )
    question_label = models.CharField("题号", max_length=100)
    question_type = models.CharField("题型", max_length=100, blank=True, default="")
    knowledge_points = models.JSONField("知识点", blank=True, default=list)
    full_score = models.FloatField("满分", null=True, blank=True)
    average_score = models.FloatField("平均分", null=True, blank=True)
    score_rate = models.FloatField("得分率", null=True, blank=True)
    zero_rate = models.FloatField("零分率", null=True, blank=True)
    full_rate = models.FloatField("满分率", null=True, blank=True)
    weakness_level = models.CharField(
        "薄弱等级", max_length=20, choices=WEAKNESS_CHOICES, default="medium",
    )
    analysis = models.TextField("薄弱原因分析", blank=True, default="")
    recommendation = models.TextField("教学建议", blank=True, default="")
    sort_order = models.IntegerField("排序", default=0)

    class Meta:
        verbose_name = "逐题薄弱知识点"
        verbose_name_plural = "逐题薄弱知识点"
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"{self.source} - {self.question_label}"
