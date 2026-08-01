"""
AI 成绩分析视图
- 设置页：API Key + 模型 + 九科提示词（可折叠逐科编辑）
- 生成页：调用模型返回分析结果并保存记录
"""
import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.scores.ai_models import AIAnalysisConfig, AIAnalysisRecord
from apps.scores.ai_prompts import get_default_prompts, get_subject_names
from apps.scores import ai_services
from apps.classes.models import SchoolClass
from apps.scores.models import Exam, ExamSubject, Score, Subject
from apps.students.models import Student


def _get_or_create_config(current_class):
    """获取或创建当前班级的 AI 配置"""
    config, created = AIAnalysisConfig.objects.get_or_create(
        school_class=current_class,
        defaults={"prompts": get_default_prompts()},
    )
    return config


@login_required
def ai_settings(request):
    """AI 分析设置页"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
    config = _get_or_create_config(current_class) if current_class else None

    if request.method == "POST":
        action = request.POST.get("action", "save")

        if action == "save":
            config.model_name = request.POST.get("model_name", "deepseek-chat").strip()
            config.base_url = request.POST.get("base_url", "https://api.deepseek.com").strip()
            try:
                config.temperature = float(request.POST.get("temperature", "0.5"))
            except (ValueError, TypeError):
                config.temperature = 0.5
            config.is_enabled = request.POST.get("is_enabled") == "1"

            # 保存每科提示词
            prompts = dict(config.prompts or {})
            for subject in get_subject_names():
                key = f"prompt_{subject}"
                value = request.POST.get(key, "").strip()
                if value:
                    prompts[subject] = value
                elif subject not in prompts:
                    prompts[subject] = ""
            # 移除空提示词（保留默认值显示）
            config.prompts = {k: v for k, v in prompts.items() if v}
            config.save()

            if config.is_enabled and not config.has_api_key():
                messages.warning(request, "已保存设置，但尚未配置 API Key，AI 分析暂不可用。")
            else:
                messages.success(request, "AI 分析设置已保存。")
            return redirect("scores:ai_settings")

        elif action == "test":
            # 测试 API 连接
            try:
                content, duration = ai_services.call_chat_completion(
                    config.base_url,
                    ai_services.get_effective_api_key(config),
                    config.model_name,
                    [{"role": "user", "content": "请回复：连接成功"}],
                    config.temperature,
                    timeout=30,
                )
                messages.success(request, f"API 连接测试成功（{duration}ms）：{content[:50]}")
            except ai_services.AIAnalysisError as exc:
                messages.error(request, f"API 连接测试失败：{exc}")

        elif action == "reset_prompts":
            config.prompts = get_default_prompts()
            config.save()
            messages.success(request, "提示词已恢复为默认值。")

        return redirect("scores:ai_settings")

    # GET: 展示配置
    prompts = config.prompts if config else {}
    default_prompts = get_default_prompts()
    # 合并：数据库缺失的科目显示默认提示词
    merged_prompts = {}
    for subject in get_subject_names():
        merged_prompts[subject] = {
            "current": prompts.get(subject, ""),
            "default": default_prompts.get(subject, ""),
        }

    # 历史记录
    records = AIAnalysisRecord.objects.filter(school_class=current_class)[:10] if current_class else []

    return render(request, "scores/ai_settings.html", {
        "config": config,
        "subjects": get_subject_names(),
        "merged_prompts": merged_prompts,
        "records": records,
        "has_key": config.has_api_key() if config else False,
    })


def _build_subject_data_context(exam, subject_name):
    """构建单科分析的数据上下文"""
    es = ExamSubject.objects.filter(
        exam=exam, subject__name=subject_name,
    ).select_related("subject").first()
    if not es:
        return None

    scores_qs = Score.objects.filter(
        exam_subject=es,
        status="normal",
        score__isnull=False,
        is_deleted=False,
    )
    scores = list(scores_qs.select_related("student"))
    if not scores:
        return None

    values = [float(s.score) for s in scores]
    avg = round(sum(values) / len(values), 1)
    full = es.full_score
    pass_count = sum(1 for v in values if v >= full * 0.6)
    excellent_count = sum(1 for v in values if v >= full * 0.85)

    # 前10名和后10名
    scores_sorted = sorted(scores, key=lambda s: float(s.score), reverse=True)
    top10 = [
        {"匿名序号": index, "分数": float(score.score)}
        for index, score in enumerate(scores_sorted[:10], 1)
    ]
    bottom10 = [
        {"匿名序号": index, "分数": float(score.score)}
        for index, score in enumerate(scores_sorted[-10:], 1)
    ]

    return {
        "考试": exam.name,
        "科目": subject_name,
        "满分": full,
        "参考人数": len(scores),
        "平均分": avg,
        "最高分": max(values),
        "最低分": min(values),
        "及格率": f"{round(pass_count / len(scores) * 100, 1)}%",
        "优秀率": f"{round(excellent_count / len(scores) * 100, 1)}%",
        "得分率分段": {
            "0-59%": sum(1 for v in values if v / full < 0.6),
            "60-69%": sum(1 for v in values if 0.6 <= v / full < 0.7),
            "70-79%": sum(1 for v in values if 0.7 <= v / full < 0.8),
            "80-89%": sum(1 for v in values if 0.8 <= v / full < 0.9),
            "90-100%": sum(1 for v in values if v / full >= 0.9),
        },
        "前10名": top10,
        "后10名": bottom10,
    }


@login_required
@require_POST
def ai_generate(request):
    """生成 AI 分析"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
    config = _get_or_create_config(current_class) if current_class else None

    if not config or not config.is_enabled:
        messages.error(request, "AI 分析未启用，请先在「AI 分析设置」中配置。")
        return redirect("scores:analysis")

    if not config.has_api_key():
        messages.error(request, "未配置 API Key，请先在「AI 分析设置」中填写。")
        return redirect("scores:analysis")

    analysis_type = request.POST.get("analysis_type", "subject")
    exam_id = request.POST.get("exam_id", "")
    subject_name = request.POST.get("subject_name", "")
    student_id = request.POST.get("student_id", "")

    exam = None
    if exam_id:
        exam = Exam.objects.filter(
            pk=exam_id, school_class=current_class, is_deleted=False
        ).first()
    if not exam:
        messages.error(request, "请先选择考试。")
        return redirect("scores:analysis")

    record = AIAnalysisRecord(
        school_class=current_class, exam=exam, analysis_type=analysis_type,
        model_name=config.model_name, created_by=request.user,
    )

    try:
        if analysis_type == "subject":
            if not subject_name:
                messages.error(request, "请选择科目。")
                return redirect("scores:analysis")
            data_context = _build_subject_data_context(exam, subject_name)
            if not data_context:
                messages.error(request, f"「{subject_name}」暂无有效成绩数据。")
                return redirect("scores:analysis")
            result, duration, prompt = ai_services.generate_subject_analysis(
                config, subject_name, data_context,
            )
            record.subject_name = subject_name
            record.input_summary = json.dumps(data_context, ensure_ascii=False)[:500]

        elif analysis_type == "comprehensive":
            # 全科综合分析
            data_context = {}
            for es in ExamSubject.objects.filter(exam=exam).select_related("subject"):
                sub_data = _build_subject_data_context(exam, es.subject.name)
                if sub_data:
                    data_context[es.subject.name] = sub_data
            if not data_context:
                messages.error(request, "该考试暂无有效成绩数据。")
                return redirect("scores:analysis")
            result, duration, prompt = ai_services.generate_comprehensive_analysis(config, data_context)
            record.subject_name = "综合"
            record.input_summary = json.dumps(data_context, ensure_ascii=False)[:500]

        elif analysis_type == "student":
            student = Student.objects.filter(pk=student_id).first() if student_id else None
            if not student:
                messages.error(request, "请选择学生。")
                return redirect("scores:analysis")
            record.student = student
            # 学生历次总分
            exams_qs = Exam.objects.filter(
                school_class=current_class, is_deleted=False,
            ).order_by("date")
            trend = []
            for e in exams_qs:
                total = 0
                total_full = 0
                count = 0
                subject_scores = {}
                for es in ExamSubject.objects.filter(exam=e):
                    s = Score.objects.filter(
                        exam_subject=es,
                        student=student,
                        status="normal",
                        is_deleted=False,
                    ).first()
                    if s and s.score is not None:
                        total += float(s.score)
                        total_full += es.full_score
                        count += 1
                        subject_scores[es.subject.name] = {
                            "成绩": float(s.score), "满分": es.full_score, "班级名次": s.rank,
                        }
                if count > 0:
                    trend.append({
                        "考试": e.name, "日期": str(e.date), "各科": subject_scores,
                        "总分": round(total, 1), "得分率": round(total / total_full * 100, 1) if total_full else 0,
                    })
            data_context = {"学生": "匿名学生", "历次考试": trend}
            result, duration, prompt = ai_services.generate_student_analysis(config, data_context)
            record.subject_name = student.name
            record.input_summary = json.dumps(data_context, ensure_ascii=False)[:500]

        else:
            messages.error(request, "未知的分析类型。")
            return redirect("scores:analysis")

        record.result = result
        record.duration_ms = duration
        record.prompt_used = prompt
        record.success = True
        record.save()

        config.last_used_at = timezone.now()
        config.last_error = ""
        config.save(update_fields=["last_used_at", "last_error", "updated_at"])

        messages.success(request, "AI 分析生成成功！")
        return redirect(f"{request.META.get('HTTP_REFERER', '/scores/analysis/')}#ai-analysis-result")

    except ai_services.AIAnalysisError as exc:
        record.success = False
        record.error_message = str(exc)
        record.save()
        config.last_error = str(exc)
        config.save(update_fields=["last_error", "updated_at"])
        messages.error(request, f"AI 分析失败：{exc}")
        return redirect("scores:analysis")


@login_required
def ai_records(request):
    """AI 分析历史记录"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
    records = AIAnalysisRecord.objects.filter(
        school_class=current_class,
    ).select_related("exam", "student").order_by("-created_at")[:50] if current_class else []

    return render(request, "scores/ai_records.html", {"records": records})


@login_required
def ai_record_detail(request, pk):
    """AI 分析记录详情"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
    record = get_object_or_404(
        AIAnalysisRecord.objects.select_related("exam", "student"),
        pk=pk, school_class=current_class,
    )
    return render(request, "scores/ai_record_detail.html", {"record": record})
