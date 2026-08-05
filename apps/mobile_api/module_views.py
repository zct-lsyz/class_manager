from collections import defaultdict

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone

from apps.classes.utils import get_current_class
from apps.mobile_api.auth import api_error, api_ok, mobile_api, parse_data
from apps.mobile_api.resources import _after_save, _apply_data, _force_scope, get_spec
from apps.mobile_api.serializers import serialize_instance


@mobile_api(["GET"])
def dashboard(request):
    from apps.attendance.models import AttendanceRecord
    from apps.backups.models import BackupRecord
    from apps.classes.models import Semester
    from apps.dashboard.models import Countdown, DailyQuote, TeachingWebsite
    from apps.homework.models import HomeworkRecord, HomeworkStatus
    from apps.students.models import Student
    from apps.todos.models import TodoItem

    user = request.mobile_user
    current = get_current_class(user)
    if not current:
        return api_ok({"has_current_class": False})
    today = timezone.localdate()
    semester = Semester.objects.filter(school_class=current, is_current=True).first()
    students = Student.objects.filter(school_class=current, is_deleted=False)
    week_start = today - timezone.timedelta(days=today.weekday())
    negative_custom = HomeworkStatus.objects.filter(
        school_class=current, is_active=True, is_positive=False,
    ).values_list("pk", flat=True)
    status_filter = Q(status__in=["unsubmitted", "late"])
    for status_id in negative_custom:
        status_filter |= Q(status=f"custom:{status_id}")
    todos = TodoItem.objects.filter(
        created_by=user, is_deleted=False, is_completed=False,
    ).select_related("student").order_by("priority", "deadline", "-created_at")[:8]
    last_backup = BackupRecord.objects.filter(user=user).order_by("-created_at").first()
    quote = DailyQuote.objects.filter(date=today).first() or DailyQuote.objects.order_by("-date").first()
    return api_ok({
        "has_current_class": True,
        "today": today.isoformat(),
        "class": {
            "id": current.pk, "name": current.name,
            "head_teacher": current.head_teacher, "school_name": current.school_name,
        },
        "semester": {"id": semester.pk, "name": semester.get_display_name()} if semester else None,
        "teaching_week": _teaching_week(semester, today),
        "stats": {
            "students": students.count(),
            "male": students.filter(gender="male").count(),
            "female": students.filter(gender="female").count(),
            "today_absent": AttendanceRecord.objects.filter(
                school_class=current, date=today,
            ).exclude(status="normal").values("student_id").distinct().count(),
            "week_unsubmitted": HomeworkRecord.objects.filter(
                task__school_class=current, task__assigned_date__gte=week_start,
                task__assigned_date__lte=today,
            ).filter(status_filter).count(),
            "active_todos": TodoItem.objects.filter(
                created_by=user, is_deleted=False, is_completed=False,
            ).count(),
        },
        "todos": [serialize_instance(item, get_spec("todos").fields) for item in todos],
        "countdowns": [{
            "id": row.pk, "name": row.name, "target_date": row.target_date.isoformat(),
            "days_remaining": row.days_remaining,
        } for row in Countdown.objects.filter(created_by=user, is_active=True).order_by("target_date")[:8]],
        "websites": [{
            "id": row.pk, "name": row.name, "url": row.url,
        } for row in TeachingWebsite.objects.filter(created_by=user).order_by("sort_order", "name")[:12]],
        "quote": {"content": quote.quote, "author": quote.author} if quote else None,
        "backup": {
            "status": last_backup.status,
            "created_at": last_backup.created_at.isoformat(),
            "error": last_backup.error_message,
        } if last_backup else None,
    })


def _teaching_week(semester, today):
    if not semester or not semester.start_date or today < semester.start_date:
        return 0 if semester and semester.start_date and today < semester.start_date else None
    if semester.end_date and today > semester.end_date:
        return None
    return (today - semester.start_date).days // 7 + 1


@mobile_api(["GET"])
def course_schedule(request):
    from apps.classes.models import CoursePeriod, CourseScheduleEntry, Semester
    current = get_current_class(request.mobile_user)
    semester = Semester.objects.filter(school_class=current, is_current=True).first()
    entries = CourseScheduleEntry.objects.filter(
        school_class=current, semester=semester,
    ).select_related("course").order_by("weekday", "period") if current and semester else []
    periods = CoursePeriod.objects.filter(
        school_class=current, semester=semester,
    ).order_by("period") if current and semester else []
    return api_ok({
        "semester": semester.get_display_name() if semester else None,
        "weekdays": [{"value": value, "label": label} for value, label in CourseScheduleEntry.WEEKDAY_CHOICES],
        "periods": [{
            "period": row.period, "name": row.name,
            "start_time": row.start_time.isoformat(timespec="minutes") if row.start_time else None,
            "end_time": row.end_time.isoformat(timespec="minutes") if row.end_time else None,
        } for row in periods],
        "entries": [{
            "id": row.pk, "weekday": row.weekday, "period": row.period,
            "course": row.course.name if row.course else row.subject,
            "teacher": row.teacher or (row.course.teacher if row.course else ""),
            "remarks": row.remarks,
        } for row in entries],
    })


@mobile_api(["GET"])
def seating(request):
    from apps.seating.models import SeatAssignment, SeatPlan
    current = get_current_class(request.mobile_user)
    plan = SeatPlan.objects.filter(school_class=current, is_active=True).select_related("layout").order_by("-created_at").first() if current else None
    if not plan:
        return api_ok({"plan": None, "assignments": []})
    if not plan.layout:
        return api_ok({"plan": {"id": plan.pk, "version": plan.version, "reason": plan.reason, "layout": None}, "assignments": []})
    assignments = SeatAssignment.objects.filter(seat_plan=plan).select_related("student").order_by("row", "col")
    return api_ok({
        "plan": {
            "id": plan.pk, "version": plan.version, "reason": plan.reason,
            "layout": {
                "name": plan.layout.name, "rows": plan.layout.rows, "cols": plan.layout.cols,
                "seats_per_desk": plan.layout.seats_per_desk,
                "aisle_positions": plan.layout.aisle_positions,
                "podium_position": plan.layout.podium_position,
            },
        },
        "assignments": [{
            "id": row.pk, "row": row.row, "col": row.col,
            "student_id": row.student_id, "student_name": row.student.name,
            "student_gender": row.student.gender, "student_height": row.student.height,
            "student_dormitory": row.student.display_dormitory,
            "seat_requirement": row.student.seat_requirement,
            "locked": row.is_locked,
        } for row in assignments],
    })


@mobile_api(["GET"])
def duty_roster(request):
    from apps.duty.models import DutyRoster, DutyRosterEntry, DutyRosterTask
    current = get_current_class(request.mobile_user)
    roster_id = request.GET.get("roster_id")
    qs = DutyRoster.objects.filter(school_class=current).order_by("-is_current", "-date_start") if current else DutyRoster.objects.none()
    roster = qs.filter(pk=roster_id).first() if roster_id else qs.first()
    if not roster:
        return api_ok({"roster": None, "tasks": [], "entries": []})
    tasks = DutyRosterTask.objects.filter(roster=roster).select_related("task").order_by("sort_order", "pk")
    entries = DutyRosterEntry.objects.filter(roster=roster).select_related("task", "student").order_by("day_index", "task__sort_order", "sort_order")
    return api_ok({
        "available": [{"id": row.pk, "name": row.name, "current": row.is_current} for row in qs[:30]],
        "roster": {
            "id": roster.pk, "name": roster.name, "date_start": roster.date_start.isoformat(),
            "date_end": roster.date_end.isoformat(), "day_count": roster.day_count,
            "status": roster.status, "current": roster.is_current,
        },
        "tasks": [{"id": row.task_id, "name": row.task.name, "area": row.task.area, "people_count": row.people_count} for row in tasks],
        "entries": [{
            "id": row.pk, "day_index": row.day_index,
            "date": (roster.date_start + timezone.timedelta(days=row.day_index)).isoformat(),
            "task_id": row.task_id, "task_name": row.task.name,
            "student_id": row.student_id, "student_name": row.student.name,
        } for row in entries],
    })


def _warning_rows(user):
    from apps.attendance.models import WarningRule
    from apps.dashboard.views import _warning_events
    from apps.students.models import Student
    current = get_current_class(user)
    rules = WarningRule.objects.filter(school_class=current, is_active=True) if current else []
    students = Student.objects.filter(school_class=current, is_deleted=False) if current else []
    rows = []
    for student in students:
        matched = []
        for rule in rules:
            events = _warning_events(student, rule)
            value = len(events) if rule.unit == "count" else sum(abs(item["points"]) for item in events if item["points"] < 0)
            if value >= rule.threshold:
                matched.append({
                    "rule_id": rule.pk, "rule": rule.name, "content": rule.content,
                    "value": value, "threshold": rule.threshold, "unit": rule.unit,
                    "events": [{**event, "date": event["date"].isoformat()} for event in events],
                })
        if matched:
            rows.append({"student_id": student.pk, "student_name": student.name, "warnings": matched})
    return rows


@mobile_api(["GET"])
def warnings(request):
    rows = _warning_rows(request.mobile_user)
    return api_ok({"student_count": len(rows), "students": rows})


@mobile_api(["GET"])
def growth(request):
    from apps.students.history_services import get_student_all_events
    from apps.students.models import Student
    current = get_current_class(request.mobile_user)
    student = Student.objects.filter(
        pk=request.GET.get("student_id"), school_class=current, is_deleted=False,
    ).first()
    if not student:
        return api_error("请选择当前班级的学生。", 400, "student_required")
    events = get_student_all_events(
        student, request.GET.get("date_from") or None, request.GET.get("date_to") or None,
    )
    module = request.GET.get("module", "")
    if module:
        events = [item for item in events if item["module_key"] == module]
    return api_ok({
        "student": {"id": student.pk, "name": student.name},
        "events": [{**item, "date": item["date"].isoformat()} for item in events[:500]],
    })


@mobile_api(["GET"])
def student_profile(request):
    from apps.comments.models import StudentComment
    from apps.communications.models import StudentConversation
    from apps.rewards.models import PointRecord
    from apps.scores.models import Exam, Score
    from apps.scores.views import _get_or_compute_total_ranks
    from apps.students.history_services import get_student_all_events
    from apps.students.models import Guardian, Student
    current = get_current_class(request.mobile_user)
    student = Student.objects.filter(
        pk=request.GET.get("student_id"), school_class=current, is_deleted=False,
    ).first()
    if not student:
        return api_error("请选择当前班级的学生。", 400, "student_required")
    guardian = Guardian.objects.filter(student=student, is_deleted=False).first()
    events = get_student_all_events(student)
    latest_exam_rows = list(Exam.objects.filter(
        scores__student=student, scores__is_deleted=False, is_deleted=False,
    ).distinct().order_by("-date", "-pk")[:10])
    scores = list(Score.objects.filter(
        student=student, exam__in=latest_exam_rows, is_deleted=False,
    ).select_related("exam", "exam_subject__subject").order_by("-exam__date", "exam_subject__sort_order"))
    scores_by_exam = defaultdict(list)
    for row in scores:
        scores_by_exam[row.exam_id].append(row)
    latest_exams = []
    for exam in latest_exam_rows:
        total = _get_or_compute_total_ranks(exam).get(student.pk, {})
        latest_exams.append({
            "exam_id": exam.pk, "exam": exam.name, "date": exam.date.isoformat(),
            "total_score": total.get("total_score"), "class_rank": total.get("class_rank"),
            "grade_rank": total.get("grade_rank"), "city_rank": total.get("city_rank"),
            "subjects": [{
                "subject": row.exam_subject.subject.name, "full_score": row.exam_subject.full_score,
                "score": float(row.score) if row.score is not None else None,
                "status": row.status, "status_display": row.get_status_display(),
                "class_rank": row.rank, "grade_rank": row.grade_rank, "city_rank": row.city_rank,
            } for row in scores_by_exam[exam.pk]],
        })
    conversations = StudentConversation.objects.filter(
        student=student, is_deleted=False,
    ).order_by("-date")[:30]
    comments = StudentComment.objects.filter(
        student=student, is_deleted=False,
    ).order_by("-created_at")[:30]
    student_data = serialize_instance(student, get_spec("students").fields)
    student_data.update({
        "display_class_position": student.display_class_position,
        "display_dormitory": student.display_dormitory,
        "display_bed_number": student.display_bed_number,
        "display_primary_contact": student.display_primary_contact,
        "display_primary_phone": student.display_primary_phone,
    })
    return api_ok({
        "student": student_data,
        "guardian": serialize_instance(guardian, get_spec("guardians").fields) if guardian else None,
        "summary": {
            "growth_event_count": len(events),
            "score_count": Score.objects.filter(student=student, is_deleted=False).count(),
            "conversation_count": StudentConversation.objects.filter(student=student, is_deleted=False).count(),
            "point_total": PointRecord.objects.filter(student=student, is_deleted=False).aggregate(total=Sum("points"))["total"] or 0,
        },
        "latest_scores": [{
            "exam_id": row.exam_id, "exam": row.exam.name, "date": row.exam.date.isoformat(),
            "subject": row.exam_subject.subject.name, "full_score": row.exam_subject.full_score,
            "score": float(row.score) if row.score is not None else None,
            "status": row.get_status_display(), "rank": row.rank,
            "grade_rank": row.grade_rank, "city_rank": row.city_rank,
        } for row in scores],
        "latest_exams": latest_exams,
        "growth_events": [{**item, "date": item["date"].isoformat()} for item in events[:100]],
        "conversations": [{
            "date": row.date.isoformat(), "reason": row.reason,
            "main_content": row.main_content, "student_feedback": row.student_feedback,
            "follow_up_actions": row.follow_up_actions,
        } for row in conversations],
        "comments": [{
            "type": row.get_comment_type_display(), "content": row.content,
            "status": row.get_status_display(), "created_at": row.created_at.isoformat(),
        } for row in comments],
    })


@mobile_api(["GET", "POST"])
def ranking(request):
    from apps.rewards.models import PointRecord, RankingSetting
    from apps.students.models import Student
    current = get_current_class(request.mobile_user)
    setting, _ = RankingSetting.objects.get_or_create(school_class=current)
    sources = [
        {"key": "reward", "label": "奖惩统计", "enabled": setting.enable_reward},
        {"key": "classroom_discipline", "label": "课堂纪律", "enabled": setting.enable_classroom_discipline},
        {"key": "dorm_discipline", "label": "宿舍纪律", "enabled": setting.enable_dorm_discipline},
        {"key": "hygiene", "label": "宿舍卫生", "enabled": setting.enable_hygiene},
        {"key": "attendance", "label": "考勤管理", "enabled": setting.enable_attendance},
        {"key": "homework", "label": "作业检查", "enabled": setting.enable_homework},
    ]
    data = parse_data(request) if request.method == "POST" else {}
    requested_value = data.get("sources") if request.method == "POST" else request.GET.get("sources", "")
    requested = requested_value if isinstance(requested_value, list) else [value for value in str(requested_value).split(",") if value]
    available = {item["key"] for item in sources}
    enabled_types = [value for value in requested if value in available] if request.method == "POST" or requested else setting.enabled_source_types()
    if request.method == "POST":
        fields = {
            "reward": "enable_reward", "classroom_discipline": "enable_classroom_discipline",
            "dorm_discipline": "enable_dorm_discipline", "hygiene": "enable_hygiene",
            "attendance": "enable_attendance", "homework": "enable_homework",
        }
        for key, name in fields.items():
            setattr(setting, name, key in enabled_types)
        setting.save(update_fields=[*fields.values(), "updated_at"])
        for item in sources:
            item["enabled"] = item["key"] in enabled_types
    qs = PointRecord.objects.filter(
        school_class=current, source_type__in=enabled_types, is_deleted=False,
    ).select_related("student")
    if request.GET.get("date_from"):
        qs = qs.filter(date__gte=request.GET["date_from"])
    if request.GET.get("date_to"):
        qs = qs.filter(date__lte=request.GET["date_to"])
    totals = defaultdict(int)
    reasons = defaultdict(lambda: defaultdict(lambda: {"total": 0, "count": 0}))
    for row in qs:
        totals[row.student_id] += row.points
        reasons[row.student_id][row.reason]["total"] += row.points
        reasons[row.student_id][row.reason]["count"] += 1
    rows = []
    for student in Student.objects.filter(school_class=current, is_deleted=False):
        detail = sorted(reasons[student.pk].items(), key=lambda item: abs(item[1]["total"]), reverse=True)[:6]
        rows.append({
            "student_id": student.pk, "student_name": student.name, "total": totals[student.pk],
            "reasons": [{"reason": name, **data} for name, data in detail],
        })
    rows.sort(key=lambda item: (-item["total"], item["student_name"]))
    rank = 0
    last = None
    for index, row in enumerate(rows, 1):
        if row["total"] != last:
            rank = index
            last = row["total"]
        row["rank"] = rank
    return api_ok({
        "sources": sources, "selected_sources": enabled_types,
        "enabled_labels": [item["label"] for item in sources if item["key"] in enabled_types],
        "ranking": rows,
    })


@mobile_api(["GET"])
def score_analysis(request):
    from apps.scores.analysis_exports import compute_analysis_data
    from apps.scores.models import Exam, Score
    current = get_current_class(request.mobile_user)
    exams = Exam.objects.filter(school_class=current, is_deleted=False).order_by("-date") if current else []
    exam = exams.filter(pk=request.GET.get("exam_id")).first() if request.GET.get("exam_id") else exams.first()
    if not exam:
        return api_ok({"exam": None, "exams": []})
    data = compute_analysis_data(current, exam)
    score_rows = {
        (row.student_id, row.exam_subject_id): row
        for row in Score.objects.filter(exam=exam, is_deleted=False)
    }
    student_rows = []
    for row in data["class_total_table"]:
        subject_details = []
        for exam_subject in data["exam_subjects"]:
            score = score_rows.get((row["student"].pk, exam_subject.pk))
            subject_details.append({
                "subject": exam_subject.subject.name, "full_score": exam_subject.full_score,
                "score": float(score.score) if score and score.score is not None else None,
                "status": score.status if score else None,
                "status_display": score.get_status_display() if score else "未录入",
                "class_rank": score.rank if score else None,
                "grade_rank": score.grade_rank if score else None,
                "city_rank": score.city_rank if score else None,
            })
        student_rows.append({
            "student_id": row["student"].pk, "student_name": row["student"].name,
            "total_score": row["total_score"], "rank": row["rank"],
            "grade_rank": row["total_grade_rank"], "city_rank": row["total_city_rank"],
            "subjects": row["subjects"], "subject_details": subject_details,
        })
    return api_ok({
        "exams": [{"id": row.pk, "name": row.name, "date": row.date.isoformat()} for row in exams[:50]],
        "exam": {"id": exam.pk, "name": exam.name, "date": exam.date.isoformat(), "published": exam.is_published},
        "subjects": [{"name": name, **values} for name, values in data["analysis_data"].items()],
        "total": {"count": data["total_count"], "avg": data["total_avg"], "max": data["total_max"]},
        "students": student_rows,
    })


@mobile_api(["GET"])
def score_comparison(request):
    from apps.scores.analysis_services import build_comparison_data
    from apps.scores.models import Exam, ExamSubject
    current = get_current_class(request.mobile_user)
    exams = Exam.objects.filter(school_class=current, is_deleted=False).order_by("-date") if current else Exam.objects.none()
    exam = exams.filter(pk=request.GET.get("exam_id")).first() if request.GET.get("exam_id") else exams.first()
    if not exam:
        return api_ok({"exam": None, "classes": [], "comparison": []})
    subjects = list(ExamSubject.objects.filter(exam=exam).select_related("subject"))
    external, table, chart = build_comparison_data(exam, subjects, current)
    return api_ok({
        "exam": {"id": exam.pk, "name": exam.name, "date": exam.date.isoformat()},
        "classes": [{"key": "own", "name": current.name}] + [{"key": f"ext_{row.pk}", "name": str(row)} for row in external],
        "comparison": table, "chart_data": chart,
    })


@mobile_api(["GET"])
def selected_student_score_analysis(request):
    try:
        student_id = int(request.GET.get("student_id", 0))
    except ValueError:
        return api_error("学生参数无效。")
    return student_score_analysis.__wrapped__(request, student_id)


def _date_filter(request, field="date"):
    values = {}
    if request.GET.get("date_from"):
        values[f"{field}__gte"] = request.GET["date_from"]
    if request.GET.get("date_to"):
        values[f"{field}__lte"] = request.GET["date_to"]
    return values


@mobile_api(["GET"])
def attendance_stats(request):
    from apps.attendance.models import AttendanceRecord
    current = get_current_class(request.mobile_user)
    rows = AttendanceRecord.objects.filter(school_class=current, **_date_filter(request)) if current else AttendanceRecord.objects.none()
    return api_ok({
        "total": rows.count(),
        "by_status": list(rows.values("status").annotate(count=Count("id")).order_by("status")),
        "by_student": list(rows.values("student_id", "student__name").annotate(count=Count("id"), points=Sum("points_deducted")).order_by("-count")[:100]),
        "by_reason": list(rows.exclude(reason="").values("reason").annotate(count=Count("id")).order_by("-count")[:30]),
    })


@mobile_api(["GET"])
def homework_stats(request):
    from apps.homework.models import HomeworkRecord
    current = get_current_class(request.mobile_user)
    rows = HomeworkRecord.objects.filter(task__school_class=current, **_date_filter(request, "task__assigned_date")) if current else HomeworkRecord.objects.none()
    return api_ok({
        "total": rows.count(),
        "by_status": list(rows.values("status").annotate(count=Count("id")).order_by("-count")),
        "by_student": list(rows.values("student_id", "student__name").annotate(count=Count("id")).order_by("-count")[:100]),
        "by_task": list(rows.values("task_id", "task__title").annotate(count=Count("id")).order_by("-task__assigned_date")[:100]),
    })


@mobile_api(["GET"])
def discipline_stats(request):
    from apps.discipline.models import ClassroomDisciplineRecord, DormDisciplineRecord
    current = get_current_class(request.mobile_user)
    classroom = ClassroomDisciplineRecord.objects.filter(school_class=current, is_deleted=False, **_date_filter(request)) if current else ClassroomDisciplineRecord.objects.none()
    dorm = DormDisciplineRecord.objects.filter(school_class=current, is_deleted=False, **_date_filter(request)) if current else DormDisciplineRecord.objects.none()
    return api_ok({
        "classroom": {"count": classroom.count(), "points": classroom.aggregate(value=Sum("points_deducted"))["value"] or 0,
                      "by_student": list(classroom.values("student_id", "student__name").annotate(count=Count("id"), points=Sum("points_deducted")).order_by("-count")[:100])},
        "dormitory": {"count": dorm.count(), "points": dorm.aggregate(value=Sum("points_deducted"))["value"] or 0,
                      "by_student": list(dorm.values("student_id", "student__name").annotate(count=Count("id"), points=Sum("points_deducted")).order_by("-count")[:100])},
    })


@mobile_api(["GET"])
def dormitory_stats(request):
    from apps.dormitory.models import DormHygieneCheck
    current = get_current_class(request.mobile_user)
    rows = DormHygieneCheck.objects.filter(school_class=current, is_deleted=False, **_date_filter(request)) if current else DormHygieneCheck.objects.none()
    return api_ok({
        "count": rows.count(), "average_score": rows.aggregate(value=Avg("total_score"))["value"],
        "by_grade": list(rows.values("grade").annotate(count=Count("id")).order_by("grade")),
        "by_room": list(rows.values("room_id", "room__room_number", "room__building__name").annotate(count=Count("id"), average_score=Avg("total_score")).order_by("-average_score")[:100]),
    })


@mobile_api(["GET"])
def reward_stats(request):
    from apps.rewards.models import RewardRecord
    current = get_current_class(request.mobile_user)
    rows = RewardRecord.objects.filter(school_class=current, is_deleted=False, **_date_filter(request)) if current else RewardRecord.objects.none()
    return api_ok({
        "count": rows.count(), "points": rows.aggregate(value=Sum("points"))["value"] or 0,
        "by_type": list(rows.values("record_type").annotate(count=Count("id"), points=Sum("points")).order_by("record_type")),
        "by_student": list(rows.values("student_id", "student__name").annotate(count=Count("id"), points=Sum("points")).order_by("-points")[:100]),
    })


def _batch_create_hygiene(request, spec, data):
    from apps.dormitory.models import DormAssignment, DormHygieneItem, DormHygieneItemScore
    from apps.dormitory.views import _create_hygiene_deductions
    from apps.students.models import Student
    current = get_current_class(request.mobile_user)
    instance = spec.model()
    _apply_data(instance, spec, data, request)
    _force_scope(instance, spec, request.mobile_user, True)
    instance.full_clean()
    student_ids = data.get("student_ids", [])
    if not isinstance(student_ids, list):
        raise ValidationError({"student_ids": ["请选择学生。"]})
    student_mode = "all" if data.get("student_mode") == "all" or "all" in student_ids else "selected"
    assignments = DormAssignment.objects.filter(
        room=instance.room, room__building__school_class=current, is_current=True,
        student__school_class=current, student__is_deleted=False,
    )
    room_student_ids = set(assignments.values_list("student_id", flat=True))
    if student_mode == "all":
        selected_ids = room_student_ids
    else:
        try:
            selected_ids = {int(value) for value in student_ids}
        except (TypeError, ValueError):
            raise ValidationError({"student_ids": ["学生参数无效。"]})
        if selected_ids - room_student_ids:
            raise ValidationError({"student_ids": ["所选学生不属于该宿舍。"]})
    if not selected_ids:
        raise ValidationError({"student_ids": ["请选择至少一名该宿舍学生。"]})
    values = data.get("scores", [])
    if not isinstance(values, list):
        raise ValidationError({"scores": ["scores 必须是数组。"]})
    items = {
        row.pk: row for row in DormHygieneItem.objects.filter(
            school_class=current, is_active=True,
        )
    }
    score_rows = []
    total = 0
    deduction = 0
    for value in values:
        try:
            item = items.get(int(value.get("item_id", 0)))
            score = int(value.get("score", 0))
        except (AttributeError, TypeError, ValueError):
            raise ValidationError({"scores": ["卫生检查得分参数无效。"]})
        if not item:
            raise ValidationError({"scores": ["卫生检查项不存在或不属于当前班级。"]})
        score = max(0, min(score, item.full_score))
        score_rows.append((item, score, str(value.get("deduction_reason", ""))))
        total += score
        deduction += max(0, item.full_score - score)
    full = sum(item.full_score for item in items.values())
    ratio = total / full if full else 0
    instance.total_score = total
    instance.grade = "excellent" if ratio >= .9 else "good" if ratio >= .8 else "fair" if ratio >= .6 else "poor"
    with transaction.atomic():
        instance.save()
        for item, score, reason in score_rows:
            DormHygieneItemScore.objects.create(
                check_record=instance, item=item, score=score, deduction_reason=reason,
            )
        _after_save(instance, spec, request.mobile_user)
        students = Student.objects.filter(pk__in=selected_ids, school_class=current, is_deleted=False)
        deducted_count = _create_hygiene_deductions(
            current, instance.semester, instance, students, deduction,
        ) if deduction else 0
    return api_ok({
        "count": 1, "records": [serialize_instance(instance, spec.fields)],
        "selected_student_count": len(selected_ids), "deducted_count": deducted_count,
        "points_deducted": deduction,
    }, 201)


@mobile_api(["POST"])
def batch_create(request, resource):
    spec = get_spec(resource)
    if not spec or resource not in {
        "attendance", "homework_records", "classroom_discipline", "dorm_discipline",
        "hygiene_checks", "rewards", "conversations", "home_school_contacts", "concerns", "scores",
    }:
        return api_error("该资源不支持批量登记。", 404, "batch_not_supported")
    data = parse_data(request)
    if resource == "hygiene_checks":
        return _batch_create_hygiene(request, spec, data)
    records = data.get("records")
    if not isinstance(records, list):
        student_ids = data.get("student_ids", [])
        if not isinstance(student_ids, list) or not student_ids:
            return api_error("请提供 records 或 student_ids。")
        records = [{**data, "student": student_id} for student_id in student_ids]
    created = []
    with transaction.atomic():
        for values in records:
            instance = spec.model()
            fake_request = request
            _apply_data(instance, spec, values, fake_request)
            _force_scope(instance, spec, request.mobile_user, True)
            instance.full_clean()
            if resource == "homework_records":
                instance, _ = spec.model.objects.update_or_create(
                    task=instance.task, student=instance.student,
                    defaults={name: getattr(instance, name) for name in spec.editable if name not in {"task", "student"}},
                )
            elif resource == "scores":
                instance, _ = spec.model.objects.update_or_create(
                    exam_subject=instance.exam_subject, student=instance.student,
                    defaults={
                        "exam": instance.exam, "score": instance.score, "status": instance.status,
                        "grade_rank": instance.grade_rank, "city_rank": instance.city_rank,
                        "remarks": instance.remarks, "is_deleted": False,
                    },
                )
            else:
                instance.save()
            _after_save(instance, spec, request.mobile_user)
            created.append(serialize_instance(instance, spec.fields))
    return api_ok({"count": len(created), "records": created}, 201)


@mobile_api(["POST"])
def assign_bed(request, pk):
    from apps.classes.models import Semester
    from apps.dormitory.models import DormAssignment, DormBed
    from apps.dormitory.services import release_bed
    from apps.students.models import Student
    current = get_current_class(request.mobile_user)
    bed = DormBed.objects.filter(pk=pk, room__building__school_class=current).select_related("room").first()
    if not bed:
        return api_error("床位不存在。", 404, "not_found")
    data = parse_data(request)
    student_id = data.get("student_id")
    with transaction.atomic():
        previous = list(Student.objects.filter(dorm_assignments__is_current=True).filter(
            Q(dorm_assignments__bed=bed) | Q(pk=student_id or None),
        ).distinct())
        if student_id:
            student = Student.objects.filter(pk=student_id, school_class=current, is_deleted=False).first()
            if not student:
                raise ValidationError("学生不存在或不属于当前班级。")
            DormAssignment.objects.filter(student=student, is_current=True).update(is_current=False, bed=None)
            release_bed(bed)
            DormAssignment.objects.create(
                student=student, room=bed.room, bed=bed, is_current=True,
                semester=Semester.objects.filter(school_class=current, is_current=True).first(),
            )
            student.dormitory = str(bed.room)
            student.bed_number = bed.bed_number
            student.save(update_fields=["dormitory", "bed_number", "updated_at"])
        else:
            release_bed(bed)
        for student in previous:
            if not student.dorm_assignments.filter(is_current=True).exists():
                student.dormitory = ""
                student.bed_number = ""
                student.save(update_fields=["dormitory", "bed_number", "updated_at"])
    return api_ok()


@mobile_api(["GET"])
def dorm_overview(request):
    from apps.dormitory.models import DormAssignment, DormBed, DormBuilding, DormRoom
    current = get_current_class(request.mobile_user)
    buildings = DormBuilding.objects.filter(school_class=current).order_by("sort_order", "name") if current else []
    rooms = DormRoom.objects.filter(building__school_class=current).select_related("building", "monitor").order_by("building__sort_order", "room_number") if current else []
    room_rows = []
    for room in rooms:
        assignments = {
            row.bed_id: row for row in DormAssignment.objects.filter(
                room=room, is_current=True,
            ).select_related("student", "bed")
        }
        room_rows.append({
            "id": room.pk, "building_id": room.building_id, "building": room.building.name,
            "room_number": room.room_number, "floor": room.floor,
            "room_type": room.room_type, "bed_count": room.bed_count,
            "monitor_id": room.monitor_id, "monitor_name": room.monitor.name if room.monitor else "",
            "active": room.is_active, "remarks": room.remarks,
            "beds": [{
                "id": bed.pk, "bed_number": bed.bed_number, "active": bed.is_active,
                "student_id": assignments[bed.pk].student_id if bed.pk in assignments else None,
                "student_name": assignments[bed.pk].student.name if bed.pk in assignments else "",
            } for bed in DormBed.objects.filter(room=room).order_by("bed_number")],
        })
    return api_ok({
        "buildings": [{"id": row.pk, "name": row.name, "floors": row.floors} for row in buildings],
        "rooms": room_rows,
    })


@mobile_api(["POST"])
def set_room_monitor(request, pk):
    from apps.dormitory.models import DormAssignment, DormRoom
    current = get_current_class(request.mobile_user)
    room = DormRoom.objects.filter(pk=pk, building__school_class=current).first()
    if not room:
        return api_error("宿舍不存在。", 404, "not_found")
    student_id = parse_data(request).get("student_id")
    if student_id:
        assignment = DormAssignment.objects.filter(
            room=room, student_id=student_id, is_current=True,
        ).select_related("student").first()
        if not assignment:
            return api_error("舍长必须是当前宿舍已分配的学生。")
        room.monitor = assignment.student
    else:
        room.monitor = None
    room.save(update_fields=["monitor", "updated_at"])
    return api_ok()


@mobile_api(["GET", "PUT"])
def hygiene_scores(request, pk):
    from apps.dormitory.models import DormHygieneCheck, DormHygieneItem, DormHygieneItemScore
    current = get_current_class(request.mobile_user)
    check = DormHygieneCheck.objects.filter(pk=pk, school_class=current, is_deleted=False).select_related("room").first()
    if not check:
        return api_error("卫生检查记录不存在。", 404, "not_found")
    items = list(DormHygieneItem.objects.filter(school_class=current).order_by("sort_order", "name"))
    if request.method == "PUT":
        values = parse_data(request).get("scores", [])
        if not isinstance(values, list):
            return api_error("scores 必须是数组。")
        allowed = {item.pk: item for item in items}
        total = 0
        full = 0
        with transaction.atomic():
            for value in values:
                item = allowed.get(int(value.get("item_id", 0)))
                if not item:
                    raise ValidationError("卫生检查项不存在或不属于当前班级。")
                score = max(0, min(int(value.get("score", 0)), item.full_score))
                DormHygieneItemScore.objects.update_or_create(
                    check_record=check, item=item,
                    defaults={"score": score, "deduction_reason": str(value.get("deduction_reason", ""))},
                )
            existing = DormHygieneItemScore.objects.filter(check_record=check).select_related("item")
            for row in existing:
                total += row.score
                full += row.item.full_score
            ratio = total / full if full else 0
            check.total_score = total
            check.grade = "excellent" if ratio >= .9 else "good" if ratio >= .8 else "fair" if ratio >= .6 else "poor"
            check.save(update_fields=["total_score", "grade", "updated_at"])
    scores = {row.item_id: row for row in DormHygieneItemScore.objects.filter(check_record=check)}
    return api_ok({
        "check_id": check.pk, "room": str(check.room), "date": check.date.isoformat(),
        "total_score": check.total_score, "grade": check.grade,
        "items": [{
            "item_id": item.pk, "name": item.name, "full_score": item.full_score,
            "score": scores[item.pk].score if item.pk in scores else None,
            "deduction_reason": scores[item.pk].deduction_reason if item.pk in scores else "",
        } for item in items],
    })


@mobile_api(["GET"])
def student_score_analysis(request, pk):
    from apps.scores.models import Exam, ExamSubject, Score
    from apps.scores.views import _get_or_compute_total_ranks
    from apps.students.models import Student
    current = get_current_class(request.mobile_user)
    student = Student.objects.filter(pk=pk, school_class=current, is_deleted=False).first()
    if not student:
        return api_error("学生不存在。", 404, "not_found")
    exams = list(Exam.objects.filter(school_class=current, is_deleted=False).order_by("date"))
    rows = []
    for exam in exams:
        subjects = []
        calculated_total = 0.0
        has_score = False
        for exam_subject in ExamSubject.objects.filter(exam=exam).select_related("subject"):
            score = Score.objects.filter(
                exam_subject=exam_subject, student=student, is_deleted=False,
            ).first()
            subjects.append({
                "subject": exam_subject.subject.name, "full_score": exam_subject.full_score,
                "score": float(score.score) if score and score.score is not None else None,
                "status": score.status if score else None,
                "status_display": score.get_status_display() if score else "未录入",
                "rank": score.rank if score else None,
                "grade_rank": score.grade_rank if score else None, "city_rank": score.city_rank if score else None,
            })
            if score and score.status == "normal" and score.score is not None:
                calculated_total += float(score.score)
                has_score = True
        total = _get_or_compute_total_ranks(exam).get(student.pk)
        if has_score or total:
            rows.append({
                "exam_id": exam.pk, "exam": exam.name, "date": exam.date.isoformat(),
                "total": total["total_score"] if total and total["total_score"] is not None else round(calculated_total, 1),
                "class_rank": total["class_rank"] if total else None,
                "grade_rank": total["grade_rank"] if total else None,
                "city_rank": total["city_rank"] if total else None,
                "subjects": subjects,
            })
    return api_ok({"student": {"id": student.pk, "name": student.name}, "history": rows})


@mobile_api(["GET"])
def notifications(request):
    from apps.todos.models import TodoItem
    now = timezone.now()
    upcoming = TodoItem.objects.filter(
        created_by=request.mobile_user, is_deleted=False, is_completed=False,
        deadline__isnull=False, deadline__lte=now + timezone.timedelta(days=30),
    ).select_related("student").order_by("deadline")[:200]
    warnings_data = _warning_rows(request.mobile_user)
    return api_ok({
        "server_time": now.isoformat(),
        "todos": [serialize_instance(row, get_spec("todos").fields) for row in upcoming],
        "warnings": warnings_data,
    })
