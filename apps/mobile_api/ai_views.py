import json

from django.db import transaction
from django.utils import timezone

from apps.classes.utils import get_current_class
from apps.mobile_api.auth import api_error, api_ok, mobile_api, parse_data
from apps.scores import ai_services
from apps.scores.ai_models import AIAnalysisConfig, AIAnalysisRecord, AIExamAnalysisSource, AIQuestionWeakness
from apps.scores.ai_prompts import get_default_prompts, get_subject_names
from apps.scores.models import Exam, ExamSubject, Score
from apps.students.models import Student


def _config(current):
    return AIAnalysisConfig.objects.get_or_create(
        school_class=current, defaults={"prompts": get_default_prompts()},
    )[0]


def _record(row):
    return {
        "id": row.pk, "analysis_type": row.analysis_type,
        "analysis_type_display": row.get_analysis_type_display(),
        "exam": row.exam.name if row.exam else "",
        "student": row.student.name if row.student else "",
        "subject_name": row.subject_name, "result": row.result,
        "model_name": row.model_name, "duration_ms": row.duration_ms,
        "success": row.success, "error_message": row.error_message,
        "created_at": row.created_at.isoformat(),
    }


def _exam_source(row):
    return {
        "id": row.pk, "subject_name": row.subject_name,
        "exam_subject_id": row.exam_subject_id,
        "exam": row.exam_subject.exam.name if row.exam_subject else "",
        "status": row.status, "status_display": row.get_status_display(),
        "overall_summary": row.overall_summary, "warnings": row.warnings,
        "result": row.analysis_result, "error_message": row.error_message,
        "model_name": row.model_name, "duration_ms": row.duration_ms,
        "created_at": row.created_at.isoformat(),
        "weaknesses": [{
            "question_label": item.question_label, "question_type": item.question_type,
            "knowledge_points": item.knowledge_points, "full_score": item.full_score,
            "average_score": item.average_score, "score_rate": item.score_rate,
            "zero_rate": item.zero_rate, "full_rate": item.full_rate,
            "weakness_level": item.get_weakness_level_display(),
            "analysis": item.analysis, "recommendation": item.recommendation,
        } for item in row.weaknesses.all()],
    }


def _payload(current, config):
    exams = Exam.objects.filter(school_class=current, is_deleted=False).order_by("-date")
    students = Student.objects.filter(school_class=current, is_deleted=False).order_by("sort_order", "student_id")
    records = AIAnalysisRecord.objects.filter(school_class=current).select_related("exam", "student")[:50]
    return {
        "config": {
            "model_name": config.model_name, "base_url": config.base_url,
            "temperature": config.temperature, "is_enabled": config.is_enabled,
            "has_api_key": config.has_api_key(), "prompts": config.prompts,
            "last_used_at": config.last_used_at.isoformat() if config.last_used_at else None,
            "last_error": config.last_error,
        },
        "subjects": get_subject_names(),
        "exams": [{
            "id": row.pk, "name": row.name, "date": row.date.isoformat(),
            "subjects": [item.subject.name for item in ExamSubject.objects.filter(exam=row).select_related("subject")],
        } for row in exams],
        "students": [{"id": row.pk, "name": row.name, "student_id": row.student_id} for row in students],
        "records": [_record(row) for row in records],
    }


@mobile_api(["GET", "POST"])
def analysis(request):
    current = get_current_class(request.mobile_user)
    if not current:
        return api_error("请先设置当前班级。")
    config = _config(current)
    if request.method == "GET":
        return api_ok(_payload(current, config))
    data = parse_data(request)
    action = data.get("action", "generate")
    if action == "save":
        config.model_name = str(data.get("model_name", "deepseek-chat")).strip()
        config.base_url = str(data.get("base_url", "https://api.deepseek.com")).strip()
        try:
            config.temperature = float(data.get("temperature", 0.5))
        except (TypeError, ValueError):
            return api_error("温度必须是有效数字。")
        enabled = data.get("is_enabled", False)
        config.is_enabled = enabled if isinstance(enabled, bool) else str(enabled).lower() in {"1", "true", "yes", "on"}
        prompts = data.get("prompts")
        if isinstance(prompts, dict):
            config.prompts = {str(key): str(value) for key, value in prompts.items() if str(value).strip()}
        config.save()
        return api_ok(_payload(current, config))
    if action == "reset_prompts":
        config.prompts = get_default_prompts()
        config.save(update_fields=["prompts", "updated_at"])
        return api_ok(_payload(current, config))
    if action == "test":
        try:
            content, duration = ai_services.call_chat_completion(
                config.base_url, ai_services.get_effective_api_key(config), config.model_name,
                [{"role": "user", "content": "请回复：连接成功"}], config.temperature, timeout=30,
            )
        except ai_services.AIAnalysisError as exc:
            return api_error(f"API 连接测试失败：{exc}", 400, "ai_failed")
        return api_ok({"message": content[:100], "duration_ms": duration})
    if not config.is_enabled or not config.has_api_key():
        return api_error("AI 分析未启用或服务器尚未配置 DEEPSEEK_API_KEY。")
    return _generate(request, current, config, data)


@mobile_api(["GET", "POST"])
def exam_paper_analysis(request):
    from apps.scores.exam_analysis_services import (
        ExamAnalysisParseError, extract_paper_text, generate_exam_analysis,
        parse_score_sheet, validate_uploads,
    )
    current = get_current_class(request.mobile_user)
    if not current:
        return api_error("请先设置当前班级。")
    config = _config(current)
    exam_subjects = ExamSubject.objects.filter(
        exam__school_class=current, exam__is_deleted=False,
    ).select_related("exam", "subject").order_by("-exam__date", "sort_order")
    if request.method == "GET":
        sources = AIExamAnalysisSource.objects.filter(
            school_class=current,
        ).select_related("exam_subject__exam", "exam_subject__subject").prefetch_related("weaknesses")[:30]
        return api_ok({
            "ai_ready": config.is_enabled and config.has_api_key(),
            "subjects": get_subject_names(),
            "exam_subjects": [{
                "id": row.pk, "label": f"{row.exam.name} · {row.subject.name}",
                "subject": row.subject.name, "date": row.exam.date.isoformat(),
            } for row in exam_subjects],
            "sources": [_exam_source(row) for row in sources],
        })
    if not config.is_enabled or not config.has_api_key():
        return api_error("AI 分析未启用或服务器尚未配置 DEEPSEEK_API_KEY。")
    data = parse_data(request)
    if str(data.get("privacy_confirm", "")).lower() not in {"1", "true", "yes", "on"}:
        return api_error("请确认外部 AI 数据范围后再开始分析。")
    subject_name = str(data.get("subject_name", "")).strip()
    if subject_name not in get_subject_names():
        return api_error("请选择九科中的一个科目。")
    subject_names = ["英语", "外语"] if subject_name == "英语" else [subject_name]
    selected = exam_subjects.filter(
        pk=data.get("exam_subject_id"), subject__name__in=subject_names,
    ).first() if data.get("exam_subject_id") else exam_subjects.filter(subject__name__in=subject_names).first()
    paper_file = request.FILES.get("paper_file")
    score_file = request.FILES.get("score_file")
    if not paper_file or not score_file:
        return api_error("请同时选择试卷原卷和小分表。")
    try:
        validate_uploads(paper_file, score_file)
    except ExamAnalysisParseError as exc:
        return api_error(str(exc))
    source = AIExamAnalysisSource.objects.create(
        school_class=current, exam_subject=selected, subject_name=subject_name,
        paper_file=paper_file, score_file=score_file, status="parsing",
        model_name=config.model_name, created_by=request.mobile_user,
    )
    try:
        paper_text = extract_paper_text(source.paper_file.path)
        question_summaries, warnings = parse_score_sheet(source.score_file.path, current)
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
                score_rate = summary["score_rate"]
                AIQuestionWeakness.objects.create(
                    source=source, question_label=summary["question_label"],
                    question_type=ai_item.get("question_type") or summary["question_type"],
                    knowledge_points=knowledge_points, full_score=summary["full_score"],
                    average_score=summary["average_score"], score_rate=score_rate,
                    zero_rate=summary["zero_rate"], full_rate=summary["full_rate"],
                    weakness_level="high" if score_rate < .6 else "medium" if score_rate < .75 else "low",
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
        source = AIExamAnalysisSource.objects.prefetch_related("weaknesses").select_related(
            "exam_subject__exam",
        ).get(pk=source.pk)
        return api_ok(_exam_source(source), 201)
    except Exception as exc:
        source.status = "failed"
        source.error_message = str(exc)
        source.save(update_fields=["status", "error_message", "updated_at"])
        config.last_error = str(exc)
        config.save(update_fields=["last_error", "updated_at"])
        return api_error(f"分析失败：{exc}", 400, "analysis_failed")


def _generate(request, current, config, data):
    from apps.scores import ai_views as web_ai_views

    analysis_type = str(data.get("analysis_type", "subject"))
    exam = Exam.objects.filter(pk=data.get("exam_id"), school_class=current, is_deleted=False).first()
    if not exam:
        return api_error("请选择有效考试。")
    record = AIAnalysisRecord(
        school_class=current, exam=exam, analysis_type=analysis_type,
        model_name=config.model_name, created_by=request.mobile_user,
    )
    try:
        if analysis_type == "subject":
            subject_name = str(data.get("subject_name", "")).strip()
            context = web_ai_views._build_subject_data_context(exam, subject_name)
            if not context:
                return api_error("所选科目暂无有效成绩数据。")
            result, duration, prompt = ai_services.generate_subject_analysis(config, subject_name, context)
            record.subject_name = subject_name
        elif analysis_type == "comprehensive":
            context = {}
            for item in ExamSubject.objects.filter(exam=exam).select_related("subject"):
                value = web_ai_views._build_subject_data_context(exam, item.subject.name)
                if value:
                    context[item.subject.name] = value
            if not context:
                return api_error("该考试暂无有效成绩数据。")
            result, duration, prompt = ai_services.generate_comprehensive_analysis(config, context)
            record.subject_name = "综合"
        elif analysis_type == "student":
            student = Student.objects.filter(pk=data.get("student_id"), school_class=current, is_deleted=False).first()
            if not student:
                return api_error("请选择有效学生。")
            record.student = student
            trend = []
            for row in Exam.objects.filter(school_class=current, is_deleted=False).order_by("date"):
                subject_scores = {}
                total = 0.0
                total_full = 0
                for item in ExamSubject.objects.filter(exam=row).select_related("subject"):
                    score = Score.objects.filter(exam_subject=item, student=student, status="normal", is_deleted=False).first()
                    if score and score.score is not None:
                        total += float(score.score)
                        total_full += item.full_score
                        subject_scores[item.subject.name] = {"成绩": float(score.score), "满分": item.full_score, "班级名次": score.rank}
                if subject_scores:
                    trend.append({"考试": row.name, "日期": row.date.isoformat(), "各科": subject_scores, "总分": round(total, 1), "得分率": round(total / total_full * 100, 1) if total_full else 0})
            context = {"学生": "匿名学生", "历次考试": trend}
            result, duration, prompt = ai_services.generate_student_analysis(config, context)
            record.subject_name = student.name
        else:
            return api_error("未知的分析类型。")
        record.input_summary = json.dumps(context, ensure_ascii=False)[:500]
        record.result = result
        record.duration_ms = duration
        record.prompt_used = prompt
        record.success = True
        record.save()
        config.last_used_at = timezone.now()
        config.last_error = ""
        config.save(update_fields=["last_used_at", "last_error", "updated_at"])
        return api_ok(_record(record), 201)
    except ai_services.AIAnalysisError as exc:
        record.success = False
        record.error_message = str(exc)
        record.save()
        config.last_error = str(exc)
        config.save(update_fields=["last_error", "updated_at"])
        return api_error(f"AI 分析失败：{exc}", 400, "ai_failed")
