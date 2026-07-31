import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def clear_stored_api_keys(apps, schema_editor):
    AIAnalysisConfig = apps.get_model("scores", "AIAnalysisConfig")
    AIAnalysisConfig.objects.exclude(api_key_encrypted="").update(api_key_encrypted="")


class Migration(migrations.Migration):

    dependencies = [
        ("scores", "0003_exam_score_is_deleted"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AIExamAnalysisSource",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="创建时间")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="更新时间")),
                ("paper_file", models.FileField(upload_to="ai_exam/papers/%Y/%m/", verbose_name="试卷原卷")),
                ("score_file", models.FileField(upload_to="ai_exam/scores/%Y/%m/", verbose_name="小分表")),
                ("paper_text", models.TextField(blank=True, default="", verbose_name="试卷解析文本")),
                ("question_summary", models.JSONField(blank=True, default=list, verbose_name="匿名逐题统计")),
                ("warnings", models.JSONField(blank=True, default=list, verbose_name="解析警告")),
                ("analysis_result", models.JSONField(blank=True, default=dict, verbose_name="结构化分析结果")),
                ("overall_summary", models.TextField(blank=True, default="", verbose_name="总体分析")),
                ("status", models.CharField(choices=[("uploaded", "已上传"), ("parsing", "解析中"), ("completed", "已完成"), ("failed", "失败")], default="uploaded", max_length=20, verbose_name="状态")),
                ("error_message", models.TextField(blank=True, default="", verbose_name="错误信息")),
                ("model_name", models.CharField(blank=True, default="", max_length=100, verbose_name="模型")),
                ("duration_ms", models.IntegerField(blank=True, null=True, verbose_name="耗时(ms)")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, verbose_name="操作人")),
                ("exam_subject", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="ai_exam_analysis_sources", to="scores.examsubject", verbose_name="考试科目")),
                ("school_class", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="ai_exam_analysis_sources", to="classes.schoolclass", verbose_name="班级")),
            ],
            options={"verbose_name": "AI 试卷小分分析", "verbose_name_plural": "AI 试卷小分分析", "ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="AIQuestionWeakness",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="创建时间")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="更新时间")),
                ("question_label", models.CharField(max_length=100, verbose_name="题号")),
                ("question_type", models.CharField(blank=True, default="", max_length=100, verbose_name="题型")),
                ("knowledge_points", models.JSONField(blank=True, default=list, verbose_name="知识点")),
                ("full_score", models.FloatField(blank=True, null=True, verbose_name="满分")),
                ("average_score", models.FloatField(blank=True, null=True, verbose_name="平均分")),
                ("score_rate", models.FloatField(blank=True, null=True, verbose_name="得分率")),
                ("zero_rate", models.FloatField(blank=True, null=True, verbose_name="零分率")),
                ("full_rate", models.FloatField(blank=True, null=True, verbose_name="满分率")),
                ("weakness_level", models.CharField(choices=[("high", "重点薄弱"), ("medium", "一般薄弱"), ("low", "掌握较好")], default="medium", max_length=20, verbose_name="薄弱等级")),
                ("analysis", models.TextField(blank=True, default="", verbose_name="薄弱原因分析")),
                ("recommendation", models.TextField(blank=True, default="", verbose_name="教学建议")),
                ("sort_order", models.IntegerField(default=0, verbose_name="排序")),
                ("source", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="weaknesses", to="scores.aiexamanalysissource", verbose_name="分析任务")),
            ],
            options={"verbose_name": "逐题薄弱知识点", "verbose_name_plural": "逐题薄弱知识点", "ordering": ["sort_order", "id"]},
        ),
        migrations.RunPython(clear_stored_api_keys, migrations.RunPython.noop),
    ]
