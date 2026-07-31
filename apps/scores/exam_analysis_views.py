"""试卷原卷 + 小分表联合 AI 分析视图。"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.audit.models import OperationLog
from apps.classes.models import SchoolClass
from apps.scores.ai_models import AIAnalysisConfig, AIExamAnalysisSource, AIQuestionWeakness
from apps.scores.ai_prompts import get_default_prompts, get_subject_names
from apps.scores.exam_analysis_services import (
    ExamAnalysisParseError,
    build_score_template_bytes,
    extract_paper_text,
    generate_exam_analysis,
    parse_score_sheet,
    validate_uploads,
)
from apps.scores.models import ExamSubject


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    return forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR", "")


def _analysis_level(score_rate):
    if score_rate < 0.6:
        return "high"
    if score_rate < 0.75:
        return "medium"
    return "low"


@login_required
def exam_analysis(request):
    current_class = SchoolClass.objects.filter(is_current=True).first()
    config = None
    exam_subjects = ExamSubject.objects.none()
    sources = AIExamAnalysisSource.objects.none()
    if current_class:
        config, _created = AIAnalysisConfig.objects.get_or_create(
            school_class=current_class, defaults={"prompts": get_default_prompts()},
        )
        exam_subjects = ExamSubject.objects.filter(
            exam__school_class=current_class, exam__is_deleted=False,
        ).select_related("exam", "subject").order_by("-exam__date", "sort_order")
        sources = AIExamAnalysisSource.objects.filter(
            school_class=current_class,
        ).select_related("exam_subject__exam", "exam_subject__subject")[:30]

    if request.method == "POST":
        if not current_class:
            messages.error(request, "请先设置当前班级。")
            return redirect("scores:exam_analysis")
        if not config.is_enabled or not config.has_api_key():
            messages.error(request, "请先启用 AI 分析并在服务器环境变量中配置 DEEPSEEK_API_KEY。")
            return redirect("scores:ai_settings")
        if request.POST.get("privacy_confirm") != "1":
            messages.error(request, "请确认外部 AI 数据范围后再开始分析。")
            return redirect("scores:exam_analysis")

        subject_name = request.POST.get("subject_name", "").strip()
        if subject_name not in get_subject_names():
            messages.error(request, "请选择九科中的一个科目。")
            return redirect("scores:exam_analysis")
        exam_subject = ExamSubject.objects.filter(
            exam__school_class=current_class,
            exam__is_deleted=False,
            subject__name__in=(["英语", "外语"] if subject_name == "英语" else [subject_name]),
        ).select_related("exam", "subject").order_by("-exam__date").first()
        paper_file = request.FILES.get("paper_file")
        score_file = request.FILES.get("score_file")
        if not paper_file or not score_file:
            messages.error(request, "请同时上传试卷原卷和小分表。")
            return redirect("scores:exam_analysis")
        try:
            validate_uploads(paper_file, score_file)
        except ExamAnalysisParseError as exc:
            messages.error(request, str(exc))
            return redirect("scores:exam_analysis")

        source = AIExamAnalysisSource.objects.create(
            school_class=current_class,
            exam_subject=exam_subject,
            subject_name=subject_name,
            paper_file=paper_file,
            score_file=score_file,
            status="parsing",
            model_name=config.model_name,
            created_by=request.user,
        )
        try:
            paper_text = extract_paper_text(source.paper_file.path)
            question_summaries, warnings = parse_score_sheet(source.score_file.path, current_class)
            source.paper_text = paper_text
            source.question_summary = question_summaries
            source.warnings = warnings
            source.save(update_fields=["paper_text", "question_summary", "warnings", "updated_at"])

            result, duration = generate_exam_analysis(config, paper_text, question_summaries, subject_name)
            ai_questions = {
                str(item.get("question_label", "")).strip(): item
                for item in result.get("questions", []) if isinstance(item, dict)
            }
            with transaction.atomic():
                for summary in question_summaries:
                    ai_item = ai_questions.get(summary["question_label"], {})
                    knowledge_points = ai_item.get("knowledge_points") or summary["knowledge_points"]
                    if not isinstance(knowledge_points, list):
                        knowledge_points = [str(knowledge_points)] if knowledge_points else []
                    AIQuestionWeakness.objects.create(
                        source=source,
                        question_label=summary["question_label"],
                        question_type=ai_item.get("question_type") or summary["question_type"],
                        knowledge_points=knowledge_points,
                        full_score=summary["full_score"],
                        average_score=summary["average_score"],
                        score_rate=summary["score_rate"],
                        zero_rate=summary["zero_rate"],
                        full_rate=summary["full_rate"],
                        weakness_level=_analysis_level(summary["score_rate"]),
                        analysis=str(ai_item.get("analysis", "")),
                        recommendation=str(ai_item.get("recommendation", "")),
                        sort_order=summary["sort_order"],
                    )
                source.analysis_result = result
                source.overall_summary = str(result.get("overall_summary", ""))
                source.duration_ms = duration
                source.status = "completed"
                source.error_message = ""
                source.save(update_fields=[
                    "analysis_result", "overall_summary", "duration_ms", "status",
                    "error_message", "updated_at",
                ])
            config.last_used_at = timezone.now()
            config.last_error = ""
            config.save(update_fields=["last_used_at", "last_error", "updated_at"])
            OperationLog.objects.create(
                user=request.user, action="create", module="ai_exam_analysis",
                object_repr=f"{exam_subject.exam.name + ' - ' if exam_subject else ''}{subject_name}",
                detail=f"原卷和匿名小分表联合分析，共 {len(question_summaries)} 道题",
                ip_address=_client_ip(request), success=True,
            )
            messages.success(request, "试卷与小分表分析完成。")
        except Exception as exc:
            source.status = "failed"
            source.error_message = str(exc)
            source.save(update_fields=["status", "error_message", "updated_at"])
            config.last_error = str(exc)
            config.save(update_fields=["last_error", "updated_at"])
            OperationLog.objects.create(
                user=request.user, action="create", module="ai_exam_analysis",
                object_repr=f"{exam_subject.exam.name + ' - ' if exam_subject else ''}{subject_name}",
                detail=f"原卷和小分表分析失败：{exc}", ip_address=_client_ip(request), success=False,
            )
            messages.error(request, f"分析失败：{exc}")
        return redirect("scores:exam_analysis_detail", pk=source.pk)

    return render(request, "scores/exam_ai_analysis.html", {
        "current_class": current_class,
        "config": config,
        "exam_subjects": exam_subjects,
        "subject_names": get_subject_names(),
        "sources": sources,
        "ai_ready": bool(config and config.is_enabled and config.has_api_key()),
    })


@login_required
def exam_analysis_detail(request, pk):
    current_class = SchoolClass.objects.filter(is_current=True).first()
    source = get_object_or_404(
        AIExamAnalysisSource.objects.select_related(
            "exam_subject__exam", "exam_subject__subject", "created_by",
        ).prefetch_related("weaknesses"),
        pk=pk, school_class=current_class,
    )
    return render(request, "scores/exam_ai_analysis_detail.html", {"source": source})


@login_required
def score_template(request):
    response = HttpResponse(
        build_score_template_bytes(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = 'attachment; filename="exam_question_scores_template.xlsx"'
    return response
