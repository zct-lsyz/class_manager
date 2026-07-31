"""AI 成绩分析配置模型"""
from django.db import models
from django.conf import settings
from django.core import signing

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
        if key:
            self.api_key_encrypted = signing.dumps(key)

    def get_api_key(self):
        if not self.api_key_encrypted:
            return ""
        try:
            return signing.loads(self.api_key_encrypted)
        except Exception:
            return ""

    def has_api_key(self):
        """是否有可用的 API Key（环境变量优先）"""
        import os
        if os.environ.get("DEEPSEEK_API_KEY"):
            return True
        return bool(self.get_api_key())


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
        return f"{self.get_analysis_type_display()} - {self.subject_name or self.student.name} ({self.created_at:%Y-%m-%d %H:%M})"
