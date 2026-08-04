import json

from django.utils import timezone

from apps.classes.utils import get_current_class
from apps.mobile_api.auth import api_error, api_ok, mobile_api, parse_data
from apps.scores import ai_services
from apps.scores.ai_models import AIAnalysisConfig, AIAnalysisRecord
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
        config.temperature = float(data.get("temperature", 0.5))
        config.is_enabled = bool(data.get("is_enabled", False))
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
